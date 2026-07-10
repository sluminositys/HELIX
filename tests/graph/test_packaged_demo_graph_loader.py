import json
from pathlib import Path

import pytest

from lattice.core import TaskFingerprinter
from lattice.graph import (
    JsonlPackagedDemoGraphStoreLoader,
    PackagedGraphStoreError,
    load_packaged_demo_graph_manifest,
)
from lattice.orchestration import run_plan_only
from lattice.schemas import GraphPatch, Provenance, create_packaged_demo_graph_profile


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )


def create_demo_asset_dirs(tmp_path: Path) -> tuple[Path, Path]:
    l0_path = tmp_path / "demo_l0"
    l1_path = tmp_path / "demo_l1"
    operational_profile = {
        "lifecycle_state": "active_hot",
        "compiled_from_graph_patch_ids": ["patch-1"],
    }
    nodes = [
        {
            "node_id": "tool-1",
            "layer": "resource",
            "node_type": "Tool",
            "canonical_name": "Tool node",
            "lifecycle_state": "active_hot",
            "operational_profile": operational_profile,
            "provenance": [{"source_type": "test"}],
        },
        {
            "node_id": "method-1",
            "layer": "workflow",
            "node_type": "Method",
            "canonical_name": "Method node",
            "lifecycle_state": "active_hot",
            "operational_profile": operational_profile,
            "provenance": [{"source_type": "test"}],
        },
    ]
    edges = [
        {
            "edge_id": "edge-1",
            "edge_type": "IMPLEMENTS_METHOD",
            "source_node_id": "tool-1",
            "target_node_id": "method-1",
            "source_layer": "resource",
            "target_layer": "workflow",
            "source_type": "packaged_demo",
            "lifecycle_state": "active_hot",
            "operational_profile": operational_profile,
            "provenance": [{"source_type": "test"}],
        }
    ]
    write_jsonl(l0_path / "nodes.jsonl", nodes)
    write_jsonl(l0_path / "edges.jsonl", edges)
    write_jsonl(l1_path / "nodes.jsonl", nodes)
    write_jsonl(l1_path / "edges.jsonl", edges)
    return l0_path, l1_path


def test_packaged_demo_loader_loads_read_only_l0_store(tmp_path) -> None:
    l0_path, l1_path = create_demo_asset_dirs(tmp_path)
    profile = create_packaged_demo_graph_profile(
        profile_id="demo-profile",
        l0_asset_path=str(l0_path),
        l1_asset_path=str(l1_path),
    )

    store = JsonlPackagedDemoGraphStoreLoader().load_l0_store(profile)

    node = store.get_node("tool-1")
    assert node is not None
    assert node["layer"] == "resource"
    assert node["node_type"] == "Tool"
    with pytest.raises(PackagedGraphStoreError):
        store.apply_patch(
            GraphPatch(
                patch_id="patch-1",
                source_event_ids=["event-1"],
                source_module="test",
                provenance=Provenance(source_type="test"),
            )
        )


def test_packaged_demo_l1_store_projects_runtime_context(tmp_path) -> None:
    l0_path, l1_path = create_demo_asset_dirs(tmp_path)
    profile = create_packaged_demo_graph_profile(
        profile_id="demo-profile",
        l0_asset_path=str(l0_path),
        l1_asset_path=str(l1_path),
    )
    store = JsonlPackagedDemoGraphStoreLoader().load_l1_store(profile)
    fingerprint = TaskFingerprinter().fingerprint("Plan requested workflow")

    context = store.project_runtime_context(fingerprint)

    assert context.sufficiency_report.status == "sufficient"
    assert context.G_task["profile_id"] == "demo-profile"
    assert context.G_workflow["nodes"][0]["node_id"] == "method-1"
    assert context.G_resource["nodes"][0]["node_id"] == "tool-1"
    assert context.cross_layer_edges[0]["edge_id"] == "edge-1"


def test_plan_only_can_use_packaged_demo_l1_store(tmp_path) -> None:
    l0_path, l1_path = create_demo_asset_dirs(tmp_path)
    profile = create_packaged_demo_graph_profile(
        profile_id="demo-profile",
        l0_asset_path=str(l0_path),
        l1_asset_path=str(l1_path),
    )
    store = JsonlPackagedDemoGraphStoreLoader().load_l1_store(profile)

    state = run_plan_only(
        "Plan requested workflow",
        session_id="session-1",
        healthy_graph_store=store,
    )

    assert state["runtime_context"].G_task["profile_id"] == "demo-profile"
    assert (
        "no healthy graph store is configured"
        not in state["workflow_search_result"].unresolved_requirements
    )


def test_load_packaged_demo_graph_manifest(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "manifest-1",
                "profile_id": "demo-profile",
                "l0": {
                    "tier": "G0",
                    "nodes_path": "demo_l0/nodes.jsonl",
                    "edges_path": "demo_l0/edges.jsonl",
                },
                "l1": {
                    "tier": "G1",
                    "nodes_path": "demo_l1/nodes.jsonl",
                    "edges_path": "demo_l1/edges.jsonl",
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = load_packaged_demo_graph_manifest(manifest_path)

    assert manifest.profile_id == "demo-profile"
    assert manifest.all_l1_nodes_healthy is True
    assert manifest.builder_artifacts_included is False
