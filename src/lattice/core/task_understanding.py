from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from lattice.schemas import ExecutionIntent, ResearchMode, ResearchTask, TaskFingerprint

_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\[^\s\"']+|(?:\.{0,2}/|/)[^\s\"']+)",
)
_FORMAT_PATTERN = re.compile(
    r"\.(csv|tsv|json|jsonl|txt|pdf|html|xml|yaml|yml|parquet|xlsx|"
    r"fa|fasta|fq|fastq|bam|vcf)(?:\.gz)?\b",
    re.IGNORECASE,
)


class TaskUnderstandingAgent:
    """Create a conservative, domain-general task model without inventing missing facts."""

    def understand(
        self,
        request: str,
        *,
        user_id: str = "local",
        execution_intent: ExecutionIntent = "plan_only",
    ) -> tuple[TaskFingerprint, ResearchTask]:
        normalized = request.strip()
        fingerprint_id = f"tf-{uuid4()}"
        artifacts = _extract_artifacts(normalized)
        formats = _extract_formats(normalized, artifacts)
        output_goals = _extract_output_goals(normalized)
        mode = _classify_research_mode(normalized, artifacts, output_goals)
        task_tags = _extract_tags(normalized)
        ambiguities = _ambiguities(artifacts, output_goals, execution_intent)

        fingerprint = TaskFingerprint(
            fingerprint_id=fingerprint_id,
            user_id=user_id,
            task=normalized,
            task_category=task_tags[0] if task_tags else "general_research",
            data_types=formats,
            input_formats=formats,
            output_goals=output_goals,
            execution_intent=execution_intent,
            research_mode=mode,
            ambiguity_items=ambiguities,
        )
        research_task = ResearchTask(
            task_id=f"research-task-{uuid4()}",
            fingerprint_id=fingerprint_id,
            user_goal=normalized,
            research_mode=mode,
            input_artifacts=artifacts,
            output_goals=output_goals,
            constraints=_extract_constraints(normalized),
            success_criteria=_success_criteria(output_goals),
            candidate_task_tags=task_tags,
            ambiguity_items=ambiguities,
        )
        return fingerprint, research_task


def _extract_artifacts(request: str) -> list[str]:
    return list(
        dict.fromkeys(
            match.rstrip(".,;，。；") for match in _PATH_PATTERN.findall(request)
        )
    )


def _extract_formats(request: str, artifacts: list[str]) -> list[str]:
    values = [match.lower() for match in _FORMAT_PATTERN.findall(request)]
    for artifact in artifacts:
        suffixes = Path(artifact).suffixes
        if suffixes:
            values.append("".join(suffixes).lstrip(".").lower())
    return list(dict.fromkeys(values))


def _extract_output_goals(request: str) -> list[str]:
    lowered = request.lower()
    goals: list[str] = []
    vocabulary = {
        "report": ("report", "报告", "汇报"),
        "table": ("table", "csv", "tsv", "表格"),
        "visualization": ("plot", "chart", "figure", "可视化", "图表"),
        "model": ("model", "模型"),
        "analysis_result": ("analyze", "analysis", "分析", "结果"),
        "hypothesis": ("hypothesis", "假设", "机制"),
    }
    for goal, markers in vocabulary.items():
        if any(marker in lowered for marker in markers):
            goals.append(goal)
    return goals


def _classify_research_mode(
    request: str,
    artifacts: list[str],
    output_goals: list[str],
) -> ResearchMode:
    lowered = request.lower()
    if any(
        marker in lowered
        for marker in ("new tool", "discover tool", "install", "新工具", "能力扩展", "找工具")
    ):
        return "capability_expansion"
    if any(
        marker in lowered
        for marker in ("hypothesis", "novel", "mechanism", "假设", "新机制", "探索", "发现")
    ):
        return "exploratory"
    if artifacts and output_goals:
        return "routine"
    return "adaptive"


def _extract_tags(request: str) -> list[str]:
    lowered = request.lower()
    tags = []
    vocabulary = {
        "data_analysis": ("analyze", "analysis", "分析"),
        "literature_research": ("paper", "literature", "论文", "文献"),
        "visualization": ("plot", "chart", "figure", "画图", "可视化"),
        "modeling": ("model", "train", "模型", "训练"),
        "scientific_discovery": ("hypothesis", "mechanism", "假设", "机制"),
    }
    for tag, markers in vocabulary.items():
        if any(marker in lowered for marker in markers):
            tags.append(tag)
    return tags


def _extract_constraints(request: str) -> list[str]:
    lowered = request.lower()
    constraints = []
    if any(marker in lowered for marker in ("offline", "no network", "离线", "不能联网")):
        constraints.append("network access is not allowed")
    if any(marker in lowered for marker in ("read only", "readonly", "只读")):
        constraints.append("input artifacts must remain read-only")
    return constraints


def _ambiguities(
    artifacts: list[str],
    output_goals: list[str],
    execution_intent: ExecutionIntent,
) -> list[str]:
    ambiguities = []
    if execution_intent == "execute" and not artifacts:
        ambiguities.append("input_artifacts")
    if not output_goals:
        ambiguities.append("output_goals")
    return ambiguities


def _success_criteria(output_goals: list[str]) -> list[str]:
    if not output_goals:
        return ["the requested research objective is addressed with traceable outputs"]
    return [f"produce a verifiable {goal} artifact" for goal in output_goals]
