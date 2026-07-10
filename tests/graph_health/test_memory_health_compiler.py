from lattice.graph_health import MemoryHealthCompiler
from lattice.schemas import GraphPatch, Provenance


def test_memory_health_compiler_skips_empty_patch_set() -> None:
    report = MemoryHealthCompiler().compile([])

    assert report.status == "skipped"
    assert report.materialized_l1 is False


def test_memory_health_compiler_reports_compiled_l0_patches() -> None:
    patch = GraphPatch(
        patch_id="patch-1",
        source_event_ids=["event-1"],
        source_module="test",
        nodes_to_add=[
            {
                "node_id": "skill-1",
                "layer": "skill",
                "node_type": "ToolUsageSkill",
                "canonical_name": "Validated skill",
                "lifecycle_state": "active_warm",
                "provenance": [{"source_type": "test"}],
            }
        ],
        provenance=Provenance(source_type="test"),
    )

    report = MemoryHealthCompiler().compile([patch])

    assert report.status == "completed"
    assert report.compiled_patch_ids == ["patch-1"]
    assert report.materialized_l1 is True
    assert report.eligible_patch_ids == ["patch-1"]
    assert report.g1_patches[0].target_graph_tier == "G1"


def test_memory_health_compiler_excludes_candidate_only_patch() -> None:
    patch = GraphPatch(
        patch_id="patch-candidate",
        source_event_ids=["event-1"],
        source_module="test",
        nodes_to_add=[
            {
                "node_id": "experience-1",
                "layer": "experience",
                "node_type": "SuccessPattern",
                "canonical_name": "Single run",
                "lifecycle_state": "candidate",
                "provenance": [{"source_type": "test"}],
            }
        ],
        provenance=Provenance(source_type="test"),
    )

    report = MemoryHealthCompiler().compile([patch])

    assert report.materialized_l1 is False
    assert "patch-candidate" in report.excluded_patch_reasons


def test_memory_health_compiler_keeps_active_edge_to_existing_node() -> None:
    patch = GraphPatch(
        patch_id="patch-linked-node",
        source_event_ids=["event-1"],
        source_module="test",
        nodes_to_add=[
            {
                "node_id": "skill-1",
                "layer": "skill",
                "node_type": "ToolUsageSkill",
                "canonical_name": "Validated skill",
                "lifecycle_state": "active_warm",
            }
        ],
        edges_to_add=[
            {
                "edge_id": "edge-existing-resource-skill",
                "source_node_id": "existing-resource",
                "target_node_id": "skill-1",
                "lifecycle_state": "active_warm",
            }
        ],
        provenance=Provenance(source_type="test"),
    )

    report = MemoryHealthCompiler().compile([patch])

    assert report.g1_patches[0].edges_to_add[0]["edge_id"] == (
        "edge-existing-resource-skill"
    )
