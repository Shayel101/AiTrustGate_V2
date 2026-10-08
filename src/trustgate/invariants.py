"""Executable domain invariants (docs/a2/invariants.md). Each returns True when the invariant HOLDS.

They are pure predicates over an AgentAction (+ audit records / policy), so a violating state can be
constructed in tests and detected without going through the guarded transition methods.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from .entities import AgentAction, AuditRecord
from .errors import InvariantViolation
from .policy import PolicyConfig, decide
from .values import (
    EXECUTION_STATES,
    TERMINAL_STATES,
    ActionState,
    ApprovalStatus,
    AuthorizationStatus,
    DecisionType,
    EventType,
)

_EXEC_EVENTS = {
    EventType.TOOL_EXECUTION_STARTED,
    EventType.TOOL_EXECUTION_COMPLETED,
    EventType.TOOL_EXECUTION_FAILED,
}


def _started_execution(action: AgentAction) -> bool:
    return action.state in EXECUTION_STATES or any(e.event in _EXEC_EVENTS for e in action.history)


def inv_blocked_never_executes(action: AgentAction) -> bool:
    """INV-01: a BLOCK decision never reaches execution and never carries authorization."""
    if action.decision is None or action.decision.decision is not DecisionType.BLOCK:
        return True
    return (
        action.state is ActionState.BLOCKED
        and not _started_execution(action)
        and action.authorization is AuthorizationStatus.NOT_AUTHORIZED
    )


def inv_review_requires_granted_approval(action: AgentAction) -> bool:
    """INV-02: a REVIEW action executes only after a GRANTED approval that names a reviewer."""
    if action.decision is None or action.decision.decision is not DecisionType.REVIEW:
        return True
    if not _started_execution(action):
        return True
    a = action.approval
    return a is not None and a.status is ApprovalStatus.GRANTED and bool(a.reviewer_id)


def inv_execution_requires_authorization(action: AgentAction) -> bool:
    """INV-03: execution requires AUTHORIZED, and AUTHORIZED is only derivable from ALLOW or a granted approval."""
    if _started_execution(action):
        if action.decision is None or action.authorization is not AuthorizationStatus.AUTHORIZED:
            return False
    if action.authorization is AuthorizationStatus.AUTHORIZED:
        d = action.decision
        if d is None:
            return False
        if d.decision is DecisionType.ALLOW:
            return True
        return (
            d.decision is DecisionType.REVIEW
            and action.approval is not None
            and action.approval.status is ApprovalStatus.GRANTED
        )
    return True


def inv_decision_matches_policy(action: AgentAction, policy: PolicyConfig) -> bool:
    """INV-04: the recorded decision equals the policy function applied to the recorded inputs."""
    d = action.decision
    if d is None:
        return True
    expected = decide(action.risk_score, policy.side_effect_for(action.tool_name), policy, action.model_version)
    return d == expected and d.risk_score == action.risk_score


def inv_audit_complete(action: AgentAction, records: Sequence[AuditRecord]) -> bool:
    """INV-05: every event in the action history (hence every decision and terminal state) has an audit record."""
    seen = {(r.action_id, r.event, r.to_state) for r in records}
    return all((action.action_id, e.event, e.to_state) in seen for e in action.history)


def inv_execution_once_and_terminal_final(action: AgentAction) -> bool:
    """INV-06: ToolExecutionStarted occurs at most once and nothing follows a terminal state."""
    started = sum(1 for e in action.history if e.event is EventType.TOOL_EXECUTION_STARTED)
    if started > 1:
        return False
    for e in action.history[:-1]:
        if e.to_state in TERMINAL_STATES:
            return False
    return True


def check_all(
    action: AgentAction,
    records: Sequence[AuditRecord],
    policy: PolicyConfig,
) -> list[str]:
    """Return the IDs of all violated invariants (empty list = all hold)."""
    checks: list[tuple[str, Callable[[], bool]]] = [
        ("INV-01", lambda: inv_blocked_never_executes(action)),
        ("INV-02", lambda: inv_review_requires_granted_approval(action)),
        ("INV-03", lambda: inv_execution_requires_authorization(action)),
        ("INV-04", lambda: inv_decision_matches_policy(action, policy)),
        ("INV-05", lambda: inv_audit_complete(action, records)),
        ("INV-06", lambda: inv_execution_once_and_terminal_final(action)),
    ]
    return [inv_id for inv_id, fn in checks if not fn()]


def assert_invariants(action: AgentAction, records: Sequence[AuditRecord], policy: PolicyConfig) -> None:
    violated = check_all(action, records, policy)
    if violated:
        raise InvariantViolation(f"action {action.action_id}: violated {', '.join(violated)}")


__all__ = [
    "inv_blocked_never_executes",
    "inv_review_requires_granted_approval",
    "inv_execution_requires_authorization",
    "inv_decision_matches_policy",
    "inv_audit_complete",
    "inv_execution_once_and_terminal_final",
    "check_all",
    "assert_invariants",
]
