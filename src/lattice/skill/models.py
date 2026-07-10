from __future__ import annotations

from typing import Any

from pydantic import Field

from lattice.schemas import LatticeBaseModel


class SkillContext(LatticeBaseModel):
    primary_skill: dict[str, Any]
    parameter_guidance: list[dict[str, Any]] = Field(default_factory=list)
    environment_specs: list[dict[str, Any]] = Field(default_factory=list)
    failure_modes: list[dict[str, Any]] = Field(default_factory=list)
    usage_constraints: list[dict[str, Any]] = Field(default_factory=list)
    recovery_strategies: list[dict[str, Any]] = Field(default_factory=list)
    quality_checkpoints: list[dict[str, Any]] = Field(default_factory=list)
    related_resource_nodes: list[dict[str, Any]] = Field(default_factory=list)
    related_experience_nodes: list[dict[str, Any]] = Field(default_factory=list)
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    readiness_state: str = "unknown"
    relevance_score: float = 0.0
