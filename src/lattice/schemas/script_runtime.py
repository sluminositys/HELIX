from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from lattice.schemas.common import LatticeBaseModel, Provenance

ScriptLanguage = Literal["python", "r", "shell"]
ScriptReviewStatus = Literal["approved", "needs_revision", "requires_revision", "blocked"]
ScriptExecutionStatus = Literal[
    "success",
    "partial",
    "failure",
    "timeout",
    "skipped",
    "cancelled",
]


class ScriptProposal(LatticeBaseModel):
    proposal_id: str
    plan_id: str
    language: ScriptLanguage = "python"
    script_text: str
    covered_step_ids: list[str] = Field(default_factory=list)
    intended_actions: list[str] = Field(default_factory=list)
    referenced_skill_ids: list[str] = Field(default_factory=list)
    suggested_tool_names: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    permission_requirements: dict[str, Any] = Field(default_factory=dict)
    environment_requirements: list[str] = Field(default_factory=list)
    rationale: str = ""
    revision_of_proposal_id: str | None = None
    provenance: list[Provenance] = Field(default_factory=list)


class ScriptReviewResult(LatticeBaseModel):
    review_id: str
    proposal_id: str
    status: ScriptReviewStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)
    static_findings: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)

    @property
    def approved(self) -> bool:
        return self.status == "approved" and not self.blockers


class ScriptExecutionRawResult(LatticeBaseModel):
    execution_id: str
    proposal_id: str
    status: ScriptExecutionStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    stdout_path: str | None = None
    stderr_path: str | None = None
    error_summary: str | None = None
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)


class ArtifactManifest(LatticeBaseModel):
    manifest_id: str
    execution_id: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)


class RunRecord(LatticeBaseModel):
    run_id: str
    session_id: str
    request: str
    plan_id: str | None = None
    proposal_id: str | None = None
    execution_id: str | None = None
    status: ScriptExecutionStatus
    referenced_skill_ids: list[str] = Field(default_factory=list)
    suggested_tool_names: list[str] = Field(default_factory=list)
    artifact_manifest_id: str | None = None
    result_summary: str = ""
    verification_status: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)
