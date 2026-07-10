from __future__ import annotations

import json
import re
from typing import Any

from lattice.schemas import ResearchTask, RuntimeGraphContext
from lattice.skill.models import SkillContext

_CHILD_EDGE_FIELDS = {
    "HAS_PARAMETER_GUIDANCE": "parameter_guidance",
    "HAS_ENVIRONMENT_SPEC": "environment_specs",
    "HAS_FAILURE_MODE": "failure_modes",
    "HAS_USAGE_CONSTRAINT": "usage_constraints",
    "HAS_RECOVERY_STRATEGY": "recovery_strategies",
    "HAS_QUALITY_CHECKPOINT": "quality_checkpoints",
}
_EXPERIENCE_TO_SKILL_EDGES = {
    "DISTILLED_TO_SKILL",
    "SUPPORTS_SKILL_UPDATE",
}


class SkillContextProvider:
    def resolve_skills_for_task(
        self,
        task: ResearchTask,
        runtime_context: RuntimeGraphContext,
        *,
        preferred_skill_ids: list[str] | None = None,
        limit: int = 8,
    ) -> list[SkillContext]:
        preferred = set(preferred_skill_ids or [])
        skill_nodes = [
            node
            for node in runtime_context.G_skill.nodes
            if node.get("node_type") == "ToolUsageSkill"
            and node.get("lifecycle_state") in {"active_hot", "active_warm", "probationary"}
        ]
        node_by_id = {
            str(node.get("node_id")): node
            for node in [
                *runtime_context.G_skill.nodes,
                *runtime_context.G_resource.nodes,
                *runtime_context.G_experience.nodes,
            ]
            if node.get("node_id")
        }
        all_edges = [
            *runtime_context.G_skill.edges,
            *runtime_context.G_resource.edges,
            *runtime_context.G_experience.edges,
            *runtime_context.cross_layer_edges,
        ]

        ranked = sorted(
            (
                (self._score(task, node, preferred), node)
                for node in skill_nodes
            ),
            key=lambda item: (-item[0], str(item[1].get("node_id", ""))),
        )
        contexts = [
            self._build_context(node, score, node_by_id, all_edges)
            for score, node in ranked[: max(limit, 0)]
            if score > 0 or not task.candidate_tool_names
        ]
        return contexts

    def format_as_prompt_context(self, skills: list[SkillContext]) -> str:
        payload = [skill.model_dump(mode="json") for skill in skills]
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    def _score(
        self,
        task: ResearchTask,
        node: dict[str, Any],
        preferred_skill_ids: set[str],
    ) -> float:
        node_id = str(node.get("node_id", ""))
        attributes = _attributes(node)
        text = " ".join(
            str(value)
            for value in (
                node.get("canonical_name", ""),
                attributes.get("tool_name", ""),
                attributes.get("purpose", ""),
                attributes.get("applicable_task_tags", ""),
                attributes.get("applicable_method_tags", ""),
            )
        ).lower()
        task_terms = _terms(
            " ".join(
                [
                    task.user_goal,
                    *task.candidate_task_tags,
                    *task.candidate_method_tags,
                    *task.candidate_tool_names,
                ]
            )
        )
        score = float(len(task_terms & _terms(text)))
        if node_id in preferred_skill_ids:
            score += 100.0
        if any(tool.lower() in text for tool in task.candidate_tool_names):
            score += 25.0
        lifecycle = node.get("lifecycle_state")
        if lifecycle == "active_hot":
            score += 3.0
        elif lifecycle == "active_warm":
            score += 2.0
        return score

    def _build_context(
        self,
        skill: dict[str, Any],
        score: float,
        node_by_id: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> SkillContext:
        skill_id = str(skill.get("node_id", ""))
        payload: dict[str, list[dict[str, Any]]] = {
            field: [] for field in _CHILD_EDGE_FIELDS.values()
        }
        resources: list[dict[str, Any]] = []
        experiences: list[dict[str, Any]] = []
        for edge in edges:
            source_id = str(edge.get("source_node_id", ""))
            target_id = str(edge.get("target_node_id", ""))
            edge_type = str(edge.get("edge_type", ""))
            if source_id == skill_id and edge_type in _CHILD_EDGE_FIELDS:
                target = node_by_id.get(target_id)
                if target is not None:
                    payload[_CHILD_EDGE_FIELDS[edge_type]].append(target)
            if target_id == skill_id and edge_type == "HAS_USAGE_SKILL":
                resource = node_by_id.get(source_id)
                if resource is not None:
                    resources.append(resource)
            if target_id == skill_id and edge_type in _EXPERIENCE_TO_SKILL_EDGES:
                experience = node_by_id.get(source_id)
                if experience is not None:
                    experiences.append(experience)

        tool_names = {
            str(_attributes(skill).get("tool_name", "")).lower(),
            *(str(_attributes(resource).get("tool_name", "")).lower() for resource in resources),
        }
        for node in node_by_id.values():
            if node.get("layer") != "experience":
                continue
            attributes = _attributes(node)
            applies_to = {
                str(name).lower() for name in attributes.get("applicable_tool_names", [])
            }
            if tool_names & applies_to:
                experiences.append(node)

        attributes = _attributes(skill)
        return SkillContext(
            primary_skill=skill,
            related_resource_nodes=_unique_nodes(resources),
            related_experience_nodes=_unique_nodes(experiences),
            provenance_summary={"source_count": len(skill.get("provenance", []))},
            readiness_state=str(attributes.get("readiness_state", "unknown")),
            relevance_score=score,
            **payload,
        )


def _attributes(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes", {})
    return value if isinstance(value, dict) else {}


def _unique_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("node_id", ""))
        if node_id:
            unique[node_id] = node
    return list(unique.values())


def _terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9_+.-]+|[\u4e00-\u9fff]+", value.lower())
        if len(term) > 1
    }
