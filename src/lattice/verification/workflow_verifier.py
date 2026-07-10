from __future__ import annotations

from uuid import uuid4

from lattice.planning import WorkflowSearchResult
from lattice.schemas import AgenticExecutionPlan, Blocker, WarningItem, WorkflowAuditReport


class WorkflowVerifier:
    def verify(
        self,
        search_result: WorkflowSearchResult,
        execution_plan: AgenticExecutionPlan | None = None,
    ) -> WorkflowAuditReport:
        blockers: list[Blocker] = []
        if (
            search_result.selected_workflow_path_id is None
            and (execution_plan is None or not execution_plan.steps)
        ):
            blockers.append(
                Blocker(
                    code="NO_WORKFLOW_PATH",
                    message=(
                        "G2 has no workflow reference and no task-specific execution "
                        "strategy was generated."
                    ),
                )
            )

        if any("executable steps" in item for item in search_result.unresolved_requirements):
            blockers.append(
                Blocker(
                    code="NO_EXECUTABLE_WORKFLOW_STEPS",
                    message="The selected workflow path has no executable step sequence.",
                )
            )
        remaining_unresolved = [
            item
            for item in search_result.unresolved_requirements
            if "executable steps" not in item
        ]
        if (
            remaining_unresolved
            and search_result.selected_workflow_path_id is not None
            and (execution_plan is None or not execution_plan.steps)
        ):
            blockers.append(
                Blocker(
                    code="UNRESOLVED_WORKFLOW_REQUIREMENTS",
                    message="Workflow path search returned unresolved requirements.",
                )
            )

        if blockers:
            return WorkflowAuditReport(
                report_id=f"war-{uuid4()}",
                status="blocked",
                blockers=blockers,
                unresolved_items=search_result.unresolved_requirements,
            )

        warnings = []
        if search_result.selected_workflow_path_id is None and execution_plan is not None:
            warnings.append(
                WarningItem(
                    code="DYNAMIC_STRATEGY_WITHOUT_G2_PATH",
                    message=(
                        "The plan was generated from the task and available references without "
                        "treating a G2 workflow as mandatory."
                    ),
                )
            )
        return WorkflowAuditReport(
            report_id=f"war-{uuid4()}",
            status="warning" if warnings else "pass",
            warnings=warnings,
        )
