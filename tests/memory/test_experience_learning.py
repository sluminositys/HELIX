from lattice.memory import ExperienceCandidateExtractor, ExperienceGeneralizationGate
from lattice.schemas import ResearchTask, ResultVerificationReport, RunRecord


def test_single_success_is_not_generalized_into_g0() -> None:
    record = RunRecord(
        run_id="run-1",
        session_id="session-1",
        request="analyze",
        status="success",
        artifact_manifest_id="manifest-1",
    )
    verification = ResultVerificationReport(
        report_id="verification-1",
        status="completed",
    )
    task = ResearchTask(
        task_id="task-1",
        fingerprint_id="tf-1",
        user_goal="analyze",
        research_mode="routine",
    )

    candidate = ExperienceCandidateExtractor().extract(
        run_record=record,
        verification=verification,
        task=task,
    )
    decision = ExperienceGeneralizationGate().evaluate(candidate)

    assert candidate.candidate_type == "success_pattern"
    assert candidate.generality == "single_observation"
    assert decision.eligible is False
