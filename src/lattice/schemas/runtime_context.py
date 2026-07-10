from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from lattice.schemas.common import LatticeBaseModel, Provenance


class RuntimeLayerView(LatticeBaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    role: str | None = None
    profile_id: str | None = None
    mode: str | None = None
    task: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.metadata[key]

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            value = getattr(self, key)
            return default if value is None else value
        return self.metadata.get(key, default)


class GraphContextSufficiencyReport(LatticeBaseModel):
    report_id: str
    status: Literal["sufficient", "insufficient", "sufficient_with_warnings"]
    missing_task_info: list[str] = Field(default_factory=list)
    missing_workflow_info: list[str] = Field(default_factory=list)
    missing_resource_info: list[str] = Field(default_factory=list)
    missing_skill_info: list[str] = Field(default_factory=list)
    missing_evidence_info: list[str] = Field(default_factory=list)
    missing_experience_info: list[str] = Field(default_factory=list)
    controlled_recall_required: bool = False
    controlled_recall_reason: str | None = None
    runtime_discovery_required: bool = False
    runtime_discovery_queries: list[str] = Field(default_factory=list)


class RuntimeGraphContext(LatticeBaseModel):
    graph_context_id: str
    task_fingerprint_id: str
    source_graph_tier: Literal["G1", "G1_plus_controlled_G0_recall"]
    G_task: RuntimeLayerView = Field(default_factory=RuntimeLayerView)
    G_evidence: RuntimeLayerView = Field(default_factory=RuntimeLayerView)
    G_workflow: RuntimeLayerView = Field(default_factory=RuntimeLayerView)
    G_resource: RuntimeLayerView = Field(default_factory=RuntimeLayerView)
    G_skill: RuntimeLayerView = Field(default_factory=RuntimeLayerView)
    G_experience: RuntimeLayerView = Field(default_factory=RuntimeLayerView)
    cross_layer_edges: list[dict[str, Any]] = Field(default_factory=list)
    repair_advice_view: dict[str, Any] = Field(default_factory=dict)
    quality_checkpoint_view: dict[str, Any] = Field(default_factory=dict)
    temporary_candidates: list[dict[str, Any]] = Field(default_factory=list)
    sufficiency_report: GraphContextSufficiencyReport
    provenance: list[Provenance] = Field(default_factory=list)
