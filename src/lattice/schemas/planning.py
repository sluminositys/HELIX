from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from lattice.schemas.common import LatticeBaseModel, Provenance

PlanStatus = Literal["planned", "verified", "executing", "completed", "failed", "blocked"]


class AgenticExecutionStep(LatticeBaseModel):
    step_id: str
    objective: str | None = None
    workflow_step_id: str | None = None
    candidate_skill_ids: list[str] = Field(default_factory=list)
    candidate_resource_ids: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    script_requirements: list[str] = Field(default_factory=list)
    permission_requirements: dict[str, Any] = Field(default_factory=dict)

    # Compatibility fields for the retired ToolCall execution path. The main agent
    # no longer uses these fields to decide whether a step is executable.
    skill_ids: list[str] = Field(default_factory=list)
    suggested_tool_names: list[str] = Field(default_factory=list)
    script_goal: str | None = None
    input_bindings: dict[str, Any] = Field(default_factory=dict)
    parameter_bindings: dict[str, Any] = Field(default_factory=dict)
    parameter_sources: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    permission_requirement: dict[str, Any] = Field(default_factory=dict)
    failure_policy: dict[str, Any] = Field(default_factory=dict)
    quality_checks: list[str] = Field(default_factory=list)
    artifact_expectations: list[str] = Field(default_factory=list)
    toolcall_spec_id: str | None = None
    observation_schema: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_reference_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        candidate_skill_ids = list(data.get("candidate_skill_ids") or [])
        skill_ids = list(data.get("skill_ids") or [])
        if not candidate_skill_ids and skill_ids:
            data["candidate_skill_ids"] = skill_ids
        if not skill_ids and candidate_skill_ids:
            data["skill_ids"] = candidate_skill_ids
        objective = (
            data.get("objective")
            or data.get("script_goal")
            or data.get("workflow_step_id")
            or data.get("step_id")
        )
        data["objective"] = objective
        data.setdefault("script_goal", objective)
        expected_outputs = list(data.get("expected_outputs") or [])
        artifact_expectations = list(data.get("artifact_expectations") or [])
        if not expected_outputs and artifact_expectations:
            data["expected_outputs"] = artifact_expectations
        if not artifact_expectations and expected_outputs:
            data["artifact_expectations"] = expected_outputs
        if not data.get("success_criteria"):
            data["success_criteria"] = [
                *list(data.get("postconditions") or []),
                *list(data.get("quality_checks") or []),
            ]
        permission_requirements = dict(data.get("permission_requirements") or {})
        permission_requirement = dict(data.get("permission_requirement") or {})
        if not permission_requirements and permission_requirement:
            data["permission_requirements"] = permission_requirement
        if not permission_requirement and permission_requirements:
            data["permission_requirement"] = permission_requirements
        return data


class AgenticExecutionPlan(LatticeBaseModel):
    plan_id: str
    task_fingerprint_id: str
    runtime_graph_context_id: str
    selected_workflow_path_id: str | None = None
    strategy_summary: str = ""
    status: PlanStatus = "planned"
    steps: list[AgenticExecutionStep] = Field(default_factory=list)
    script_strategy: str | None = None
    verification_report_id: str | None = None
    provenance: list[Provenance] = Field(default_factory=list)
