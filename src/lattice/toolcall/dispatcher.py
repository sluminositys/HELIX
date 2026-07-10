from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from lattice.schemas import AgenticExecutionStep, Provenance, StructuredObservation
from lattice.toolcall.backends import RuntimeBackend
from lattice.toolcall.registry import ToolCallRegistry, ToolCallRegistryError
from lattice.toolcall.validator import ToolCallValidator


class ToolCallDispatcher:
    def __init__(
        self,
        *,
        registry: ToolCallRegistry,
        backends: Mapping[str, RuntimeBackend] | None = None,
    ) -> None:
        self.registry = registry
        self.backends = dict(backends or {})
        self.validator = ToolCallValidator(registry)

    def dispatch(self, step: AgenticExecutionStep) -> StructuredObservation:
        toolcall_event_id = f"toolcall-event-{uuid4()}"
        spec_id = step.toolcall_spec_id
        if spec_id is None:
            return _failure_observation(
                toolcall_event_id=toolcall_event_id,
                error_class="ToolCallValidationFailed",
                reason="Legacy ToolCall execution requires toolcall_spec_id.",
            )
        validation = self.validator.validate_step(step)
        if validation.status == "blocked":
            return _failure_observation(
                toolcall_event_id=toolcall_event_id,
                error_class="ToolCallValidationFailed",
                reason="; ".join(validation.blockers),
            )

        try:
            spec = self.registry.require_active(spec_id)
        except ToolCallRegistryError as error:
            return _failure_observation(
                toolcall_event_id=toolcall_event_id,
                error_class="ToolCallRegistryError",
                reason=str(error),
            )

        backend = self.backends.get(spec.runtime_backend)
        if backend is None:
            return _failure_observation(
                toolcall_event_id=toolcall_event_id,
                error_class="RuntimeBackendUnavailable",
                reason=f"No runtime backend registered: {spec.runtime_backend}",
            )

        return backend.execute(step=step, spec=spec, toolcall_event_id=toolcall_event_id)


def _failure_observation(
    *,
    toolcall_event_id: str,
    error_class: str,
    reason: str,
) -> StructuredObservation:
    return StructuredObservation(
        observation_id=f"obs-{uuid4()}",
        toolcall_event_id=toolcall_event_id,
        status="failure",
        error_class=error_class,
        parsed_summary={"reason": reason},
        provenance=Provenance(source_type="toolcall_dispatcher"),
    )
