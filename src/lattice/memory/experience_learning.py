from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import Field

from lattice.schemas import (
    ExperienceCandidate,
    LatticeBaseModel,
    ResearchTask,
    ResultVerificationReport,
    RunRecord,
)


class ExperienceGeneralizationDecision(LatticeBaseModel):
    status: Literal["eligible", "insufficient_evidence", "contradicted"]
    reasons: list[str] = Field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.status == "eligible"


class ExperienceCandidateExtractor:
    def extract(
        self,
        *,
        run_record: RunRecord,
        verification: ResultVerificationReport,
        task: ResearchTask,
    ) -> ExperienceCandidate:
        success = verification.status == "completed" and run_record.status == "success"
        candidate_type: Literal["success_pattern", "failure_pattern"] = (
            "success_pattern" if success else "failure_pattern"
        )
        summary = (
            f"Successful execution candidate for task {task.task_id}"
            if success
            else f"Execution issue candidate for task {task.task_id}: "
            + "; ".join(verification.issues or [run_record.status])
        )
        return ExperienceCandidate(
            candidate_id=f"experience-candidate-{uuid4()}",
            candidate_type=candidate_type,
            summary=summary,
            trigger_conditions=[*task.constraints, f"research_mode={task.research_mode}"],
            applicable_task_tags=task.candidate_task_tags,
            applicable_method_tags=task.candidate_method_tags,
            applicable_tool_names=run_record.suggested_tool_names,
            supporting_run_ids=[run_record.run_id],
            evidence_refs=[run_record.artifact_manifest_id]
            if run_record.artifact_manifest_id
            else [],
            occurrence_count=1,
            generality="single_observation",
            confidence=0.35 if success else 0.45,
            proposed_target_layers=["experience"],
            source_event_ids=[],
            trigger_condition={"task_id": task.task_id},
        )


class ExperienceGeneralizationGate:
    def __init__(self, *, min_occurrences: int = 3, min_confidence: float = 0.7) -> None:
        self.min_occurrences = min_occurrences
        self.min_confidence = min_confidence

    def evaluate(self, candidate: ExperienceCandidate) -> ExperienceGeneralizationDecision:
        if candidate.contradiction_refs:
            return ExperienceGeneralizationDecision(
                status="contradicted",
                reasons=["candidate has unresolved contradiction references"],
            )
        reasons = []
        if candidate.occurrence_count < self.min_occurrences:
            reasons.append(
                f"occurrence_count {candidate.occurrence_count} is below {self.min_occurrences}"
            )
        if candidate.confidence < self.min_confidence:
            reasons.append(
                f"confidence {candidate.confidence:.2f} is below {self.min_confidence:.2f}"
            )
        if candidate.generality == "single_observation":
            reasons.append("single observations are retained in run history, not G0")
        if reasons:
            return ExperienceGeneralizationDecision(
                status="insufficient_evidence",
                reasons=reasons,
            )
        return ExperienceGeneralizationDecision(status="eligible")
