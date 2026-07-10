from __future__ import annotations

from uuid import uuid4

from lattice.planning.execution_plan_builder import AgenticExecutionPlanBuilder
from lattice.planning.workflow_path_search import WorkflowSearchResult
from lattice.schemas import (
    AgenticExecutionPlan,
    AgenticExecutionStep,
    Provenance,
    ResearchTask,
    RuntimeGraphContext,
    TaskFingerprint,
)
from lattice.skill import SkillContext


class ResearchStrategyPlanner:
    """Compile a task strategy while treating G2 workflows and skills as references."""

    def build(
        self,
        *,
        task: ResearchTask,
        fingerprint: TaskFingerprint,
        runtime_context: RuntimeGraphContext,
        search_result: WorkflowSearchResult,
        skill_contexts: list[SkillContext],
    ) -> AgenticExecutionPlan:
        graph_plan = AgenticExecutionPlanBuilder().build(
            fingerprint=fingerprint,
            runtime_context=runtime_context,
            search_result=search_result,
        )
        if graph_plan is not None:
            return graph_plan.model_copy(
                update={
                    "strategy_summary": (
                        "Adapt the highest-ranked G2 workflow reference to the current "
                        "research task."
                    )
                }
            )

        skill_ids = [
            str(context.primary_skill.get("node_id"))
            for context in skill_contexts
            if context.primary_skill.get("node_id")
        ]
        resource_ids = [
            str(resource.get("node_id"))
            for context in skill_contexts
            for resource in context.related_resource_nodes
            if resource.get("node_id")
        ]
        step = AgenticExecutionStep(
            step_id=f"dynamic-step-{uuid4()}",
            objective=task.user_goal,
            candidate_skill_ids=list(dict.fromkeys(skill_ids)),
            candidate_resource_ids=list(dict.fromkeys(resource_ids)),
            input_artifacts=task.input_artifacts,
            expected_outputs=task.output_goals,
            constraints=task.constraints,
            success_criteria=task.success_criteria,
            script_requirements=[
                "use only declared inputs and an isolated task working directory",
                "write inspectable artifacts and preserve stdout/stderr",
                "fail explicitly when required data or capabilities are missing",
            ],
            permission_requirements={
                "network": False,
                "shell": bool(resource_ids),
                "write_workspace": True,
            },
        )
        return AgenticExecutionPlan(
            plan_id=f"aep-{uuid4()}",
            task_fingerprint_id=fingerprint.fingerprint_id,
            runtime_graph_context_id=runtime_context.graph_context_id,
            selected_workflow_path_id=search_result.selected_workflow_path_id,
            strategy_summary=(
                "Create a task-specific execution strategy. G2 paths and skills are references, "
                "not mandatory execution contracts."
            ),
            steps=[step],
            provenance=[Provenance(source_type="research_strategy_planner")],
        )
