from lattice.core import TaskFingerprinter


def test_task_fingerprinter_is_conservative_about_unknown_fields() -> None:
    fingerprint = TaskFingerprinter().fingerprint("  Analyze provided dataset  ", user_id="user-1")

    assert fingerprint.task == "Analyze provided dataset"
    assert fingerprint.user_id == "user-1"
    assert fingerprint.execution_intent == "plan_only"
    assert fingerprint.task_category == "data_analysis"
    assert fingerprint.research_mode == "adaptive"
    assert fingerprint.output_goals == ["analysis_result"]
    assert fingerprint.ambiguity_items == []
