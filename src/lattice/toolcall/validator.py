from __future__ import annotations

from typing import Literal

from pydantic import Field

from lattice.schemas import AgenticExecutionStep, LatticeBaseModel
from lattice.toolcall.registry import ToolCallRegistry, ToolCallRegistryError


class ToolCallValidationReport(LatticeBaseModel):
    toolcall_spec_id: str
    status: Literal["pass", "blocked"]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ToolCallValidator:
    def __init__(self, registry: ToolCallRegistry) -> None:
        self.registry = registry

    def validate_step(self, step: AgenticExecutionStep) -> ToolCallValidationReport:
        blockers: list[str] = []
        warnings: list[str] = []
        spec_id = step.toolcall_spec_id
        if spec_id is None:
            return ToolCallValidationReport(
                toolcall_spec_id="missing",
                status="blocked",
                blockers=["Legacy ToolCall execution requires toolcall_spec_id."],
            )

        try:
            spec = self.registry.require_active(spec_id)
        except ToolCallRegistryError as error:
            return ToolCallValidationReport(
                toolcall_spec_id=spec_id,
                status="blocked",
                blockers=[str(error)],
            )

        blockers.extend(_missing_required_keys(spec.input_schema, step.input_bindings, "input"))
        blockers.extend(
            _missing_required_keys(spec.parameter_schema, step.parameter_bindings, "parameter")
        )

        if not spec.output_schema:
            warnings.append("ToolCallSpec has no output_schema.")

        status: Literal["pass", "blocked"] = "blocked" if blockers else "pass"
        return ToolCallValidationReport(
            toolcall_spec_id=spec_id,
            status=status,
            blockers=blockers,
            warnings=warnings,
        )


def _missing_required_keys(
    schema: dict[str, object],
    bindings: dict[str, object],
    label: str,
) -> list[str]:
    required = schema.get("required", [])
    if not isinstance(required, list):
        return [f"{label}_schema.required must be a list."]

    missing: list[str] = []
    for key in required:
        if not isinstance(key, str):
            missing.append(f"{label}_schema.required contains non-string key.")
        elif key not in bindings:
            missing.append(f"Missing required {label} binding: {key}")
    return missing
