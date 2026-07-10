from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from lattice.schemas import (
    AgenticExecutionPlan,
    ArtifactManifest,
    Provenance,
    ResultVerificationReport,
    ScriptExecutionRawResult,
    ScriptProposal,
)


class ResultVerifier:
    def verify(
        self,
        *,
        plan: AgenticExecutionPlan | None,
        proposal: ScriptProposal | None,
        execution: ScriptExecutionRawResult | None,
        manifest: ArtifactManifest | None,
    ) -> ResultVerificationReport:
        provenance = [Provenance(source_type="result_verifier")]
        criteria = [
            criterion
            for step in (plan.steps if plan is not None else [])
            for criterion in step.success_criteria
        ]
        if execution is None:
            return ResultVerificationReport(
                report_id=f"result-verification-{uuid4()}",
                status="not_executed",
                success_criteria=criteria,
                issues=["no script execution result is available"],
                provenance=provenance,
            )

        if execution.status in {"failure", "timeout"}:
            issue = execution.error_summary or execution.stderr[-1000:] or execution.status
            return ResultVerificationReport(
                report_id=f"result-verification-{uuid4()}",
                status="repairable" if proposal is not None else "failed",
                success_criteria=criteria,
                issues=[issue],
                repair_guidance=[
                    "revise the script using the captured error and relevant recovery strategies"
                ],
                provenance=provenance,
            )

        expected = [
            output
            for step in (plan.steps if plan is not None else [])
            for output in step.expected_outputs
            if _looks_like_artifact(output)
        ]
        actual_paths = [
            str(item.get("path", ""))
            for item in (manifest.artifacts if manifest is not None else [])
            if item.get("path")
        ]
        missing = [
            output
            for output in expected
            if not any(_artifact_matches(output, path) for path in actual_paths)
        ]
        if missing:
            return ResultVerificationReport(
                report_id=f"result-verification-{uuid4()}",
                status="repairable",
                success_criteria=criteria,
                satisfied_criteria=["script process exited successfully"],
                missing_artifacts=missing,
                issues=["declared artifacts were not produced"],
                repair_guidance=["write each declared output into the task working directory"],
                provenance=provenance,
            )

        unverified = [
            criterion for criterion in criteria if not _is_deterministic_criterion(criterion)
        ]
        if unverified:
            return ResultVerificationReport(
                report_id=f"result-verification-{uuid4()}",
                status="failed",
                success_criteria=criteria,
                satisfied_criteria=["script process exited successfully"],
                unverified_criteria=unverified,
                issues=[
                    "success criteria require semantic or domain-specific verification"
                ],
                provenance=provenance,
            )

        return ResultVerificationReport(
            report_id=f"result-verification-{uuid4()}",
            status="completed",
            success_criteria=criteria,
            satisfied_criteria=["script process exited successfully", *criteria],
            provenance=provenance,
        )


def _looks_like_artifact(value: str) -> bool:
    path = Path(value)
    return bool(path.suffix or "/" in value or "\\" in value)


def _artifact_matches(expected: str, actual: str) -> bool:
    expected_path = Path(expected)
    actual_path = Path(actual)
    return expected_path.name == actual_path.name or str(expected_path) == str(actual_path)


def _is_deterministic_criterion(value: str) -> bool:
    lowered = value.lower()
    return _looks_like_artifact(value) and any(
        marker in lowered for marker in ("exists", "non-empty", "not empty", "checksum")
    )
