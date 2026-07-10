import json

from lattice.app.cli import main


def test_cli_plan_outputs_dynamic_plan(capsys) -> None:
    exit_code = main(["plan", "Plan requested workflow", "--session-id", "session-1"])

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "plan_verified"
    assert output["execution_plan"]["selected_workflow_path_id"] is None
    assert output["task_fingerprint"]["execution_intent"] == "plan_only"
    assert output["permission_decision"]["allowed"] is False


def test_cli_plan_can_write_event_log(capsys, tmp_path) -> None:
    event_log_path = tmp_path / "events.jsonl"

    exit_code = main(
        [
            "plan",
            "Plan requested workflow",
            "--session-id",
            "session-1",
            "--event-log",
            str(event_log_path),
        ]
    )

    capsys.readouterr()

    assert exit_code == 0
    assert event_log_path.exists()
    assert len(event_log_path.read_text(encoding="utf-8").splitlines()) == 10
