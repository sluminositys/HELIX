from lattice.schemas import (
    AgenticExecutionPlan,
    AgenticExecutionStep,
    ArtifactManifest,
    ScriptExecutionRawResult,
    ScriptProposal,
)
from lattice.verification import ResultVerifier


def test_exit_zero_does_not_pass_when_declared_artifact_is_missing() -> None:
    plan = AgenticExecutionPlan(
        plan_id="plan-1",
        task_fingerprint_id="tf-1",
        runtime_graph_context_id="g2-1",
        steps=[
            AgenticExecutionStep(
                step_id="step-1",
                objective="produce result.csv",
                expected_outputs=["result.csv"],
            )
        ],
    )
    proposal = ScriptProposal(
        proposal_id="script-1",
        plan_id="plan-1",
        script_text="print('done')",
        covered_step_ids=["step-1"],
    )
    execution = ScriptExecutionRawResult(
        execution_id="execution-1",
        proposal_id="script-1",
        status="success",
        exit_code=0,
    )
    manifest = ArtifactManifest(
        manifest_id="manifest-1",
        execution_id="execution-1",
        artifacts=[],
    )

    report = ResultVerifier().verify(
        plan=plan,
        proposal=proposal,
        execution=execution,
        manifest=manifest,
    )

    assert report.status == "repairable"
    assert report.missing_artifacts == ["result.csv"]
