from lattice.orchestration import run_plan_only
from lattice.runtime import FileAgentEventLog


def test_plan_only_flow_builds_dynamic_strategy_without_graph() -> None:
    state = run_plan_only("Plan requested workflow", session_id="session-1")

    assert state["status"] == "plan_verified"
    assert state["task_fingerprint"].execution_intent == "plan_only"
    assert state["runtime_context"].sufficiency_report.status == "insufficient"
    assert state["workflow_report"].status == "warning"
    assert state["execution_plan"] is not None
    assert state["execution_plan"].selected_workflow_path_id is None
    assert state["permission_decision"].allowed is False
    assert state["permission_decision"].blocked_by == ["PLAN_ONLY_MODE"]
    assert state["response"] == "Plan verified."


def test_plan_only_flow_appends_event_log(tmp_path) -> None:
    event_log = FileAgentEventLog(tmp_path / "events.jsonl")

    run_plan_only("Plan requested workflow", session_id="session-1", event_log=event_log)

    events = event_log.read_all()
    assert [event.event_type for event in events] == [
        "UserRequestReceived",
        "TaskUnderstood",
        "PlanModeEntered",
        "TaskFingerprinted",
        "RuntimeGraphContextProjected",
        "WorkflowPathSelected",
        "CapabilityGapDetected",
        "EvolutionRequested",
        "WorkflowVerified",
        "PermissionChecked",
    ]
    assert {event.session_id for event in events} == {"session-1"}
