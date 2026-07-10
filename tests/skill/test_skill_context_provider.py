from lattice.schemas import (
    GraphContextSufficiencyReport,
    ResearchTask,
    RuntimeGraphContext,
)
from lattice.skill import SkillContextProvider


def test_skill_context_provider_resolves_cross_layer_resource_and_children() -> None:
    context = RuntimeGraphContext(
        graph_context_id="g2-1",
        task_fingerprint_id="tf-1",
        source_graph_tier="G1",
        G_resource={
            "nodes": [
                {
                    "node_id": "tool-python",
                    "layer": "resource",
                    "node_type": "Tool",
                    "canonical_name": "Python",
                    "attributes": {"tool_name": "python"},
                    "lifecycle_state": "active_hot",
                }
            ]
        },
        G_skill={
            "nodes": [
                {
                    "node_id": "skill-python",
                    "layer": "skill",
                    "node_type": "ToolUsageSkill",
                    "canonical_name": "Python table analysis",
                    "attributes": {
                        "tool_name": "python",
                        "purpose": "analyze CSV tables",
                        "readiness_state": "usable_validated",
                    },
                    "lifecycle_state": "active_hot",
                    "provenance": [{"source_type": "docs"}],
                },
                {
                    "node_id": "skill-python-params",
                    "layer": "skill",
                    "node_type": "ParameterGuidance",
                    "canonical_name": "CSV delimiter",
                    "attributes": {},
                    "lifecycle_state": "active_hot",
                },
            ],
            "edges": [
                {
                    "edge_type": "HAS_PARAMETER_GUIDANCE",
                    "source_node_id": "skill-python",
                    "target_node_id": "skill-python-params",
                }
            ],
        },
        G_experience={
            "nodes": [
                {
                    "node_id": "experience-python-recovery",
                    "layer": "experience",
                    "node_type": "SuccessPattern",
                    "canonical_name": "Recover malformed CSV rows before parsing",
                    "attributes": {},
                    "lifecycle_state": "active_warm",
                }
            ]
        },
        cross_layer_edges=[
            {
                "edge_type": "HAS_USAGE_SKILL",
                "source_node_id": "tool-python",
                "target_node_id": "skill-python",
            },
            {
                "edge_type": "SUPPORTS_SKILL_UPDATE",
                "source_node_id": "experience-python-recovery",
                "target_node_id": "skill-python",
            },
        ],
        sufficiency_report=GraphContextSufficiencyReport(
            report_id="report-1",
            status="sufficient",
        ),
    )
    task = ResearchTask(
        task_id="task-1",
        fingerprint_id="tf-1",
        user_goal="Analyze a CSV table with Python",
        research_mode="routine",
        candidate_tool_names=["python"],
    )

    skills = SkillContextProvider().resolve_skills_for_task(task, context)

    assert [skill.primary_skill["node_id"] for skill in skills] == ["skill-python"]
    assert skills[0].parameter_guidance[0]["node_id"] == "skill-python-params"
    assert skills[0].related_resource_nodes[0]["node_id"] == "tool-python"
    assert (
        skills[0].related_experience_nodes[0]["node_id"]
        == "experience-python-recovery"
    )
