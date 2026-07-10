from __future__ import annotations

from pydantic import Field

from lattice.schemas import (
    AgenticExecutionPlan,
    LatticeBaseModel,
    PermissionMode,
    ScriptProposal,
    ScriptReviewResult,
    WorkflowAuditReport,
)


class PermissionDecision(LatticeBaseModel):
    allowed: bool
    mode: PermissionMode
    reason: str
    blocked_by: list[str] = Field(default_factory=list)


class PermissionGate:
    def check_execution(
        self,
        workflow_report: WorkflowAuditReport,
        *,
        mode: PermissionMode = "plan_only",
        execution_plan: AgenticExecutionPlan | None = None,
        script_proposal: ScriptProposal | None = None,
        script_review: ScriptReviewResult | None = None,
    ) -> PermissionDecision:
        if workflow_report.status == "blocked":
            return PermissionDecision(
                allowed=False,
                mode=mode,
                reason="workflow verification blocked execution",
                blocked_by=[blocker.code for blocker in workflow_report.blockers],
            )

        if mode in {"plan_only", "read_only"}:
            return PermissionDecision(
                allowed=False,
                mode=mode,
                reason=f"{mode} mode does not allow script execution",
                blocked_by=[f"{mode.upper()}_MODE"],
            )

        if mode == "ask_before_execute":
            return PermissionDecision(
                allowed=False,
                mode=mode,
                reason="ask_before_execute requires an explicit external approval decision",
                blocked_by=["EXTERNAL_APPROVAL_REQUIRED"],
            )

        if execution_plan is None or not execution_plan.steps:
            return PermissionDecision(
                allowed=False,
                mode=mode,
                reason="no execution plan is available",
                blocked_by=["EXECUTION_PLAN_REQUIRED"],
            )

        if script_proposal is None or script_review is None or not script_review.approved:
            return PermissionDecision(
                allowed=False,
                mode=mode,
                reason="an approved script proposal is required",
                blocked_by=["APPROVED_SCRIPT_REQUIRED"],
            )

        requirements = script_proposal.permission_requirements
        if requirements.get("admin") and mode != "admin_approved_execute":
            return PermissionDecision(
                allowed=False,
                mode=mode,
                reason="the script requests administrator privileges",
                blocked_by=["ADMIN_APPROVAL_REQUIRED"],
            )

        return PermissionDecision(
            allowed=True,
            mode=mode,
            reason="permission checks passed",
        )
