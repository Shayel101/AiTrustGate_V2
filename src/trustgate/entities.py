"""Entities of the AI Trust Gate domain: AgentAction (central lifecycle), ApprovalRequest, AuditRecord.

The state model is docs/a2/state_model.md; TRANSITIONS below is checked against it by tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional

from .errors import AuthorizationError, InvalidTransitionError, ValidationError
from .values import (
    TERMINAL_STATES,
    ActionState,
    ApprovalStatus,
    AuthorizationStatus,
    DecisionType,
    EventType,
    RiskScore,
    TrustDecision,
    ensure_utc,
    normalize_text,
    normalize_tool_name,
    sha256_text,
    validate_identifier,
)

S = ActionState
E = EventType

TRANSITIONS: dict[tuple[ActionState, EventType], frozenset[ActionState]] = {
    (S.PROPOSED, E.ACTION_NORMALIZED): frozenset({S.NORMALIZED}),
    (S.NORMALIZED, E.RISK_ASSESSED): frozenset({S.RISK_ASSESSED}),
    (S.RISK_ASSESSED, E.ACTION_ALLOWED): frozenset({S.ALLOWED}),
    (S.RISK_ASSESSED, E.HUMAN_APPROVAL_REQUESTED): frozenset({S.PENDING_APPROVAL}),
    (S.RISK_ASSESSED, E.ACTION_BLOCKED): frozenset({S.BLOCKED}),
    (S.PENDING_APPROVAL, E.HUMAN_APPROVAL_GRANTED): frozenset({S.APPROVED}),
    (S.PENDING_APPROVAL, E.HUMAN_APPROVAL_REJECTED): frozenset({S.REJECTED}),
    (S.ALLOWED, E.TOOL_EXECUTION_STARTED): frozenset({S.EXECUTING}),
    (S.APPROVED, E.TOOL_EXECUTION_STARTED): frozenset({S.EXECUTING}),
    (S.EXECUTING, E.TOOL_EXECUTION_COMPLETED): frozenset({S.EXECUTED}),
    (S.EXECUTING, E.TOOL_EXECUTION_FAILED): frozenset({S.EXECUTION_FAILED}),
}

_DECISION_EVENT = {
    DecisionType.ALLOW: (E.ACTION_ALLOWED, S.ALLOWED),
    DecisionType.REVIEW: (E.HUMAN_APPROVAL_REQUESTED, S.PENDING_APPROVAL),
    DecisionType.BLOCK: (E.ACTION_BLOCKED, S.BLOCKED),
}


@dataclass(frozen=True)
class ActionEvent:
    event: EventType
    from_state: Optional[ActionState]
    to_state: ActionState
    at: datetime
    detail: str = ""


@dataclass
class ApprovalRequest:
    approval_id: str
    action_id: str
    requested_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_id: Optional[str] = None
    decided_at: Optional[datetime] = None

    def decide(self, status: ApprovalStatus, reviewer_id: str, at: datetime) -> None:
        if self.status is not ApprovalStatus.PENDING:
            raise InvalidTransitionError(f"approval {self.approval_id} is already {self.status.value}")
        if status not in (ApprovalStatus.GRANTED, ApprovalStatus.REJECTED):
            raise ValidationError("approval can only be decided as GRANTED or REJECTED")
        self.reviewer_id = validate_identifier(reviewer_id, "reviewer_id")
        self.decided_at = ensure_utc(at, "timestamp")
        self.status = status


@dataclass
class AgentAction:
    """A proposed action awaiting trust-gate evaluation (A1: 'request' sent to the AI system)."""

    action_id: str
    request_id: str
    request_text: str
    tool_name: str
    tool_arguments: dict[str, Any]
    state: ActionState = ActionState.PROPOSED
    risk_score: Optional[RiskScore] = None
    model_version: Optional[str] = None
    decision: Optional[TrustDecision] = None
    authorization: AuthorizationStatus = AuthorizationStatus.NOT_AUTHORIZED
    approval: Optional[ApprovalRequest] = None
    history: list[ActionEvent] = field(default_factory=list)

    @classmethod
    def propose(
        cls,
        *,
        action_id: object,
        request_id: object,
        request_text: object,
        tool_name: object,
        tool_arguments: Optional[Mapping[str, Any]] = None,
        at: datetime,
    ) -> "AgentAction":
        args = {} if tool_arguments is None else tool_arguments
        if not isinstance(args, Mapping) or not all(isinstance(k, str) and k for k in args):
            raise ValidationError("tool_arguments: expected a mapping with non-empty string keys")
        action = cls(
            action_id=validate_identifier(action_id, "action_id"),
            request_id=validate_identifier(request_id, "request_id"),
            request_text=normalize_text(request_text, "request_text"),
            tool_name=normalize_tool_name(tool_name),
            tool_arguments=dict(args),
        )
        ts = ensure_utc(at, "timestamp")
        action.history.append(ActionEvent(E.ACTION_PROPOSED, None, S.PROPOSED, ts))
        return action

    @property
    def text_sha256(self) -> str:
        return sha256_text(self.request_text)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    # --- transition plumbing -------------------------------------------------
    def _prepare(self, event: EventType, to_state: ActionState, at: datetime) -> datetime:
        if to_state not in TRANSITIONS.get((self.state, event), frozenset()):
            raise InvalidTransitionError(f"{self.state.value} --{event.value}--> {to_state.value} is not allowed")
        ts = ensure_utc(at, "timestamp")
        if self.history and ts < self.history[-1].at:
            raise ValidationError("timestamp is earlier than the previous event")
        return ts

    def _commit(self, event: EventType, to_state: ActionState, ts: datetime, detail: str = "") -> None:
        self.history.append(ActionEvent(event, self.state, to_state, ts, detail))
        self.state = to_state

    # --- events --------------------------------------------------------------
    def normalize(self, at: datetime) -> None:
        ts = self._prepare(E.ACTION_NORMALIZED, S.NORMALIZED, at)
        self.request_text = normalize_text(self.request_text, "request_text")
        self.tool_name = normalize_tool_name(self.tool_name)
        self._commit(E.ACTION_NORMALIZED, S.NORMALIZED, ts)

    def record_risk(self, score: Optional[RiskScore], model_version: Optional[str], at: datetime) -> None:
        """score=None means the assessor reported no usable estimate (fails closed in the policy)."""
        ts = self._prepare(E.RISK_ASSESSED, S.RISK_ASSESSED, at)
        if score is not None and not isinstance(score, RiskScore):
            raise ValidationError("risk_score must be a RiskScore or None")
        self.risk_score = score
        self.model_version = model_version
        self._commit(E.RISK_ASSESSED, S.RISK_ASSESSED, ts, "unavailable" if score is None else "")

    def apply_decision(self, decision: TrustDecision, at: datetime) -> None:
        if not isinstance(decision, TrustDecision):
            raise ValidationError("decision must be a TrustDecision")
        event, to_state = _DECISION_EVENT[decision.decision]
        ts = self._prepare(event, to_state, at)
        if decision.risk_score != self.risk_score:
            raise ValidationError("decision was derived from a different risk score than the recorded one")
        self.decision = decision
        if decision.decision is DecisionType.ALLOW:
            self.authorization = AuthorizationStatus.AUTHORIZED
        elif decision.decision is DecisionType.REVIEW:
            self.approval = ApprovalRequest(f"APR-{self.action_id}", self.action_id, ts)
        self._commit(event, to_state, ts, decision.rule_id)

    def grant_approval(self, reviewer_id: str, at: datetime) -> None:
        ts = self._prepare(E.HUMAN_APPROVAL_GRANTED, S.APPROVED, at)
        assert self.approval is not None, "PENDING_APPROVAL always has an ApprovalRequest"
        self.approval.decide(ApprovalStatus.GRANTED, reviewer_id, ts)
        self.authorization = AuthorizationStatus.AUTHORIZED
        self._commit(E.HUMAN_APPROVAL_GRANTED, S.APPROVED, ts)

    def reject_approval(self, reviewer_id: str, at: datetime) -> None:
        ts = self._prepare(E.HUMAN_APPROVAL_REJECTED, S.REJECTED, at)
        assert self.approval is not None, "PENDING_APPROVAL always has an ApprovalRequest"
        self.approval.decide(ApprovalStatus.REJECTED, reviewer_id, ts)
        self._commit(E.HUMAN_APPROVAL_REJECTED, S.REJECTED, ts)

    def start_execution(self, at: datetime) -> None:
        ts = self._prepare(E.TOOL_EXECUTION_STARTED, S.EXECUTING, at)
        if self.authorization is not AuthorizationStatus.AUTHORIZED:
            raise AuthorizationError("execution requires authorization")
        self._commit(E.TOOL_EXECUTION_STARTED, S.EXECUTING, ts)

    def complete_execution(self, at: datetime) -> None:
        ts = self._prepare(E.TOOL_EXECUTION_COMPLETED, S.EXECUTED, at)
        self._commit(E.TOOL_EXECUTION_COMPLETED, S.EXECUTED, ts)

    def fail_execution(self, at: datetime) -> None:
        ts = self._prepare(E.TOOL_EXECUTION_FAILED, S.EXECUTION_FAILED, at)
        self._commit(E.TOOL_EXECUTION_FAILED, S.EXECUTION_FAILED, ts)


@dataclass(frozen=True)
class AuditRecord:
    """Immutable, append-only record of one AgentAction event. Holds a text digest, never the text."""

    audit_id: str
    action_id: str
    request_id: str
    event: EventType
    from_state: Optional[ActionState]
    to_state: ActionState
    timestamp: datetime
    decision: Optional[DecisionType]
    rule_id: str
    policy_version: Optional[str]
    model_version: Optional[str]
    text_sha256: str
    tool_name: str = ""
    risk_score: Optional[float] = None

    def __post_init__(self) -> None:
        validate_identifier(self.audit_id, "audit_id")
        validate_identifier(self.action_id, "action_id")
        validate_identifier(self.request_id, "request_id")
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp, "timestamp"))
