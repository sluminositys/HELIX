from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from lattice.schemas import (
    BioEvoKGEdge,
    BioEvoKGGraphRecords,
    BioEvoKGNode,
    GraphContextSufficiencyReport,
    GraphPatch,
    GraphProfile,
    PackagedDemoGraphManifest,
    Provenance,
    RuntimeGraphContext,
    RuntimeLayerView,
    TaskFingerprint,
)


class PackagedGraphStoreError(ValueError):
    pass


class PackagedFullGraphStore:
    def __init__(
        self,
        *,
        profile: GraphProfile,
        nodes: list[BioEvoKGNode],
        edges: list[BioEvoKGEdge],
    ) -> None:
        self.profile = profile
        self.nodes = [node.model_dump(mode="json") for node in nodes]
        self.edges = [edge.model_dump(mode="json") for edge in edges]
        self._nodes_by_id = _index_nodes(nodes)

    def apply_patch(self, patch: GraphPatch) -> str:
        msg = f"Packaged graph profile is read-only: {self.profile.profile_id}"
        raise PackagedGraphStoreError(msg)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes_by_id.get(node_id)


class PackagedHealthyGraphStore:
    def __init__(
        self,
        *,
        profile: GraphProfile,
        nodes: list[BioEvoKGNode],
        edges: list[BioEvoKGEdge],
    ) -> None:
        self.profile = profile
        self.nodes = [node.model_dump(mode="json") for node in nodes]
        self.edges = [edge.model_dump(mode="json") for edge in edges]
        self._nodes_by_id = _index_nodes(nodes)

    def project_runtime_context(self, fingerprint: TaskFingerprint) -> RuntimeGraphContext:
        views = _split_runtime_views(self.nodes, self.edges)
        report = GraphContextSufficiencyReport(
            report_id=f"gcsr-{uuid4()}",
            status="sufficient" if self.nodes else "insufficient",
            missing_workflow_info=[] if self.nodes else ["packaged demo G1 has no nodes"],
            controlled_recall_required=False,
        )
        return RuntimeGraphContext(
            graph_context_id=f"rgc-{uuid4()}",
            task_fingerprint_id=fingerprint.fingerprint_id,
            source_graph_tier="G1",
            G_task=RuntimeLayerView(
                profile_id=self.profile.profile_id,
                mode=self.profile.mode,
                task=fingerprint.task,
                nodes=views["task"]["nodes"],
                edges=views["task"]["edges"],
            ),
            G_evidence=RuntimeLayerView(**views["evidence"]),
            G_workflow=RuntimeLayerView(**views["workflow"]),
            G_resource=RuntimeLayerView(**views["resource"]),
            G_skill=RuntimeLayerView(**views["skill"]),
            G_experience=RuntimeLayerView(**views["experience"]),
            cross_layer_edges=views["cross_layer_edges"]["edges"],
            sufficiency_report=report,
            provenance=[
                Provenance(
                    source_type="packaged_demo_g1",
                    source_id=self.profile.profile_id,
                    source_path=self.profile.l1_asset_path,
                )
            ],
        )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes_by_id.get(node_id)

    def materialize_from_patches(self, patches: list[GraphPatch]) -> str:
        msg = f"Packaged graph profile is read-only: {self.profile.profile_id}"
        raise PackagedGraphStoreError(msg)


class JsonlPackagedDemoGraphStoreLoader:
    def load_l0_store(self, profile: GraphProfile) -> PackagedFullGraphStore:
        _assert_packaged_demo_profile(profile)
        if profile.l0_asset_path is None:
            msg = f"Demo profile has no G0 asset path: {profile.profile_id}"
            raise PackagedGraphStoreError(msg)
        records = load_graph_records(Path(profile.l0_asset_path), graph_tier="G0")
        return PackagedFullGraphStore(
            profile=profile,
            nodes=records.nodes,
            edges=records.edges,
        )

    def load_l1_store(self, profile: GraphProfile) -> PackagedHealthyGraphStore:
        _assert_packaged_demo_profile(profile)
        if profile.l1_asset_path is None:
            msg = f"Demo profile has no G1 asset path: {profile.profile_id}"
            raise PackagedGraphStoreError(msg)
        records = load_graph_records(Path(profile.l1_asset_path), graph_tier="G1")
        return PackagedHealthyGraphStore(
            profile=profile,
            nodes=records.nodes,
            edges=records.edges,
        )


def load_packaged_demo_graph_manifest(path: str | Path) -> PackagedDemoGraphManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return PackagedDemoGraphManifest.model_validate(payload)


def _assert_packaged_demo_profile(profile: GraphProfile) -> None:
    if profile.mode != "demo":
        msg = f"Packaged demo loader only accepts demo profiles: {profile.profile_id}"
        raise PackagedGraphStoreError(msg)
    if profile.l0_source != "packaged" or profile.l1_source != "packaged":
        msg = f"Packaged demo loader requires packaged G0 and G1: {profile.profile_id}"
        raise PackagedGraphStoreError(msg)


def load_graph_records(
    path: str | Path,
    *,
    graph_tier: Literal["G0", "G1"],
) -> BioEvoKGGraphRecords:
    asset_path = Path(path)
    nodes = [
        BioEvoKGNode.model_validate(record)
        for record in _load_jsonl(asset_path / "nodes.jsonl")
    ]
    edges = [
        BioEvoKGEdge.model_validate(record)
        for record in _load_jsonl(asset_path / "edges.jsonl")
    ]
    return BioEvoKGGraphRecords(
        graph_tier=graph_tier,
        nodes=nodes,
        edges=edges,
        require_l1_operational_profile=graph_tier == "G1",
        require_l1_healthy_states=graph_tier == "G1",
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        msg = f"Packaged graph asset file does not exist: {path}"
        raise PackagedGraphStoreError(msg)

    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            msg = f"Packaged graph asset line must be a JSON object: {path}:{line_number}"
            raise PackagedGraphStoreError(msg)
        records.append(payload)
    return records


def _index_nodes(nodes: list[BioEvoKGNode]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for node in nodes:
        indexed[node.node_id] = node.model_dump(mode="json")
    return indexed


def _split_runtime_views(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    views: dict[str, dict[str, Any]] = {
        "task": {"nodes": [], "edges": []},
        "evidence": {"nodes": [], "edges": []},
        "workflow": {"nodes": [], "edges": []},
        "resource": {"nodes": [], "edges": []},
        "skill": {"nodes": [], "edges": []},
        "experience": {"nodes": [], "edges": []},
        "cross_layer_edges": {"nodes": [], "edges": []},
    }
    node_view: dict[str, str] = {}
    for node in nodes:
        layer = node.get("layer")
        view_name = str(layer)
        if view_name in views:
            views[view_name]["nodes"].append(node)
            node_view[str(node["node_id"])] = view_name

    for edge in edges:
        source_view = node_view.get(str(edge.get("source_node_id")))
        target_view = node_view.get(str(edge.get("target_node_id")))
        if source_view == target_view and source_view in views:
            views[source_view]["edges"].append(edge)
        elif source_view in views and target_view in views:
            views["cross_layer_edges"]["edges"].append(edge)
    return views
