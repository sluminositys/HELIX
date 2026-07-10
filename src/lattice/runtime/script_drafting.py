from __future__ import annotations

import re
from typing import Protocol


class ScriptDraftError(RuntimeError):
    pass


class ScriptDraftProvider(Protocol):
    def draft(self, prompt: str) -> str:
        """Return one executable script without markdown narration."""


class UnavailableScriptDraftProvider:
    def __init__(self, reason: str = "No chat model is configured for script generation.") -> None:
        self.reason = reason

    def draft(self, prompt: str) -> str:
        _ = prompt
        raise ScriptDraftError(self.reason)


class StaticScriptDraftProvider:
    """Deterministic adapter used by tests and explicit offline integrations."""

    def __init__(self, script_text: str) -> None:
        self.script_text = script_text

    def draft(self, prompt: str) -> str:
        _ = prompt
        return self.script_text


class LangChainScriptDraftProvider:
    def __init__(self, *, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model

    def draft(self, prompt: str) -> str:
        try:
            from langchain.chat_models import init_chat_model
        except ImportError as error:
            raise ScriptDraftError("LangChain chat model initialization is unavailable.") from error

        try:
            chat_model = init_chat_model(
                self.model,
                model_provider=self.provider,
                temperature=0,
            )
            response = chat_model.invoke(prompt)
        except Exception as error:  # provider packages expose heterogeneous errors
            raise ScriptDraftError(f"Script model invocation failed: {error}") from error

        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "\n".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        script = _strip_markdown_fence(str(content))
        if not script.strip():
            raise ScriptDraftError("Script model returned empty content.")
        return script


def _strip_markdown_fence(value: str) -> str:
    stripped = value.strip()
    match = re.fullmatch(
        r"```(?:python|py|bash|sh|r)?\s*(.*?)\s*```",
        stripped,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else stripped
