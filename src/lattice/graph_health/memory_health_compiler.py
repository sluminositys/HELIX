from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from lattice.graph import GraphTierPolicy
from lattice.schemas import GraphPatch, LatticeBaseModel


class MemoryHealthCompileReport(LatticeBaseModel):
    report_id: str
    status: Literal["completed", "skipped"]
    compiled_patch_ids: list[str] = Field(default_factory=list)
    materialized_l1: bool = False
    eligible_patch_ids: list[str] = Field(default_factory=list)
    excluded_patch_reasons: dict[str, list[str]] = Field(default_factory=dict)
    g1_patches: list[GraphPatch] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryHealthCompiler:
    def __init__(self, graph_tier_policy: GraphTierPolicy | None = None) -> None:
        self.graph_tier_policy = graph_tier_policy or GraphTierPolicy()

    def compile(self, patches: Iterable[GraphPatch]) -> MemoryHealthCompileReport:
        patch_list = list(patches)
        if not patch_list:
            return MemoryHealthCompileReport(
                report_id="mhc-skipped-no-patches",
                status="skipped",
            )

        for patch in patch_list:
            self.graph_tier_policy.assert_patch_targets_l0(patch)

        g1_patches: list[GraphPatch] = []
        excluded: dict[str, list[str]] = {}
        for patch in patch_list:
            compiled, reasons = _compile_patch(patch)
            if compiled is None:
                excluded[patch.patch_id] = reasons
            else:
                g1_patches.append(compiled)

        return MemoryHealthCompileReport(
            report_id="mhc-completed",
            status="completed",
            compiled_patch_ids=[patch.patch_id for patch in patch_list],
            materialized_l1=bool(g1_patches),
            eligible_patch_ids=[patch.patch_id.removesuffix("-g1") for patch in g1_patches],
            excluded_patch_reasons=excluded,
            g1_patches=g1_patches,
        )


def _compile_patch(patch: GraphPatch) -> tuple[GraphPatch | None, list[str]]:
    healthy_states = {"active_hot", "active_warm"}
    nodes_to_add = [
        node for node in patch.nodes_to_add if node.get("lifecycle_state") in healthy_states
    ]
    nodes_to_update = [
        node for node in patch.nodes_to_update if node.get("lifecycle_state") in healthy_states
    ]
    edges_to_add = [
        edge
        for edge in patch.edges_to_add
        if edge.get("lifecycle_state") in healthy_states
    ]
    edges_to_update = [
        edge
        for edge in patch.edges_to_update
        if edge.get("lifecycle_state") in healthy_states
    ]
    if not any((nodes_to_add, nodes_to_update, edges_to_add, edges_to_update)):
        return None, ["patch contains no active_hot or active_warm graph mutations"]
    return (
        patch.model_copy(
            update={
                "patch_id": f"{patch.patch_id}-g1",
                "target_graph_tier": "G1",
                "source_module": "MemoryHealthCompiler",
                "approval_status": "approved",
                "nodes_to_add": nodes_to_add,
                "nodes_to_update": nodes_to_update,
                "edges_to_add": edges_to_add,
                "edges_to_update": edges_to_update,
            }
        ),
        [],
    )
