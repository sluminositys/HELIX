from __future__ import annotations

from uuid import uuid4

from lattice.graph import HealthyGraphStore
from lattice.schemas import (
    GraphContextSufficiencyReport,
    RuntimeGraphContext,
    RuntimeLayerView,
    TaskFingerprint,
)


class RuntimeViewProjector:
    def __init__(self, healthy_graph_store: HealthyGraphStore | None = None) -> None:
        self.healthy_graph_store = healthy_graph_store

    def project(self, fingerprint: TaskFingerprint) -> RuntimeGraphContext:
        if self.healthy_graph_store is not None:
            return self.healthy_graph_store.project_runtime_context(fingerprint)

        report = GraphContextSufficiencyReport(
            report_id=f"gcsr-{uuid4()}",
            status="insufficient",
            missing_workflow_info=["no healthy graph store is configured"],
            missing_skill_info=["no active L5 skill view has been projected"],
            missing_evidence_info=["no evidence view has been projected"],
            missing_experience_info=["no reusable L6 experience view has been projected"],
            controlled_recall_required=False,
            runtime_discovery_required=True,
            runtime_discovery_queries=[fingerprint.task],
        )
        return RuntimeGraphContext(
            graph_context_id=f"rgc-{uuid4()}",
            task_fingerprint_id=fingerprint.fingerprint_id,
            source_graph_tier="G1",
            G_skill=RuntimeLayerView(role="agent-readable skill reference"),
            G_experience=RuntimeLayerView(role="generalized experience reference"),
            repair_advice_view={"items": []},
            quality_checkpoint_view={"items": []},
            sufficiency_report=report,
        )
