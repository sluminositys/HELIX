from __future__ import annotations

from pathlib import Path
from typing import Any

from lattice.capability_evolution import RuntimeDiscoveryResult
from lattice.orchestration import run_execution
from lattice.runtime import ScriptGenerationAgent, ScriptRunner, StaticScriptDraftProvider
from lattice.schemas import (
    AgenticExecutionPlan,
    AgenticExecutionStep,
    GraphContextSufficiencyReport,
    GraphPatch,
    Provenance,
    RuntimeGraphContext,
    TaskFingerprint,
)


class FakeHealthyGraphStore:
    def project_runtime_context(self, fingerprint: TaskFingerprint) -> RuntimeGraphContext:
        return RuntimeGraphContext(
            graph_context_id="rgc-test",
            task_fingerprint_id=fingerprint.fingerprint_id,
            source_graph_tier="G1",
            G_workflow={
                "nodes": [
                    {
                        "node_id": "workflow-path-1",
                        "layer": "workflow",
                        "node_type": "WorkflowPath",
                        "lifecycle_state": "active_hot",
                        "attributes": {"step_ids": ["workflow-step-1"]},
                    },
                    {
                        "node_id": "workflow-step-1",
                        "layer": "workflow",
                        "node_type": "WorkflowStep",
                        "lifecycle_state": "active_hot",
                        "attributes": {
                            "workflow_path_id": "workflow-path-1",
                            "skill_ids": ["skill-double"],
                            "suggested_tool_names": ["double"],
                            "input_bindings": {"value": 2},
                        },
                    },
                ],
                "edges": [],
            },
            G_resource={"nodes": [], "edges": []},
            G_skill={
                "nodes": [
                    {
                        "node_id": "skill-double",
                        "layer": "skill",
                        "node_type": "ToolUsageSkill",
                        "lifecycle_state": "active_hot",
                        "attributes": {
                            "agent_readable_skill": {
                                "enabled": True,
                            }
                        },
                    }
                ],
                "edges": [],
            },
            sufficiency_report=GraphContextSufficiencyReport(
                report_id="gcsr-test",
                status="sufficient",
            ),
        )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return None


class FakeFullGraphStore:
    def __init__(self) -> None:
        self.applied_patch: GraphPatch | None = None
        self.applied_patches: list[GraphPatch] = []

    def apply_patch(self, patch: GraphPatch) -> str:
        self.applied_patch = patch
        self.applied_patches.append(patch)
        return f"write-{len(self.applied_patches)}"

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return None


def _test_script_generator() -> ScriptGenerationAgent:
    return ScriptGenerationAgent(
        StaticScriptDraftProvider(
            "from pathlib import Path\n"
            "Path('result.json').write_text('{\"status\": \"ok\"}', encoding='utf-8')\n"
        )
    )


def test_execution_flow_generates_script_without_promoting_single_run(tmp_path: Path) -> None:
    full_store = FakeFullGraphStore()

    state = run_execution(
        "Run executable workflow",
        session_id="session-1",
        healthy_graph_store=FakeHealthyGraphStore(),
        full_graph_store=full_store,
        script_generation_agent=_test_script_generator(),
        script_runner=ScriptRunner(output_root=tmp_path),
    )

    assert state["status"] == "executed"
    assert state["permission_decision"].allowed is True
    assert state["script_review"].approved is True
    assert state["script_execution_result"].status == "success"
    assert state["run_record"].referenced_skill_ids == ["skill-double"]
    assert state["result_verification"].status == "completed"
    assert state["experience_candidate"].generality == "single_observation"
    assert state["experience_generalization"].eligible is False
    assert state["experience_patch"] is None
    assert state["graph_write_id"] is None
    assert full_store.applied_patch is None
    assert all(item["exists"] for item in state["artifact_manifest"].artifacts)


def test_execution_fails_closed_when_no_script_model_is_configured() -> None:
    state = run_execution(
        "Run executable workflow",
        session_id="session-no-model",
        healthy_graph_store=FakeHealthyGraphStore(),
    )

    assert state["script_proposal"] is None
    assert state["script_execution_result"] is None
    assert "No chat model is configured" in state["response"]


class EmptyHealthyGraphStore:
    def __init__(self) -> None:
        self.applied_patches: list[GraphPatch] = []

    def project_runtime_context(self, fingerprint: TaskFingerprint) -> RuntimeGraphContext:
        return RuntimeGraphContext(
            graph_context_id="rgc-empty",
            task_fingerprint_id=fingerprint.fingerprint_id,
            source_graph_tier="G1",
            sufficiency_report=GraphContextSufficiencyReport(
                report_id="gcsr-empty",
                status="insufficient",
                missing_workflow_info=["no active workflow path nodes projected from G1"],
                missing_skill_info=["no active L5 skill view has been projected"],
                controlled_recall_required=True,
                controlled_recall_reason="G1 lacks a ready path for this request.",
            ),
        )

    def materialize_from_patches(self, patches: list[GraphPatch]) -> str:
        self.applied_patches.extend(patches)
        return f"g1-write-{len(self.applied_patches)}"

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return None


class StaticRuntimeDiscoverer:
    def discover(
        self,
        *,
        request: str,
        fingerprint: TaskFingerprint,
        runtime_context: RuntimeGraphContext,
        workflow_search_result: Any,
        capability_gaps: list[Any],
    ) -> RuntimeDiscoveryResult:
        plan = AgenticExecutionPlan(
            plan_id="aep-runtime-discovered",
            task_fingerprint_id=fingerprint.fingerprint_id,
            runtime_graph_context_id=runtime_context.graph_context_id,
            selected_workflow_path_id="runtime-discovered-path",
            steps=[
                AgenticExecutionStep(
                    step_id="runtime-step-1",
                    workflow_step_id="runtime-step-1",
                    skill_ids=["skill-increment"],
                    suggested_tool_names=["increment"],
                    input_bindings={"value": 2},
                )
            ],
            provenance=[Provenance(source_type="runtime_capability_discovery")],
        )
        patch = GraphPatch(
            patch_id="patch-runtime-discovered",
            source_event_ids=["event-runtime-discovery"],
            source_module="RuntimeCapabilityDiscovery",
            nodes_to_add=[
                {
                    "node_id": "resource-tool-increment",
                    "layer": "resource",
                    "node_type": "Tool",
                    "canonical_name": "increment",
                    "attributes": {"tool_name": "increment", "request": request},
                    "lifecycle_state": "probationary",
                    "provenance": [{"source_type": "runtime_capability_discovery"}],
                },
                {
                    "node_id": "skill-tool-usage-increment",
                    "layer": "skill",
                    "node_type": "ToolUsageSkill",
                    "canonical_name": "increment usage skill",
                    "attributes": {
                        "software_id": "resource-tool-increment",
                        "software_name": "increment",
                        "agent_readable_skill": {
                            "enabled": True,
                        },
                    },
                    "lifecycle_state": "probationary",
                    "provenance": [{"source_type": "runtime_capability_discovery"}],
                },
            ],
            provenance=Provenance(source_type="runtime_capability_discovery"),
            approval_status="proposed",
        )
        return RuntimeDiscoveryResult(
            status="candidate_plan_ready",
            reason="G2 had no mandatory path, so runtime discovery supplied a temporary plan.",
            execution_plan=plan,
            discovered_skills=[{"skill_id": "skill-increment", "tool_name": "increment"}],
            graph_patches=[patch],
        )


class SequencedScriptProvider:
    def __init__(self, scripts: list[str]) -> None:
        self.scripts = scripts
        self.calls = 0

    def draft(self, prompt: str) -> str:
        _ = prompt
        script = self.scripts[min(self.calls, len(self.scripts) - 1)]
        self.calls += 1
        return script


def test_execution_can_use_runtime_discovery_when_g2_has_no_path(tmp_path: Path) -> None:
    full_store = FakeFullGraphStore()
    healthy_store = EmptyHealthyGraphStore()

    state = run_execution(
        "Use a tool not already present in G2",
        session_id="session-2",
        healthy_graph_store=healthy_store,
        full_graph_store=full_store,
        runtime_discoverer=StaticRuntimeDiscoverer(),
        script_generation_agent=_test_script_generator(),
        script_runner=ScriptRunner(output_root=tmp_path),
    )

    assert state["status"] == "executed"
    assert state["workflow_report"].status == "warning"
    assert state["workflow_report"].warnings[0].code == (
        "DYNAMIC_STRATEGY_WITHOUT_G2_PATH"
    )
    assert state["runtime_discovery_result"].status == "candidate_plan_ready"
    assert state["run_record"].referenced_skill_ids == ["skill-increment"]
    assert [patch.patch_id for patch in full_store.applied_patches] == [
        "patch-runtime-discovered",
    ]
    assert state["experience_patch"] is None
    assert healthy_store.applied_patches == []


def test_execution_revises_invalid_script_before_running(tmp_path: Path) -> None:
    provider = SequencedScriptProvider(
        [
            "def broken(:\n    pass\n",
            "from pathlib import Path\nPath('result.txt').write_text('ok', encoding='utf-8')\n",
        ]
    )

    state = run_execution(
        "Run executable workflow",
        session_id="session-revision",
        healthy_graph_store=FakeHealthyGraphStore(),
        script_generation_agent=ScriptGenerationAgent(provider),
        script_runner=ScriptRunner(output_root=tmp_path),
    )

    assert provider.calls == 2
    assert state["script_revision_count"] == 1
    assert state["script_review"].approved is True
    assert state["result_verification"].status == "completed"
