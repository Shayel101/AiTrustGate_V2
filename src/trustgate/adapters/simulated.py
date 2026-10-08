"""In-memory, simulated adapters. Nothing here performs a real side effect."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from ..entities import AgentAction, AuditRecord
from ..errors import ValidationError


class TickingClock:
    """Deterministic clock: each call advances by a fixed step (default 1 s)."""

    def __init__(self, start: Optional[datetime] = None, step: timedelta = timedelta(seconds=1)) -> None:
        self._now = start or datetime(2026, 10, 8, 9, 0, 0, tzinfo=timezone.utc)
        self._step = step

    def __call__(self) -> datetime:
        now = self._now
        self._now += self._step
        return now


class FixedRiskAssessor:
    """STIPULATED scores (not model output) for synthetic scenarios and tests."""

    def __init__(self, scores: Mapping[str, Optional[float]] | None = None, default: Optional[float] = 0.0,
                 model_version: str = "stipulated-fixed-scores") -> None:
        self._scores = dict(scores or {})
        self._default = default
        self.model_version = model_version

    def assess(self, request_text: str, tool_name: str, tool_arguments: Mapping[str, Any]) -> Optional[float]:
        return self._scores.get(request_text, self._default)


class SimulatedToolExecutor:
    """Records calls; never does anything. Optionally fails for chosen action ids."""

    def __init__(self, failing_action_ids: frozenset[str] = frozenset()) -> None:
        self.executed: list[str] = []
        self._failing = failing_action_ids

    def execute(self, action: AgentAction) -> None:
        if action.action_id in self._failing:
            raise RuntimeError("simulated tool failure")
        self.executed.append(action.action_id)


class InMemoryAuditStore:
    """Append-only; rejects duplicate audit ids and per-action timestamps that go backwards."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._ids: set[str] = set()

    def next_audit_id(self) -> str:
        return f"AUD-{len(self._records) + 1:06d}"

    def append(self, record: AuditRecord) -> None:
        if not isinstance(record, AuditRecord):
            raise ValidationError("audit store accepts AuditRecord only")
        if record.audit_id in self._ids:
            raise ValidationError(f"duplicate audit_id {record.audit_id}")
        previous = self.records_for(record.action_id)
        if previous and record.timestamp < previous[-1].timestamp:
            raise ValidationError("audit timestamp goes backwards for this action")
        self._records.append(record)
        self._ids.add(record.audit_id)

    def records_for(self, action_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.action_id == action_id]

    def all_records(self) -> list[AuditRecord]:
        return list(self._records)
