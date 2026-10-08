"""Domain ports: the gate depends on these abstractions, never on a specific ML/LLM library."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from .entities import AgentAction, AuditRecord


class RiskAssessor(Protocol):
    """Supplies a risk *estimate* in [0, 1] (or None if unavailable). It is not the decision authority."""

    model_version: str

    def assess(self, request_text: str, tool_name: str, tool_arguments: Mapping[str, Any]) -> Optional[float]: ...


class ToolExecutor(Protocol):
    """Outside the trust boundary. Raises on failure."""

    def execute(self, action: AgentAction) -> None: ...


class AuditStore(Protocol):
    def next_audit_id(self) -> str: ...

    def append(self, record: AuditRecord) -> None: ...

    def records_for(self, action_id: str) -> Sequence[AuditRecord]: ...


Clock = Callable[[], datetime]
