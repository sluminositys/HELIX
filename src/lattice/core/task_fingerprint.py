from __future__ import annotations

from pathlib import Path

from lattice.core.task_understanding import TaskUnderstandingAgent
from lattice.schemas import ExecutionIntent, TaskFingerprint


class TaskFingerprinter:
    """Compatibility facade over the domain-general task-understanding agent."""

    def __init__(self, prompt_path: str | Path = "config/prompts/task_fingerprint.md") -> None:
        self.prompt_path = Path(prompt_path)

    def fingerprint(
        self,
        request: str,
        *,
        user_id: str = "local",
        execution_intent: ExecutionIntent = "plan_only",
    ) -> TaskFingerprint:
        fingerprint, _ = TaskUnderstandingAgent().understand(
            request,
            user_id=user_id,
            execution_intent=execution_intent,
        )
        return fingerprint
