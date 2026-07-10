from lattice.planning import ResearchStrategyPlanner, WorkflowSearchResult
from lattice.schemas import (
    GraphContextSufficiencyReport,
    ResearchTask,
    RuntimeGraphContext,
    TaskFingerprint,
)


def test_research_strategy_can_plan_without_mandatory_g2_workflow() -> None:
    fingerprint = TaskFingerprint(
        fingerprint_id="tf-1",
        user_id="user-1",
        task="Analyze input.csv and write result.csv",
        task_category="data_analysis",
        execution_intent="execute",
    )
    task = ResearchTask(
        task_id="task-1",
        fingerprint_id="tf-1",
        user_goal=fingerprint.task,
        research_mode="routine",
        input_artifacts=["input.csv"],
        output_goals=["result.csv"],
        success_criteria=["result.csv exists"],
    )
    context = RuntimeGraphContext(
        graph_context_id="g2-1",
        task_fingerprint_id="tf-1",
        source_graph_tier="G1",
        sufficiency_report=GraphContextSufficiencyReport(
            report_id="report-1",
            status="insufficient",
        ),
    )

    plan = ResearchStrategyPlanner().build(
        task=task,
        fingerprint=fingerprint,
        runtime_context=context,
        search_result=WorkflowSearchResult(
            unresolved_requirements=["no active workflow path nodes projected from G1"]
        ),
        skill_contexts=[],
    )

    assert plan.selected_workflow_path_id is None
    assert plan.steps[0].objective == task.user_goal
    assert plan.steps[0].expected_outputs == ["result.csv"]
