from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from lattice.schemas.common import ExecutionIntent, LatticeBaseModel

ResearchMode = Literal[
    "routine",
    "adaptive",
    "exploratory",
    "capability_expansion",
]


class TaskFingerprint(LatticeBaseModel):
    fingerprint_id: str
    user_id: str
    task: str
    task_category: str
    data_types: list[str] = Field(default_factory=list)
    input_formats: list[str] = Field(default_factory=list)
    output_goals: list[str] = Field(default_factory=list)
    execution_intent: ExecutionIntent = "plan_only"
    research_mode: ResearchMode = "adaptive"
    environment_constraints: dict[str, Any] = Field(default_factory=dict)
    preference_scope: dict[str, Any] = Field(default_factory=dict)
    ambiguity_items: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchTask(LatticeBaseModel):
    task_id: str
    fingerprint_id: str
    user_goal: str
    research_mode: ResearchMode
    input_artifacts: list[str] = Field(default_factory=list)
    output_goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    candidate_task_tags: list[str] = Field(default_factory=list)
    candidate_method_tags: list[str] = Field(default_factory=list)
    candidate_tool_names: list[str] = Field(default_factory=list)
    ambiguity_items: list[str] = Field(default_factory=list)
