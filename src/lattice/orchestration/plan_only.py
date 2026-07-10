from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from typing_extensions import NotRequired, TypedDict

from lattice.capability_evolution import CapabilityGapDetector, EvolutionAgent, EvolutionRequest
from lattice.core import TaskUnderstandingAgent
from lattice.graph import HealthyGraphStore
from lattice.permissions import PermissionDecision, PermissionGate
from lattice.planning import ResearchStrategyPlanner, WorkflowPathSearch, WorkflowSearchResult
from lattice.projection import RuntimeViewProjector
from lattice.runtime import AgentEvent, AgentEventLog
from lattice.schemas import (
    AgenticExecutionPlan,
    CapabilityGap,
    GraphPatch,
    Provenance,
    ResearchTask,
    RuntimeGraphContext,
    TaskFingerprint,
    WorkflowAuditReport,
)
from lattice.skill import SkillContext, SkillContextProvider
from lattice.verification import WorkflowVerifier


class PlanOnlyState(TypedDict):
    request: str
    session_id: str
    status: NotRequired[str]
    task_fingerprint: NotRequired[TaskFingerprint]
    research_task: NotRequired[ResearchTask]
    runtime_context: NotRequired[RuntimeGraphContext]
    workflow_search_result: NotRequired[WorkflowSearchResult]
    capability_gaps: NotRequired[list[CapabilityGap]]
    evolution_request: NotRequired[EvolutionRequest]
    proposed_evolution_patch: NotRequired[GraphPatch | None]
    workflow_report: NotRequired[WorkflowAuditReport]
    skill_contexts: NotRequired[list[SkillContext]]
    execution_plan: NotRequired[AgenticExecutionPlan | None]
    permission_decision: NotRequired[PermissionDecision]
    response: NotRequired[str]


def build_plan_only_graph(
    *,
    healthy_graph_store: HealthyGraphStore | None = None,
) -> Any:
    graph = StateGraph(PlanOnlyState)
    graph.add_node("receive_request", receive_request)
    graph.add_node("understand_task", understand_task)
    graph.add_node(
        "project_runtime_context",
        lambda state: project_runtime_context(state, healthy_graph_store=healthy_graph_store),
    )
    graph.add_node("search_workflow_path", search_workflow_path)
    graph.add_node("detect_capability_gaps", detect_capability_gaps)
    graph.add_node("request_evolution", request_evolution)
    graph.add_node("resolve_skill_context", resolve_skill_context)
    graph.add_node("formulate_research_strategy", formulate_research_strategy)
    graph.add_node("verify_workflow", verify_workflow)
    graph.add_node("compile_aep", compile_aep)
    graph.add_node("permission_check", permission_check)
    graph.add_node("produce_response", produce_response)

    graph.add_edge(START, "receive_request")
    graph.add_edge("receive_request", "understand_task")
    graph.add_edge("understand_task", "project_runtime_context")
    graph.add_edge("project_runtime_context", "search_workflow_path")
    graph.add_edge("search_workflow_path", "detect_capability_gaps")
    graph.add_edge("detect_capability_gaps", "request_evolution")
    graph.add_edge("request_evolution", "resolve_skill_context")
    graph.add_edge("resolve_skill_context", "formulate_research_strategy")
    graph.add_edge("formulate_research_strategy", "verify_workflow")
    graph.add_edge("verify_workflow", "compile_aep")
    graph.add_edge("compile_aep", "permission_check")
    graph.add_edge("permission_check", "produce_response")
    graph.add_edge("produce_response", END)
    return graph.compile()


def run_plan_only(
    request: str,
    *,
    session_id: str | None = None,
    event_log: AgentEventLog | None = None,
    healthy_graph_store: HealthyGraphStore | None = None,
) -> PlanOnlyState:
    compiled = build_plan_only_graph(healthy_graph_store=healthy_graph_store)
    initial_state: PlanOnlyState = {
        "request": request,
        "session_id": session_id or f"session-{uuid4()}",
    }
    result = compiled.invoke(initial_state)
    final_state = cast(PlanOnlyState, result)
    if event_log is not None:
        append_plan_only_events(event_log, final_state)
    return final_state


def append_plan_only_events(event_log: AgentEventLog, state: PlanOnlyState) -> None:
    provenance = [Provenance(source_type="plan_only_orchestrator")]
    session_id = state["session_id"]
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="UserRequestReceived",
            payload={"request": state["request"]},
            provenance=provenance,
        )
    )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="TaskUnderstood",
            payload=state["research_task"].model_dump(mode="json"),
            provenance=provenance,
        )
    )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="PlanModeEntered",
            payload={"mode": "plan_only"},
            provenance=provenance,
        )
    )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="TaskFingerprinted",
            payload=state["task_fingerprint"].model_dump(mode="json"),
            provenance=provenance,
        )
    )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="RuntimeGraphContextProjected",
            payload=state["runtime_context"].model_dump(mode="json"),
            provenance=provenance,
        )
    )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="WorkflowPathSelected",
            payload=state["workflow_search_result"].model_dump(mode="json"),
            provenance=provenance,
        )
    )
    for gap in state.get("capability_gaps", []):
        event_log.append(
            AgentEvent(
                event_id=f"event-{uuid4()}",
                session_id=session_id,
                event_type="CapabilityGapDetected",
                payload=gap.model_dump(mode="json"),
                provenance=provenance,
            )
        )
    if state.get("evolution_request") is not None:
        proposed_patch = state.get("proposed_evolution_patch")
        event_log.append(
            AgentEvent(
                event_id=f"event-{uuid4()}",
                session_id=session_id,
                event_type="EvolutionRequested",
                payload=state["evolution_request"].model_dump(mode="json"),
                graph_patch_ids=[proposed_patch.patch_id] if proposed_patch is not None else [],
                provenance=provenance,
            )
        )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="WorkflowVerified",
            payload=state["workflow_report"].model_dump(mode="json"),
            provenance=provenance,
        )
    )
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type="PermissionChecked",
            payload=state["permission_decision"].model_dump(mode="json"),
            provenance=provenance,
        )
    )


def receive_request(state: PlanOnlyState) -> PlanOnlyState:
    return {**state, "status": "received"}


def understand_task(state: PlanOnlyState) -> PlanOnlyState:
    fingerprint, research_task = TaskUnderstandingAgent().understand(
        state["request"],
        user_id="local",
        execution_intent="plan_only",
    )
    return {
        **state,
        "status": "task_understood",
        "task_fingerprint": fingerprint,
        "research_task": research_task,
    }


def project_runtime_context(
    state: PlanOnlyState,
    *,
    healthy_graph_store: HealthyGraphStore | None = None,
) -> PlanOnlyState:
    fingerprint = state["task_fingerprint"]
    context = RuntimeViewProjector(healthy_graph_store=healthy_graph_store).project(fingerprint)
    return {**state, "status": "runtime_context_projected", "runtime_context": context}


def search_workflow_path(state: PlanOnlyState) -> PlanOnlyState:
    result = WorkflowPathSearch().search(state["task_fingerprint"], state["runtime_context"])
    return {**state, "status": "planning", "workflow_search_result": result}


def detect_capability_gaps(state: PlanOnlyState) -> PlanOnlyState:
    gaps = CapabilityGapDetector().detect(
        fingerprint=state["task_fingerprint"],
        runtime_context=state["runtime_context"],
        workflow_search_result=state["workflow_search_result"],
    )
    status = "capability_gap_detected" if gaps else state["status"]
    return {**state, "status": status, "capability_gaps": gaps}


def request_evolution(state: PlanOnlyState) -> PlanOnlyState:
    gaps = state.get("capability_gaps", [])
    if not gaps:
        return state
    source_event = AgentEvent(
        event_id=f"event-{uuid4()}",
        session_id=state["session_id"],
        event_type="CapabilityGapDetected",
        payload={"gap_ids": [gap.gap_id for gap in gaps]},
        provenance=[Provenance(source_type="plan_only_orchestrator")],
    )
    request, patch = EvolutionAgent().propose_gap_patch(
        gaps=gaps,
        source_events=[source_event],
    )
    return {
        **state,
        "status": "evolution_requested",
        "evolution_request": request,
        "proposed_evolution_patch": patch,
    }


def resolve_skill_context(state: PlanOnlyState) -> PlanOnlyState:
    contexts = SkillContextProvider().resolve_skills_for_task(
        state["research_task"],
        state["runtime_context"],
    )
    return {**state, "status": "skill_context_resolved", "skill_contexts": contexts}


def formulate_research_strategy(state: PlanOnlyState) -> PlanOnlyState:
    plan = ResearchStrategyPlanner().build(
        task=state["research_task"],
        fingerprint=state["task_fingerprint"],
        runtime_context=state["runtime_context"],
        search_result=state["workflow_search_result"],
        skill_contexts=state.get("skill_contexts", []),
    )
    return {**state, "status": "execution_plan_compiled", "execution_plan": plan}


def verify_workflow(state: PlanOnlyState) -> PlanOnlyState:
    search_result = state["workflow_search_result"]
    report = WorkflowVerifier().verify(search_result, state.get("execution_plan"))
    return {**state, "status": "workflow_verified", "workflow_report": report}


def compile_aep(state: PlanOnlyState) -> PlanOnlyState:
    report = state["workflow_report"]
    if report.status == "blocked":
        return {**state, "status": "plan_blocked"}
    if state.get("execution_plan") is None:
        return {**state, "status": "plan_blocked"}
    return {**state, "status": "plan_verified"}


def permission_check(state: PlanOnlyState) -> PlanOnlyState:
    decision = PermissionGate().check_execution(state["workflow_report"], mode="plan_only")
    return {**state, "permission_decision": decision}


def produce_response(state: PlanOnlyState) -> PlanOnlyState:
    report = state["workflow_report"]
    if report.status == "blocked":
        blocker_text = "; ".join(blocker.code for blocker in report.blockers)
        response = f"Plan blocked: {blocker_text}"
    else:
        response = "Plan verified."
    return {**state, "response": response}
