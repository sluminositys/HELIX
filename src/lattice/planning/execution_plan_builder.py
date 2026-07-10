from __future__ import annotations

from typing import Any
from uuid import uuid4

from lattice.planning.workflow_path_search import (
    WorkflowSearchResult,
    get_workflow_steps_for_selected_path,
)
from lattice.schemas import (
    AgenticExecutionPlan,
    AgenticExecutionStep,
    Provenance,
    RuntimeGraphContext,
    TaskFingerprint,
)


class AgenticExecutionPlanBuilder:
    def build(
        self,
        *,
        fingerprint: TaskFingerprint,
        runtime_context: RuntimeGraphContext,
        search_result: WorkflowSearchResult,
    ) -> AgenticExecutionPlan | None:
        selected_path_id = search_result.selected_workflow_path_id
        if selected_path_id is None or search_result.unresolved_requirements:
            return None

        steps = [
            _build_execution_step(raw_step)
            for raw_step in get_workflow_steps_for_selected_path(runtime_context, selected_path_id)
        ]
        if not steps:
            return None

        return AgenticExecutionPlan(
            plan_id=f"aep-{uuid4()}",
            task_fingerprint_id=fingerprint.fingerprint_id,
            runtime_graph_context_id=runtime_context.graph_context_id,
            selected_workflow_path_id=selected_path_id,
            steps=steps,
            provenance=[Provenance(source_type="agentic_execution_plan_builder")],
        )


def _build_execution_step(raw_step: dict[str, Any]) -> AgenticExecutionStep:
    attributes = raw_step.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}

    step_id = str(attributes.get("step_id") or raw_step.get("node_id") or f"step-{uuid4()}")
    workflow_step_id = str(raw_step.get("node_id") or step_id)
    return AgenticExecutionStep(
        step_id=step_id,
        objective=_optional_string(
            attributes.get("objective")
            or attributes.get("script_goal")
            or attributes.get("goal")
            or attributes.get("description")
            or raw_step.get("canonical_name")
        ),
        workflow_step_id=workflow_step_id,
        candidate_skill_ids=_string_list(attributes.get("skill_ids")),
        candidate_resource_ids=_string_list(attributes.get("resource_ids")),
        input_artifacts=_string_list(attributes.get("input_artifacts")),
        expected_outputs=_string_list(
            attributes.get("expected_outputs") or attributes.get("artifact_expectations")
        ),
        constraints=_string_list(attributes.get("constraints")),
        success_criteria=_string_list(
            attributes.get("success_criteria") or attributes.get("quality_checks")
        ),
        script_requirements=_string_list(attributes.get("script_requirements")),
        permission_requirements=_dict(
            attributes.get("permission_requirements")
            or attributes.get("permission_requirement")
        ),
        skill_ids=_string_list(attributes.get("skill_ids")),
        suggested_tool_names=_string_list(attributes.get("suggested_tool_names")),
        script_goal=_optional_string(
            attributes.get("script_goal")
            or attributes.get("goal")
            or attributes.get("description")
            or raw_step.get("canonical_name")
        ),
        input_bindings=_dict(attributes.get("input_bindings")),
        parameter_bindings=_dict(attributes.get("parameter_bindings")),
        parameter_sources=_dict(attributes.get("parameter_sources")),
        preconditions=_string_list(attributes.get("preconditions")),
        postconditions=_string_list(attributes.get("postconditions")),
        permission_requirement=_dict(attributes.get("permission_requirement")),
        failure_policy=_dict(attributes.get("failure_policy")),
        quality_checks=_string_list(attributes.get("quality_checks")),
        artifact_expectations=_string_list(attributes.get("artifact_expectations")),
        toolcall_spec_id=_optional_string(attributes.get("toolcall_spec_id")),
        observation_schema=_dict(attributes.get("observation_schema")),
    )


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
