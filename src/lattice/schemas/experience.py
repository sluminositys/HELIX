from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from lattice.schemas.common import LatticeBaseModel, LifecycleState, Provenance


class ExperienceCandidate(LatticeBaseModel):
    candidate_id: str
    candidate_type: Literal[
        "constraint",
        "repair_action",
        "workflow_pattern",
        "quality_signal",
        "method_comparison",
        "success_pattern",
        "failure_pattern",
        "workflow_insight",
        "task_constraint",
        "domain_heuristic",
        "skill_update",
        "resource_discovery",
        "workflow_update",
    ]
    summary: str = ""
    trigger_conditions: list[str] = Field(default_factory=list)
    applicable_task_tags: list[str] = Field(default_factory=list)
    applicable_method_tags: list[str] = Field(default_factory=list)
    applicable_tool_names: list[str] = Field(default_factory=list)
    supporting_run_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    occurrence_count: int = 1
    generality: Literal["single_observation", "likely_general", "general"] = (
        "single_observation"
    )
    confidence: float = 0.0
    contradiction_refs: list[str] = Field(default_factory=list)
    proposed_target_layers: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    trigger_condition: dict[str, Any] = Field(default_factory=dict)
    proposed_graph_patch_id: str | None = None
    scope: Literal["user", "lab", "project", "global"] = "global"
    confidence_state: Literal["raw", "reviewed", "approved", "rejected"] = "raw"


class Constraint(LatticeBaseModel):
    constraint_id: str
    type: str
    subject: str
    relation: str
    object: str
    trigger_condition: dict[str, Any] = Field(default_factory=dict)
    applies_to_layers: list[str] = Field(default_factory=list)
    severity: Literal["blocker", "warning", "info"]
    repair_hint: str
    provenance: Provenance
    lifecycle_state: LifecycleState = "candidate"


class CapabilityGap(LatticeBaseModel):
    gap_id: str
    task_fingerprint_id: str
    runtime_graph_context_id: str | None = None
    gap_type: Literal["workflow", "tool", "skill", "runtime_capability", "evidence", "data"]
    missing_requirements: list[str] = Field(default_factory=list)
    trigger_condition: dict[str, Any] = Field(default_factory=dict)
    suggested_discovery_queries: list[str] = Field(default_factory=list)
    provenance: Provenance
    lifecycle_state: LifecycleState = "candidate"
