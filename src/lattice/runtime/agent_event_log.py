from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field

from lattice.schemas.common import LatticeBaseModel, Provenance

AgentEventType = Literal[
    "UserRequestReceived",
    "SessionStart",
    "TaskFingerprinted",
    "TaskUnderstood",
    "RuntimeGraphContextProjected",
    "SkillContextResolved",
    "ResearchStrategyFormulated",
    "PreWorkflowSearch",
    "PostWorkflowSearch",
    "WorkflowPathSelected",
    "PreWorkflowVerification",
    "PostWorkflowVerification",
    "WorkflowVerified",
    "PlanModeEntered",
    "PlanModeExited",
    "PermissionChecked",
    "ScriptGenerated",
    "ScriptReviewed",
    "ScriptExecuted",
    "RunRecordCreated",
    "ResultVerified",
    "ExperienceGeneralizationEvaluated",
    "PreToolCall",
    "PostToolCall",
    "PostToolCallFailure",
    "ToolCallStarted",
    "ToolCallCompleted",
    "ToolCallFailed",
    "ObservationParsed",
    "PreClaimVerification",
    "PostClaimVerification",
    "ClaimVerified",
    "ExperienceCandidateCreated",
    "CapabilityGapDetected",
    "EvolutionRequested",
    "RuntimeCapabilityDiscoveryStarted",
    "RuntimeCapabilityDiscoveryCompleted",
    "CandidateToolCreated",
    "ToolCallSpecCandidateCreated",
    "PreGraphPatch",
    "PostGraphPatch",
    "GraphPatchProposed",
    "GraphPatchApproved",
    "GraphPatchRejected",
    "PreGraphWrite",
    "PostGraphWrite",
    "GraphPatchWritten",
    "PreMemoryHealthCompile",
    "PostMemoryHealthCompile",
    "MemoryHealthCompileStarted",
    "MemoryHealthCompileCompleted",
    "SessionEnd",
]


class AgentEvent(LatticeBaseModel):
    event_id: str
    session_id: str
    event_type: AgentEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(min_length=1)
    graph_patch_ids: list[str] = Field(default_factory=list)
    l6_node_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentEventLog(Protocol):
    def append(self, event: AgentEvent) -> None:
        """Append one event without mutating existing events."""

    def read_all(self) -> list[AgentEvent]:
        """Read events in append order."""


class FileAgentEventLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: AgentEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = event.model_dump(mode="json")
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            file.write("\n")

    def read_all(self) -> list[AgentEvent]:
        if not self.path.exists():
            return []

        events: list[AgentEvent] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                stripped = line.strip()
                if stripped:
                    events.append(AgentEvent.model_validate(json.loads(stripped)))
        return events
