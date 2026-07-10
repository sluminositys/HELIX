from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from typing_extensions import NotRequired, TypedDict

from lattice.capability_evolution import (
    CapabilityGapDetector,
    EvolutionAgent,
    EvolutionRequest,
    NoopRuntimeCapabilityDiscoverer,
    RuntimeCapabilityDiscoverer,
    RuntimeDiscoveryResult,
)
from lattice.core import TaskFingerprinter, TaskUnderstandingAgent
from lattice.graph import FullGraphStore, HealthyGraphStore
from lattice.graph_health import MemoryHealthCompiler
from lattice.graph_patch import GraphPatchAuditor, PatchAuditReport
from lattice.memory import (
    ExperienceCandidateExtractor,
    ExperienceGeneralizationDecision,
    ExperienceGeneralizationGate,
)
from lattice.permissions import PermissionDecision, PermissionGate
from lattice.planning import (
    AgenticExecutionPlanBuilder,
    ResearchStrategyPlanner,
    WorkflowPathSearch,
    WorkflowSearchResult,
)
from lattice.projection import RuntimeViewProjector
from lattice.runtime import (
    AgentEvent,
    AgentEventLog,
    AgentEventType,
    RunRecordBuilder,
    ScriptDraftError,
    ScriptGenerationAgent,
    ScriptReviewAgent,
    ScriptRunner,
)
from lattice.schemas import (
    AgenticExecutionPlan,
    ArtifactManifest,
    Blocker,
    CapabilityGap,
    ExperienceCandidate,
    GraphPatch,
    PermissionMode,
    Provenance,
    ResearchTask,
    ResultVerificationReport,
    RunRecord,
    RuntimeGraphContext,
    ScriptExecutionRawResult,
    ScriptProposal,
    ScriptReviewResult,
    TaskFingerprint,
    WorkflowAuditReport,
)
from lattice.skill import SkillContext, SkillContextProvider
from lattice.verification import ResultVerifier, WorkflowVerifier


class ExecutionState(TypedDict):
    request: str
    session_id: str
    permission_mode: PermissionMode
    status: NotRequired[str]
    task_fingerprint: NotRequired[TaskFingerprint]
    research_task: NotRequired[ResearchTask]
    runtime_context: NotRequired[RuntimeGraphContext]
    workflow_search_result: NotRequired[WorkflowSearchResult]
    capability_gaps: NotRequired[list[CapabilityGap]]
    evolution_request: NotRequired[EvolutionRequest]
    proposed_evolution_patch: NotRequired[GraphPatch | None]
    runtime_discovery_result: NotRequired[RuntimeDiscoveryResult]
    runtime_graph_patches: NotRequired[list[GraphPatch]]
    workflow_report: NotRequired[WorkflowAuditReport]
    execution_plan: NotRequired[AgenticExecutionPlan | None]
    skill_contexts: NotRequired[list[SkillContext]]
    script_proposal: NotRequired[ScriptProposal | None]
    script_generation_error: NotRequired[str | None]
    script_revision_count: NotRequired[int]
    script_review: NotRequired[ScriptReviewResult | None]
    permission_decision: NotRequired[PermissionDecision]
    script_execution_result: NotRequired[ScriptExecutionRawResult | None]
    execution_attempt_count: NotRequired[int]
    run_record: NotRequired[RunRecord | None]
    artifact_manifest: NotRequired[ArtifactManifest | None]
    result_verification: NotRequired[ResultVerificationReport | None]
    experience_candidate: NotRequired[ExperienceCandidate | None]
    experience_generalization: NotRequired[ExperienceGeneralizationDecision | None]
    experience_patch: NotRequired[GraphPatch | None]
    experience_patch_audit: NotRequired[PatchAuditReport | None]
    graph_patch_audits: NotRequired[list[PatchAuditReport]]
    graph_write_id: NotRequired[str | None]
    graph_update_write_ids: NotRequired[list[str]]
    healthy_graph_write_id: NotRequired[str | None]
    response: NotRequired[str]


def build_execution_graph(
    *,
    healthy_graph_store: HealthyGraphStore | None = None,
    full_graph_store: FullGraphStore | None = None,
    toolcall_registry: object | None = None,
    runtime_backends: object | None = None,
    runtime_discoverer: RuntimeCapabilityDiscoverer | None = None,
    apply_experience_patch: bool = True,
    task_understanding_agent: TaskUnderstandingAgent | None = None,
    skill_context_provider: SkillContextProvider | None = None,
    strategy_planner: ResearchStrategyPlanner | None = None,
    script_generation_agent: ScriptGenerationAgent | None = None,
    script_review_agent: ScriptReviewAgent | None = None,
    script_runner: ScriptRunner | None = None,
    result_verifier: ResultVerifier | None = None,
    experience_candidate_extractor: ExperienceCandidateExtractor | None = None,
    experience_generalization_gate: ExperienceGeneralizationGate | None = None,
    max_script_revisions: int = 2,
    max_execution_repairs: int = 1,
) -> Any:
    _ = (toolcall_registry, runtime_backends)
    understander = task_understanding_agent or TaskUnderstandingAgent()
    skill_provider = skill_context_provider or SkillContextProvider()
    planner = strategy_planner or ResearchStrategyPlanner()
    generator = script_generation_agent or ScriptGenerationAgent()
    reviewer = script_review_agent or ScriptReviewAgent()
    runner = script_runner or ScriptRunner()
    verifier = result_verifier or ResultVerifier()
    candidate_extractor = experience_candidate_extractor or ExperienceCandidateExtractor()
    generalization_gate = experience_generalization_gate or ExperienceGeneralizationGate()
    graph = StateGraph(ExecutionState)
    graph.add_node("receive_request", receive_request)
    graph.add_node(
        "understand_task",
        lambda state: understand_task(state, task_understanding_agent=understander),
    )
    graph.add_node(
        "project_runtime_context",
        lambda state: project_runtime_context(state, healthy_graph_store=healthy_graph_store),
    )
    graph.add_node("search_workflow_path", search_workflow_path)
    graph.add_node("detect_capability_gaps", detect_capability_gaps)
    graph.add_node("request_evolution", request_evolution)
    graph.add_node(
        "discover_runtime_capabilities",
        lambda state: discover_runtime_capabilities(
            state,
            runtime_discoverer=runtime_discoverer,
        ),
    )
    graph.add_node(
        "resolve_skill_context",
        lambda state: resolve_skill_context(state, skill_context_provider=skill_provider),
    )
    graph.add_node(
        "formulate_research_strategy",
        lambda state: formulate_research_strategy(state, strategy_planner=planner),
    )
    graph.add_node("verify_workflow", verify_workflow)
    graph.add_node(
        "generate_script",
        lambda state: generate_script(state, script_generation_agent=generator),
    )
    graph.add_node(
        "review_script",
        lambda state: review_script(
            state,
            script_review_agent=reviewer,
            max_script_revisions=max_script_revisions,
        ),
    )
    graph.add_node("permission_check", permission_check)
    graph.add_node(
        "execute_script",
        lambda state: execute_script(state, script_runner=runner),
    )
    graph.add_node("build_run_record", build_run_record)
    graph.add_node(
        "verify_results",
        lambda state: verify_results(state, result_verifier=verifier),
    )
    graph.add_node("finalize_run_record", finalize_run_record)
    graph.add_node(
        "extract_experience_candidate",
        lambda state: extract_experience_candidate(
            state,
            extractor=candidate_extractor,
            gate=generalization_gate,
        ),
    )
    graph.add_node("build_experience_patch", build_experience_patch)
    graph.add_node(
        "write_experience_patch",
        lambda state: write_experience_patch(
            state,
            full_graph_store=full_graph_store,
            healthy_graph_store=healthy_graph_store,
            apply_experience_patch=apply_experience_patch,
        ),
    )
    graph.add_node("produce_response", produce_response)

    graph.add_edge(START, "receive_request")
    graph.add_edge("receive_request", "understand_task")
    graph.add_edge("understand_task", "project_runtime_context")
    graph.add_edge("project_runtime_context", "search_workflow_path")
    graph.add_edge("search_workflow_path", "detect_capability_gaps")
    graph.add_edge("detect_capability_gaps", "request_evolution")
    graph.add_edge("request_evolution", "discover_runtime_capabilities")
    graph.add_edge("discover_runtime_capabilities", "resolve_skill_context")
    graph.add_edge("resolve_skill_context", "formulate_research_strategy")
    graph.add_edge("formulate_research_strategy", "verify_workflow")
    graph.add_edge("verify_workflow", "generate_script")
    graph.add_edge("generate_script", "review_script")
    graph.add_conditional_edges(
        "review_script",
        route_after_script_review,
        {
            "revise": "generate_script",
            "continue": "permission_check",
        },
    )
    graph.add_edge("permission_check", "execute_script")
    graph.add_edge("execute_script", "build_run_record")
    graph.add_edge("build_run_record", "verify_results")
    graph.add_conditional_edges(
        "verify_results",
        lambda state: route_after_result_verification(
            state,
            max_execution_repairs=max_execution_repairs,
        ),
        {
            "repair": "generate_script",
            "continue": "finalize_run_record",
        },
    )
    graph.add_edge("finalize_run_record", "extract_experience_candidate")
    graph.add_edge("extract_experience_candidate", "build_experience_patch")
    graph.add_edge("build_experience_patch", "write_experience_patch")
    graph.add_edge("write_experience_patch", "produce_response")
    graph.add_edge("produce_response", END)
    return graph.compile()


def run_execution(
    request: str,
    *,
    session_id: str | None = None,
    event_log: AgentEventLog | None = None,
    permission_mode: PermissionMode = "safe_execute",
    healthy_graph_store: HealthyGraphStore | None = None,
    full_graph_store: FullGraphStore | None = None,
    toolcall_registry: object | None = None,
    runtime_backends: object | None = None,
    runtime_discoverer: RuntimeCapabilityDiscoverer | None = None,
    apply_experience_patch: bool = True,
    task_understanding_agent: TaskUnderstandingAgent | None = None,
    skill_context_provider: SkillContextProvider | None = None,
    strategy_planner: ResearchStrategyPlanner | None = None,
    script_generation_agent: ScriptGenerationAgent | None = None,
    script_review_agent: ScriptReviewAgent | None = None,
    script_runner: ScriptRunner | None = None,
    result_verifier: ResultVerifier | None = None,
    experience_candidate_extractor: ExperienceCandidateExtractor | None = None,
    experience_generalization_gate: ExperienceGeneralizationGate | None = None,
    max_script_revisions: int = 2,
    max_execution_repairs: int = 1,
) -> ExecutionState:
    compiled = build_execution_graph(
        healthy_graph_store=healthy_graph_store,
        full_graph_store=full_graph_store,
        toolcall_registry=toolcall_registry,
        runtime_backends=runtime_backends,
        runtime_discoverer=runtime_discoverer,
        apply_experience_patch=apply_experience_patch,
        task_understanding_agent=task_understanding_agent,
        skill_context_provider=skill_context_provider,
        strategy_planner=strategy_planner,
        script_generation_agent=script_generation_agent,
        script_review_agent=script_review_agent,
        script_runner=script_runner,
        result_verifier=result_verifier,
        experience_candidate_extractor=experience_candidate_extractor,
        experience_generalization_gate=experience_generalization_gate,
        max_script_revisions=max_script_revisions,
        max_execution_repairs=max_execution_repairs,
    )
    initial_state: ExecutionState = {
        "request": request,
        "session_id": session_id or f"session-{uuid4()}",
        "permission_mode": permission_mode,
        "script_revision_count": 0,
        "execution_attempt_count": 0,
    }
    result = compiled.invoke(initial_state)
    final_state = cast(ExecutionState, result)
    if event_log is not None:
        append_execution_events(event_log, final_state)
    return final_state


def receive_request(state: ExecutionState) -> ExecutionState:
    return {**state, "status": "received"}


def understand_task(
    state: ExecutionState,
    *,
    task_understanding_agent: TaskUnderstandingAgent | None = None,
) -> ExecutionState:
    agent = task_understanding_agent or TaskUnderstandingAgent()
    fingerprint, research_task = agent.understand(
        state["request"],
        user_id="local",
        execution_intent="execute",
    )
    return {
        **state,
        "status": "task_understood",
        "task_fingerprint": fingerprint,
        "research_task": research_task,
    }


def fingerprint_task(state: ExecutionState) -> ExecutionState:
    fingerprint = TaskFingerprinter().fingerprint(
        state["request"],
        user_id="local",
        execution_intent="execute",
    )
    return {**state, "status": "fingerprinted", "task_fingerprint": fingerprint}


def project_runtime_context(
    state: ExecutionState,
    *,
    healthy_graph_store: HealthyGraphStore | None = None,
) -> ExecutionState:
    context = RuntimeViewProjector(healthy_graph_store=healthy_graph_store).project(
        state["task_fingerprint"]
    )
    return {**state, "status": "runtime_context_projected", "runtime_context": context}


def search_workflow_path(state: ExecutionState) -> ExecutionState:
    result = WorkflowPathSearch().search(state["task_fingerprint"], state["runtime_context"])
    return {**state, "status": "planning", "workflow_search_result": result}


def detect_capability_gaps(state: ExecutionState) -> ExecutionState:
    gaps = CapabilityGapDetector().detect(
        fingerprint=state["task_fingerprint"],
        runtime_context=state["runtime_context"],
        workflow_search_result=state["workflow_search_result"],
    )
    status = "capability_gap_detected" if gaps else state["status"]
    return {**state, "status": status, "capability_gaps": gaps}


def request_evolution(state: ExecutionState) -> ExecutionState:
    gaps = state.get("capability_gaps", [])
    if not gaps:
        return state
    source_event = AgentEvent(
        event_id=f"event-{uuid4()}",
        session_id=state["session_id"],
        event_type="CapabilityGapDetected",
        payload={"gap_ids": [gap.gap_id for gap in gaps]},
        provenance=[Provenance(source_type="execution_orchestrator")],
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


def discover_runtime_capabilities(
    state: ExecutionState,
    *,
    runtime_discoverer: RuntimeCapabilityDiscoverer | None = None,
) -> ExecutionState:
    search_result = state["workflow_search_result"]
    workflow_ready = search_result.selected_workflow_path_id is not None
    discoverer = runtime_discoverer or NoopRuntimeCapabilityDiscoverer()
    result = discoverer.discover(
        request=state["request"],
        fingerprint=state["task_fingerprint"],
        runtime_context=state["runtime_context"],
        workflow_search_result=search_result,
        capability_gaps=state.get("capability_gaps", []),
    )
    result = result.model_copy(
        update={"graph_patches": _normalize_runtime_graph_patches(result.graph_patches)}
    )
    update: ExecutionState = {
        **state,
        "runtime_discovery_result": result,
        "runtime_graph_patches": result.graph_patches,
    }
    if workflow_ready:
        return {**update, "status": state["status"]}
    if result.execution_plan is not None:
        return {
            **update,
            "status": "runtime_discovery_ready",
            "execution_plan": result.execution_plan,
        }
    return {**update, "status": "runtime_discovery_unavailable"}


def resolve_skill_context(
    state: ExecutionState,
    *,
    skill_context_provider: SkillContextProvider | None = None,
) -> ExecutionState:
    provider = skill_context_provider or SkillContextProvider()
    preferred_skill_ids: list[str] = []
    discovery = state.get("runtime_discovery_result")
    if discovery is not None and discovery.execution_plan is not None:
        preferred_skill_ids = [
            skill_id
            for step in discovery.execution_plan.steps
            for skill_id in step.candidate_skill_ids
        ]
    contexts = provider.resolve_skills_for_task(
        state["research_task"],
        state["runtime_context"],
        preferred_skill_ids=preferred_skill_ids,
    )
    return {**state, "status": "skill_context_resolved", "skill_contexts": contexts}


def formulate_research_strategy(
    state: ExecutionState,
    *,
    strategy_planner: ResearchStrategyPlanner | None = None,
) -> ExecutionState:
    discovery = state.get("runtime_discovery_result")
    if discovery is not None and discovery.execution_plan is not None:
        return {
            **state,
            "status": "execution_plan_compiled",
            "execution_plan": discovery.execution_plan,
        }
    planner = strategy_planner or ResearchStrategyPlanner()
    plan = planner.build(
        task=state["research_task"],
        fingerprint=state["task_fingerprint"],
        runtime_context=state["runtime_context"],
        search_result=state["workflow_search_result"],
        skill_contexts=state.get("skill_contexts", []),
    )
    return {**state, "status": "execution_plan_compiled", "execution_plan": plan}


def _normalize_runtime_graph_patches(patches: list[GraphPatch]) -> list[GraphPatch]:
    return [patch.model_copy(update=_normalized_patch_payload(patch)) for patch in patches]


def _normalized_patch_payload(patch: GraphPatch) -> dict[str, Any]:
    node_id_remap: dict[str, str] = {}
    nodes_to_add: list[dict[str, Any]] = []
    for node in patch.nodes_to_add:
        updated = dict(node)
        if (
            updated.get("layer") == "implementation"
            and updated.get("node_type") == "ToolImplementationProfile"
        ):
            old_id = str(updated.get("node_id", ""))
            new_id = old_id.replace("implementation-profile", "skill-tool-usage")
            updated["node_id"] = new_id
            updated["layer"] = "skill"
            updated["node_type"] = "ToolUsageSkill"
            updated["canonical_name"] = str(updated.get("canonical_name", "")).replace(
                "implementation profile",
                "usage skill",
            )
            attributes = dict(updated.get("attributes", {}))
            callability = attributes.pop("agent_callability", {})
            attributes["agent_readable_skill"] = (
                callability if isinstance(callability, dict) else {}
            )
            updated["attributes"] = attributes
            node_id_remap[old_id] = new_id
        nodes_to_add.append(updated)

    edges_to_add: list[dict[str, Any]] = []
    for edge in patch.edges_to_add:
        updated = dict(edge)
        if updated.get("edge_type") == "HAS_IMPLEMENTATION_PROFILE":
            updated["edge_type"] = "HAS_USAGE_SKILL"
        if updated.get("source_node_id") in node_id_remap:
            updated["source_node_id"] = node_id_remap[str(updated["source_node_id"])]
        if updated.get("target_node_id") in node_id_remap:
            updated["target_node_id"] = node_id_remap[str(updated["target_node_id"])]
        if updated.get("source_layer") == "implementation":
            updated["source_layer"] = "skill"
        if updated.get("target_layer") == "implementation":
            updated["target_layer"] = "skill"
        edges_to_add.append(updated)

    return {"nodes_to_add": nodes_to_add, "edges_to_add": edges_to_add}


def verify_workflow(state: ExecutionState) -> ExecutionState:
    report = WorkflowVerifier().verify(
        state["workflow_search_result"],
        state.get("execution_plan"),
    )
    return {**state, "status": "workflow_verified", "workflow_report": report}


def compile_execution_plan(state: ExecutionState) -> ExecutionState:
    report = state["workflow_report"]
    if report.status == "blocked":
        return {**state, "status": "execution_blocked", "execution_plan": None}

    if state.get("execution_plan") is not None:
        return {**state, "status": "execution_plan_compiled"}

    plan = AgenticExecutionPlanBuilder().build(
        fingerprint=state["task_fingerprint"],
        runtime_context=state["runtime_context"],
        search_result=state["workflow_search_result"],
    )
    if plan is None:
        blocked_report = WorkflowAuditReport(
            report_id=f"war-{uuid4()}",
            status="blocked",
            blockers=[
                Blocker(
                    code="AEP_NOT_GENERATED",
                    message=(
                        "Workflow verification passed, but no executable AEP could be compiled."
                    ),
                )
            ],
            provenance=[Provenance(source_type="execution_orchestrator")],
        )
        return {
            **state,
            "status": "execution_blocked",
            "workflow_report": blocked_report,
            "execution_plan": None,
        }
    return {**state, "status": "execution_plan_compiled", "execution_plan": plan}


def permission_check(state: ExecutionState) -> ExecutionState:
    decision = PermissionGate().check_execution(
        state["workflow_report"],
        mode=state["permission_mode"],
        execution_plan=state.get("execution_plan"),
        script_proposal=state.get("script_proposal"),
        script_review=state.get("script_review"),
    )
    return {**state, "permission_decision": decision}


def generate_script(
    state: ExecutionState,
    *,
    script_generation_agent: ScriptGenerationAgent | None = None,
) -> ExecutionState:
    plan = state.get("execution_plan")
    if plan is None:
        return {**state, "script_proposal": None}
    generator = script_generation_agent or ScriptGenerationAgent()
    previous_proposal = state.get("script_proposal")
    revision_count = state.get("script_revision_count", 0)
    if previous_proposal is not None:
        revision_count += 1
    try:
        proposal = generator.generate(
            request=state["request"],
            task=state["research_task"],
            plan=plan,
            runtime_context=state["runtime_context"],
            skill_contexts=state.get("skill_contexts", []),
            previous_review=state.get("script_review"),
            previous_execution=state.get("script_execution_result"),
        )
    except ScriptDraftError as error:
        return {
            **state,
            "status": "script_generation_blocked",
            "script_proposal": None,
            "script_generation_error": str(error),
            "script_revision_count": revision_count,
        }
    return {
        **state,
        "status": "script_generated",
        "script_proposal": proposal,
        "script_generation_error": None,
        "script_revision_count": revision_count,
    }


def review_script(
    state: ExecutionState,
    *,
    script_review_agent: ScriptReviewAgent | None = None,
    max_script_revisions: int = 2,
) -> ExecutionState:
    proposal = state.get("script_proposal")
    if proposal is None:
        return {**state, "script_review": None}
    review = (script_review_agent or ScriptReviewAgent()).review(proposal)
    if (
        review.status in {"needs_revision", "requires_revision"}
        and state.get("script_revision_count", 0) >= max_script_revisions
    ):
        review = review.model_copy(
            update={
                "status": "blocked",
                "blockers": [
                    *review.blockers,
                    f"script revision limit reached: {max_script_revisions}",
                ],
            }
        )
    status = (
        "script_reviewed"
        if review.approved
        else "script_needs_revision"
        if review.status in {"needs_revision", "requires_revision"}
        else "script_blocked"
    )
    if review.status == "blocked":
        blocked_report = WorkflowAuditReport(
            report_id=f"war-{uuid4()}",
            status="blocked",
            blockers=[
                Blocker(code="SCRIPT_REVIEW_BLOCKED", message=blocker)
                for blocker in review.blockers
            ],
            warnings=[],
            provenance=[Provenance(source_type="script_review_agent")],
        )
        return {
            **state,
            "status": status,
            "script_review": review,
            "workflow_report": blocked_report,
        }
    return {**state, "status": status, "script_review": review}


def route_after_script_review(state: ExecutionState) -> str:
    review = state.get("script_review")
    if review is not None and review.status in {"needs_revision", "requires_revision"}:
        return "revise"
    return "continue"


def execute_script(
    state: ExecutionState,
    *,
    script_runner: ScriptRunner | None = None,
) -> ExecutionState:
    decision = state["permission_decision"]
    proposal = state.get("script_proposal")
    review = state.get("script_review")
    if not decision.allowed or proposal is None or review is None or not review.approved:
        return {**state, "script_execution_result": None, "status": "execution_blocked"}

    result = (script_runner or ScriptRunner()).run(proposal)
    status = "executed" if result.status == "success" else "execution_failed"
    return {
        **state,
        "script_execution_result": result,
        "execution_attempt_count": state.get("execution_attempt_count", 0) + 1,
        "status": status,
    }


def execute_toolcalls(
    state: ExecutionState,
    *,
    toolcall_registry: object | None = None,
    runtime_backends: object | None = None,
) -> ExecutionState:
    _ = (toolcall_registry, runtime_backends)
    return execute_script(state)


def build_run_record(state: ExecutionState) -> ExecutionState:
    record, manifest = RunRecordBuilder().build(
        session_id=state["session_id"],
        request=state["request"],
        plan=state.get("execution_plan"),
        proposal=state.get("script_proposal"),
        execution=state.get("script_execution_result"),
    )
    execution = state.get("script_execution_result")
    status = (
        "executed"
        if execution is not None and execution.status == "success"
        else state["status"]
    )
    return {
        **state,
        "status": status,
        "run_record": record,
        "artifact_manifest": manifest,
    }


def verify_results(
    state: ExecutionState,
    *,
    result_verifier: ResultVerifier | None = None,
) -> ExecutionState:
    report = (result_verifier or ResultVerifier()).verify(
        plan=state.get("execution_plan"),
        proposal=state.get("script_proposal"),
        execution=state.get("script_execution_result"),
        manifest=state.get("artifact_manifest"),
    )
    status = "result_verified" if report.status == "completed" else "result_needs_repair"
    return {**state, "status": status, "result_verification": report}


def route_after_result_verification(
    state: ExecutionState,
    *,
    max_execution_repairs: int = 1,
) -> str:
    report = state.get("result_verification")
    if (
        report is not None
        and report.status == "repairable"
        and state.get("execution_attempt_count", 0) <= max_execution_repairs
        and state.get("script_proposal") is not None
    ):
        return "repair"
    return "continue"


def finalize_run_record(state: ExecutionState) -> ExecutionState:
    record = state.get("run_record")
    manifest = state.get("artifact_manifest")
    verification = state.get("result_verification")
    if record is None or verification is None:
        return state
    updated_record = record.model_copy(
        update={
            "result_summary": (
                "Task result verified."
                if verification.status == "completed"
                else "; ".join(verification.issues)
            ),
            "verification_status": verification.status,
            "status": (
                "success"
                if verification.status == "completed"
                else record.status
            ),
        }
    )
    updated_manifest = manifest
    if manifest is not None:
        updated_manifest = manifest.model_copy(
            update={
                "checks": [
                    *manifest.checks,
                    {
                        "name": "result_verification",
                        "status": verification.status,
                        "issues": verification.issues,
                        "missing_artifacts": verification.missing_artifacts,
                        "unverified_criteria": verification.unverified_criteria,
                    },
                ]
            }
        )
    return {
        **state,
        "run_record": updated_record,
        "artifact_manifest": updated_manifest,
        "status": "executed" if verification.status == "completed" else "execution_failed",
    }


def extract_experience_candidate(
    state: ExecutionState,
    *,
    extractor: ExperienceCandidateExtractor | None = None,
    gate: ExperienceGeneralizationGate | None = None,
) -> ExecutionState:
    record = state.get("run_record")
    verification = state.get("result_verification")
    task = state.get("research_task")
    if (
        record is None
        or verification is None
        or task is None
        or verification.status == "not_executed"
    ):
        return {
            **state,
            "experience_candidate": None,
            "experience_generalization": None,
        }
    candidate = (extractor or ExperienceCandidateExtractor()).extract(
        run_record=record,
        verification=verification,
        task=task,
    )
    decision = (gate or ExperienceGeneralizationGate()).evaluate(candidate)
    return {
        **state,
        "experience_candidate": candidate,
        "experience_generalization": decision,
    }


def build_experience_patch(state: ExecutionState) -> ExecutionState:
    candidate = state.get("experience_candidate")
    decision = state.get("experience_generalization")
    if candidate is None or decision is None or not decision.eligible:
        return {**state, "experience_patch": None}

    source_event = AgentEvent(
        event_id=f"event-{uuid4()}",
        session_id=state["session_id"],
        event_type="RunRecordCreated",
        payload={"candidate_id": candidate.candidate_id},
        provenance=[Provenance(source_type="execution_orchestrator")],
    )
    provenance = Provenance(
        source_type="execution_experience_distiller",
        source_id=candidate.candidate_id,
        metadata={"supporting_run_ids": candidate.supporting_run_ids},
    )
    patch = GraphPatch(
        patch_id=f"patch-{uuid4()}",
        source_event_ids=[source_event.event_id],
        source_module="ExecutionExperienceDistiller",
        provenance=provenance,
        approval_status="proposed",
    )
    node_type = (
        "SuccessPattern"
        if candidate.candidate_type == "success_pattern"
        else "FailureRecord"
    )
    node_id = f"experience-{node_type.lower()}-{candidate.candidate_id}"
    patch.nodes_to_add.append(
        {
            "node_id": node_id,
            "layer": "experience",
            "node_type": node_type,
            "canonical_name": candidate.summary,
            "attributes": {
                **candidate.model_dump(mode="json"),
                "generalization_scope": "task_and_skill_pattern",
            },
            "lifecycle_state": "candidate",
            "provenance": [provenance.model_dump(mode="json")],
        }
    )
    return {**state, "experience_patch": patch}


def write_experience_patch(
    state: ExecutionState,
    *,
    full_graph_store: FullGraphStore | None = None,
    healthy_graph_store: HealthyGraphStore | None = None,
    apply_experience_patch: bool = True,
) -> ExecutionState:
    experience_patch = state.get("experience_patch")
    patches = [*state.get("runtime_graph_patches", [])]
    if experience_patch is not None:
        patches.append(experience_patch)

    if not patches:
        return {
            **state,
            "experience_patch_audit": None,
            "graph_patch_audits": [],
            "graph_write_id": None,
            "graph_update_write_ids": [],
            "healthy_graph_write_id": None,
        }

    audits: list[PatchAuditReport] = []
    write_ids: list[str] = []
    written_patches: list[GraphPatch] = []
    experience_audit: PatchAuditReport | None = None
    auditor = GraphPatchAuditor()
    for patch in patches:
        audit = auditor.audit(patch)
        audits.append(audit)
        if experience_patch is not None and patch.patch_id == experience_patch.patch_id:
            experience_audit = audit
        if audit.status == "blocked" or full_graph_store is None or not apply_experience_patch:
            continue
        approved_patch = patch.model_copy(update={"approval_status": "approved"})
        write_ids.append(full_graph_store.apply_patch(approved_patch))
        written_patches.append(approved_patch)

    healthy_graph_write_id = _materialize_healthy_graph(
        healthy_graph_store=healthy_graph_store,
        written_patches=written_patches,
    )
    return {
        **state,
        "experience_patch_audit": experience_audit,
        "graph_patch_audits": audits,
        "graph_write_id": write_ids[-1] if write_ids else None,
        "graph_update_write_ids": write_ids,
        "healthy_graph_write_id": healthy_graph_write_id,
    }


def _materialize_healthy_graph(
    *,
    healthy_graph_store: HealthyGraphStore | None,
    written_patches: list[GraphPatch],
) -> str | None:
    if healthy_graph_store is None or not written_patches:
        return None
    materialize = getattr(healthy_graph_store, "materialize_from_patches", None)
    if materialize is None:
        return None

    report = MemoryHealthCompiler().compile(written_patches)
    if not report.materialized_l1:
        return None
    return str(materialize(report.g1_patches))


def produce_response(state: ExecutionState) -> ExecutionState:
    if state.get("execution_plan") is None:
        blockers = "; ".join(blocker.code for blocker in state["workflow_report"].blockers)
        return {**state, "response": f"Execution blocked: {blockers}"}

    generation_error = state.get("script_generation_error")
    if generation_error:
        return {
            **state,
            "response": f"Execution blocked during script generation: {generation_error}",
        }

    review = state.get("script_review")
    if review is not None and not review.approved:
        blockers = "; ".join(review.blockers)
        return {**state, "response": f"Script review blocked execution: {blockers}"}

    execution = state.get("script_execution_result")
    if execution is None:
        decision = state.get("permission_decision")
        blockers = "; ".join(decision.blocked_by) if decision is not None else ""
        return {**state, "response": f"Execution blocked: {blockers}"}
    verification = state.get("result_verification")
    if verification is not None and verification.status != "completed":
        issues = "; ".join(verification.issues or verification.missing_artifacts)
        return {
            **state,
            "response": (
                f"Script ran with status {execution.status}, but result verification "
                f"did not complete: {issues}"
            ),
        }
    return {
        **state,
        "response": "Script execution and result verification completed successfully.",
    }


def append_execution_events(event_log: AgentEventLog, state: ExecutionState) -> None:
    provenance = [Provenance(source_type="execution_orchestrator")]
    session_id = state["session_id"]
    _append(
        event_log,
        session_id,
        "UserRequestReceived",
        {"request": state["request"]},
        provenance,
    )
    _append(
        event_log,
        session_id,
        "TaskFingerprinted",
        state["task_fingerprint"].model_dump(mode="json"),
        provenance,
    )
    if state.get("research_task") is not None:
        _append(
            event_log,
            session_id,
            "TaskUnderstood",
            state["research_task"].model_dump(mode="json"),
            provenance,
        )
    _append(
        event_log,
        session_id,
        "RuntimeGraphContextProjected",
        state["runtime_context"].model_dump(mode="json"),
        provenance,
    )
    _append(
        event_log,
        session_id,
        "WorkflowPathSelected",
        state["workflow_search_result"].model_dump(mode="json"),
        provenance,
    )
    for gap in state.get("capability_gaps", []):
        _append(
            event_log,
            session_id,
            "CapabilityGapDetected",
            gap.model_dump(mode="json"),
            provenance,
        )
    if state.get("evolution_request") is not None:
        proposed_patch = state.get("proposed_evolution_patch")
        _append(
            event_log,
            session_id,
            "EvolutionRequested",
            state["evolution_request"].model_dump(mode="json"),
            provenance,
            graph_patch_ids=[proposed_patch.patch_id] if proposed_patch is not None else [],
        )
    if state.get("runtime_discovery_result") is not None:
        discovery = state["runtime_discovery_result"]
        _append(
            event_log,
            session_id,
            "RuntimeCapabilityDiscoveryCompleted",
            discovery.model_dump(mode="json"),
            provenance,
            graph_patch_ids=[patch.patch_id for patch in discovery.graph_patches],
        )
    if state.get("skill_contexts") is not None:
        _append(
            event_log,
            session_id,
            "SkillContextResolved",
            {
                "skill_ids": [
                    context.primary_skill.get("node_id")
                    for context in state["skill_contexts"]
                ]
            },
            provenance,
        )
    execution_plan = state.get("execution_plan")
    if execution_plan is not None:
        _append(
            event_log,
            session_id,
            "ResearchStrategyFormulated",
            execution_plan.model_dump(mode="json"),
            provenance,
        )
    _append(
        event_log,
        session_id,
        "WorkflowVerified",
        state["workflow_report"].model_dump(mode="json"),
        provenance,
    )
    _append(
        event_log,
        session_id,
        "PermissionChecked",
        state["permission_decision"].model_dump(mode="json"),
        provenance,
    )
    script_proposal = state.get("script_proposal")
    if script_proposal is not None:
        _append(
            event_log,
            session_id,
            "ScriptGenerated",
            script_proposal.model_dump(mode="json"),
            provenance,
        )
    script_review = state.get("script_review")
    if script_review is not None:
        _append(
            event_log,
            session_id,
            "ScriptReviewed",
            script_review.model_dump(mode="json"),
            provenance,
        )
    script_execution_result = state.get("script_execution_result")
    if script_execution_result is not None:
        _append(
            event_log,
            session_id,
            "ScriptExecuted",
            script_execution_result.model_dump(mode="json"),
            provenance,
        )
    run_record = state.get("run_record")
    if run_record is not None:
        _append(
            event_log,
            session_id,
            "RunRecordCreated",
            run_record.model_dump(mode="json"),
            provenance,
        )
    result_verification = state.get("result_verification")
    if result_verification is not None:
        _append(
            event_log,
            session_id,
            "ResultVerified",
            result_verification.model_dump(mode="json"),
            provenance,
        )
    experience_generalization = state.get("experience_generalization")
    if experience_generalization is not None:
        candidate = state.get("experience_candidate")
        _append(
            event_log,
            session_id,
            "ExperienceGeneralizationEvaluated",
            {
                "candidate_id": candidate.candidate_id if candidate is not None else None,
                **experience_generalization.model_dump(mode="json"),
            },
            provenance,
        )
    patch = state.get("experience_patch")
    if patch is not None:
        l6_node_ids = [
            str(node["node_id"])
            for node in patch.nodes_to_add
            if node.get("layer") == "experience" and "node_id" in node
        ]
        _append(
            event_log,
            session_id,
            "ExperienceCandidateCreated",
            {"patch_id": patch.patch_id},
            provenance,
            graph_patch_ids=[patch.patch_id],
            l6_node_ids=l6_node_ids,
        )
        _append(
            event_log,
            session_id,
            "GraphPatchProposed",
            patch.model_dump(mode="json"),
            provenance,
            graph_patch_ids=[patch.patch_id],
            l6_node_ids=l6_node_ids,
        )
    if state.get("graph_write_id") is not None and patch is not None:
        _append(
            event_log,
            session_id,
            "GraphPatchWritten",
            {"patch_id": patch.patch_id, "write_id": state["graph_write_id"]},
            provenance,
            graph_patch_ids=[patch.patch_id],
        )


def _append(
    event_log: AgentEventLog,
    session_id: str,
    event_type: AgentEventType,
    payload: dict[str, Any],
    provenance: list[Provenance],
    *,
    graph_patch_ids: list[str] | None = None,
    l6_node_ids: list[str] | None = None,
) -> None:
    event_log.append(
        AgentEvent(
            event_id=f"event-{uuid4()}",
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            provenance=provenance,
            graph_patch_ids=graph_patch_ids or [],
            l6_node_ids=l6_node_ids or [],
        )
    )
