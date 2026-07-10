from __future__ import annotations

from typing import Any

from pydantic import Field

from lattice.schemas import LatticeBaseModel, RuntimeGraphContext, RuntimeLayerView, TaskFingerprint


class WorkflowSearchResult(LatticeBaseModel):
    candidate_path_ids: list[str] = Field(default_factory=list)
    selected_workflow_path_id: str | None = None
    rejected_path_ids: list[str] = Field(default_factory=list)
    path_rationale: list[str] = Field(default_factory=list)
    unresolved_requirements: list[str] = Field(default_factory=list)


class WorkflowPathSearch:
    def search(
        self,
        fingerprint: TaskFingerprint,
        runtime_context: RuntimeGraphContext,
    ) -> WorkflowSearchResult:
        report = runtime_context.sufficiency_report
        if report.status == "insufficient":
            return WorkflowSearchResult(
                unresolved_requirements=[
                    *report.missing_task_info,
                    *report.missing_workflow_info,
                    *report.missing_skill_info,
                    *report.missing_evidence_info,
                    *report.missing_experience_info,
                ],
                path_rationale=[
                    "RuntimeGraphContext is insufficient; execution may need runtime discovery."
                ],
            )

        workflow_nodes = _nodes(runtime_context.G_workflow)
        candidate_paths = [
            node
            for node in workflow_nodes
            if node.get("node_type") in {"WorkflowPath", "WorkflowTemplate"}
            and node.get("lifecycle_state") in {"active_hot", "active_warm"}
        ]
        if not candidate_paths:
            return WorkflowSearchResult(
                unresolved_requirements=["no active workflow path nodes projected from L1"],
                path_rationale=["L2 workflow view does not contain an active workflow path."],
            )

        selected = _rank_candidate_paths(candidate_paths)[0]
        selected_id = str(selected["node_id"])
        steps = _steps_for_path(selected, workflow_nodes)
        unresolved: list[str] = []
        if not steps:
            unresolved.append(f"workflow path has no executable steps: {selected_id}")
        missing_skill_steps = []
        for step in steps:
            attributes = _attributes(step)
            if not attributes.get("skill_ids") and not attributes.get("suggested_tool_names"):
                missing_skill_steps.append(str(step.get("node_id", "unknown")))

        return WorkflowSearchResult(
            candidate_path_ids=[str(node["node_id"]) for node in candidate_paths],
            selected_workflow_path_id=selected_id,
            rejected_path_ids=[
                str(node["node_id"])
                for node in candidate_paths
                if node.get("node_id") != selected_id
            ],
            unresolved_requirements=unresolved,
            path_rationale=[
                "Selected the highest-priority active workflow path from L2.",
                f"Task fingerprint: {fingerprint.fingerprint_id}",
                *[
                    "Workflow step has no projected L5 skill and will rely on runtime discovery: "
                    f"{step_id}"
                    for step_id in missing_skill_steps
                ],
            ],
        )


def _nodes(view: RuntimeLayerView | dict[str, Any]) -> list[dict[str, Any]]:
    raw_nodes = view.get("nodes", [])
    if not isinstance(raw_nodes, list):
        return []
    return [node for node in raw_nodes if isinstance(node, dict)]


def _attributes(node: dict[str, Any]) -> dict[str, Any]:
    attributes = node.get("attributes", {})
    if isinstance(attributes, dict):
        return attributes
    return {}


def _rank_candidate_paths(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(paths, key=lambda node: (_priority(node), str(node.get("node_id", ""))))


def _priority(node: dict[str, Any]) -> int:
    attributes = _attributes(node)
    raw_priority = attributes.get("priority", 100)
    if isinstance(raw_priority, int):
        return raw_priority
    if isinstance(raw_priority, str) and raw_priority.isdecimal():
        return int(raw_priority)
    return 100


def _steps_for_path(
    selected_path: dict[str, Any],
    workflow_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    attributes = _attributes(selected_path)
    embedded_steps = attributes.get("steps")
    if isinstance(embedded_steps, list) and embedded_steps:
        return [step for step in embedded_steps if isinstance(step, dict)]

    step_ids = attributes.get("step_ids")
    if isinstance(step_ids, list) and step_ids:
        wanted = {str(step_id) for step_id in step_ids}
        return sorted(
            [node for node in workflow_nodes if str(node.get("node_id")) in wanted],
            key=lambda node: (_step_order(node), str(node.get("node_id", ""))),
        )

    selected_id = selected_path.get("node_id")
    step_types = {"WorkflowStep", "QCStep", "AnalysisStep", "ValidationStep", "InterpretationStep"}
    return sorted(
        [
            node
            for node in workflow_nodes
            if node.get("node_type") in step_types
            and _attributes(node).get("workflow_path_id") == selected_id
        ],
        key=lambda node: (_step_order(node), str(node.get("node_id", ""))),
    )


def _step_order(node: dict[str, Any]) -> int:
    attributes = _attributes(node)
    raw_order = attributes.get("order", attributes.get("step_order", 1000))
    if isinstance(raw_order, int):
        return raw_order
    if isinstance(raw_order, str) and raw_order.isdecimal():
        return int(raw_order)
    return 1000


def get_workflow_steps_for_selected_path(
    runtime_context: RuntimeGraphContext,
    selected_workflow_path_id: str,
) -> list[dict[str, Any]]:
    workflow_nodes = _nodes(runtime_context.G_workflow)
    for node in workflow_nodes:
        if node.get("node_id") == selected_workflow_path_id:
            return _steps_for_path(node, workflow_nodes)
    return []


def get_runtime_nodes(view: dict[str, Any]) -> list[dict[str, Any]]:
    return _nodes(view)
