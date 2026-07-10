from pathlib import Path

from lattice.runtime import ScriptReviewAgent, ScriptRunner
from lattice.schemas import ScriptProposal


def test_script_review_blocks_undeclared_network_import() -> None:
    proposal = ScriptProposal(
        proposal_id="script-1",
        plan_id="plan-1",
        script_text="import requests\nprint(requests.get('https://example.com'))\n",
        covered_step_ids=["step-1"],
        permission_requirements={"network": False},
    )

    review = ScriptReviewAgent().review(proposal)

    assert review.status == "blocked"
    assert "undeclared network-capable imports" in review.blockers[0]


def test_script_review_blocks_undeclared_subprocess() -> None:
    proposal = ScriptProposal(
        proposal_id="script-1",
        plan_id="plan-1",
        script_text="import subprocess\nsubprocess.run(['tool', '--version'])\n",
        covered_step_ids=["step-1"],
        permission_requirements={"shell": False},
    )

    review = ScriptReviewAgent().review(proposal)

    assert review.status == "blocked"
    assert "without declared shell permission" in review.blockers[0]


def test_script_review_requests_revision_for_absolute_path_write() -> None:
    proposal = ScriptProposal(
        proposal_id="script-1",
        plan_id="plan-1",
        script_text=(
            "from pathlib import Path\n"
            "Path('C:/outside.txt').write_text('result', encoding='utf-8')\n"
        ),
        covered_step_ids=["step-1"],
    )

    review = ScriptReviewAgent().review(proposal)

    assert review.status == "needs_revision"
    assert "task working directory" in review.required_revisions[0]


def test_script_runner_preserves_run_files(tmp_path: Path) -> None:
    proposal = ScriptProposal(
        proposal_id="script-1",
        plan_id="plan-1",
        script_text=(
            "from pathlib import Path\n"
            "Path('result.txt').write_text('done', encoding='utf-8')\n"
        ),
        covered_step_ids=["step-1"],
    )

    result = ScriptRunner(output_root=tmp_path).run(proposal)

    assert result.status == "success"
    assert result.stdout_path is not None and Path(result.stdout_path).exists()
    assert any(Path(path).name == "result.txt" for path in result.artifact_paths)
