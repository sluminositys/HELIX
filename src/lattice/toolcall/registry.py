from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from lattice.schemas import RuntimeGraphContext, RuntimeLayerView, ToolCallSpec


class ToolCallRegistryError(ValueError):
    pass


class ToolCallRegistry:
    active_lifecycle_states = frozenset({"active_hot", "active_warm"})

    def __init__(self, specs: Iterable[ToolCallSpec] = ()) -> None:
        self._specs = {spec.toolcall_spec_id: spec for spec in specs}

    @classmethod
    def from_runtime_context(cls, runtime_context: RuntimeGraphContext) -> ToolCallRegistry:
        specs: list[ToolCallSpec] = []
        for node in _runtime_nodes(runtime_context.G_resource):
            attributes = node.get("attributes", {})
            if not isinstance(attributes, dict):
                continue
            if node.get("node_type") == "ToolCallSpec":
                _append_spec(specs, attributes)
        return cls(specs)

    def get(self, toolcall_spec_id: str) -> ToolCallSpec | None:
        return self._specs.get(toolcall_spec_id)

    def with_specs(self, specs: Iterable[ToolCallSpec]) -> ToolCallRegistry:
        merged = [*self._specs.values(), *specs]
        return ToolCallRegistry(merged)

    def require_active(self, toolcall_spec_id: str) -> ToolCallSpec:
        spec = self.get(toolcall_spec_id)
        if spec is None:
            msg = f"ToolCallSpec is not registered: {toolcall_spec_id}"
            raise ToolCallRegistryError(msg)

        if spec.lifecycle_state not in self.active_lifecycle_states:
            msg = (
                "ToolCallSpec is registered but not active: "
                f"{toolcall_spec_id} ({spec.lifecycle_state})"
            )
            raise ToolCallRegistryError(msg)
        return spec


def _runtime_nodes(view: RuntimeLayerView | dict[str, Any]) -> list[dict[str, Any]]:
    nodes = view.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


def _append_spec(specs: list[ToolCallSpec], payload: dict[str, Any]) -> None:
    try:
        specs.append(ToolCallSpec.model_validate(payload))
    except ValidationError:
        return
