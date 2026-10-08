"""State-machine behaviour (docs/a2/state_model.md): valid/invalid transitions, approvals, terminals, repeats."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import REVIEWER, TEXT, submit

from trustgate import (
    ActionState as S, AgentAction, ApprovalRequest, ApprovalStatus, AuthorizationError, AuthorizationStatus, DecisionType,
    EventType as E, ExternalSideEffect, InvalidTransitionError, RiskScore, TRANSITIONS, ValidationError, decide,
)
from trustgate.entities import TERMINAL_STATES
from trustgate.policy import PolicyConfig
from trustgate.values import TERMINAL_STATES as VALUE_TERMINALS

T0 = datetime(2026, 10, 8, 9, 0, 0, tzinfo=timezone.utc)
ACTION_EVENTS = [e for e in E if e not in (E.AUDIT_RECORDED, E.ACTION_PROPOSED)]  # PROPOSED is creation, AUDIT is stateless
POLICY = PolicyConfig(tool_side_effects={"llm_generate": ExternalSideEffect.NO}, reviewer_ids=frozenset({REVIEWER}))


def _fresh(state: S) -> AgentAction:
    a = AgentAction.propose(action_id="A-1", request_id="R-1", request_text=TEXT, tool_name="llm_generate", at=T0)
    a.state = state
    a.authorization = AuthorizationStatus.AUTHORIZED  # so only the STATE decides whether an event is legal
    a.approval = ApprovalRequest("APR-A-1", "A-1", T0)
    return a


def _fire(a: AgentAction, event: E) -> None:
    t = datetime(2026, 10, 8, 9, 5, 0, tzinfo=timezone.utc)
    if event is E.ACTION_NORMALIZED:
        a.normalize(t)
    elif event is E.RISK_ASSESSED:
        a.record_risk(RiskScore(0.1), "m", t)
    elif event is E.ACTION_ALLOWED:
        a.risk_score = RiskScore(0.1); a.apply_decision(decide(a.risk_score, ExternalSideEffect.NO, POLICY), t)
    elif event is E.HUMAN_APPROVAL_REQUESTED:
        a.risk_score = RiskScore(0.4); a.apply_decision(decide(a.risk_score, ExternalSideEffect.NO, POLICY), t)
    elif event is E.ACTION_BLOCKED:
        a.risk_score = RiskScore(0.9); a.apply_decision(decide(a.risk_score, ExternalSideEffect.NO, POLICY), t)
    elif event is E.HUMAN_APPROVAL_GRANTED:
        a.grant_approval(REVIEWER, t)
    elif event is E.HUMAN_APPROVAL_REJECTED:
        a.reject_approval(REVIEWER, t)
    elif event is E.TOOL_EXECUTION_STARTED:
        a.start_execution(t)
    elif event is E.TOOL_EXECUTION_COMPLETED:
        a.complete_execution(t)
    elif event is E.TOOL_EXECUTION_FAILED:
        a.fail_execution(t)
    else:  # pragma: no cover
        raise AssertionError(event)


@pytest.mark.parametrize("state", list(S))
@pytest.mark.parametrize("event", ACTION_EVENTS)
def test_every_state_event_pair_is_allowed_iff_in_the_transition_table(state, event):
    a = _fresh(state)
    allowed = TRANSITIONS.get((state, event), frozenset())
    if allowed:
        _fire(a, event)
        assert a.state in allowed
    else:
        with pytest.raises(InvalidTransitionError):
            _fire(a, event)
        assert a.state is state  # a refused transition leaves the state untouched


def test_creation_and_stateless_events_are_never_transitions():
    used = {event for (_, event) in TRANSITIONS}
    assert E.ACTION_PROPOSED not in used and E.AUDIT_RECORDED not in used
    assert used == set(E) - {E.ACTION_PROPOSED, E.AUDIT_RECORDED}


def test_terminal_states_have_no_outgoing_transitions():
    assert TERMINAL_STATES == VALUE_TERMINALS == {S.BLOCKED, S.REJECTED, S.EXECUTED, S.EXECUTION_FAILED}
    assert not [k for k in TRANSITIONS if k[0] in TERMINAL_STATES]


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_no_event_is_accepted_in_a_terminal_state(terminal):
    for event in ACTION_EVENTS:
        with pytest.raises(InvalidTransitionError):
            _fire(_fresh(terminal), event)


# ------------------------------------------------------------ valid end-to-end flows
def test_allow_flow_reaches_executed(make_env):
    env = make_env(score=0.1)
    a = submit(env)
    assert a.state is S.ALLOWED and a.authorization is AuthorizationStatus.AUTHORIZED
    env.gate.execute("A-1")
    assert a.state is S.EXECUTED and env.executor.executed == ["A-1"]
    assert [e.to_state for e in a.history] == [S.PROPOSED, S.NORMALIZED, S.RISK_ASSESSED, S.ALLOWED, S.EXECUTING, S.EXECUTED]


def test_review_flow_approved_then_executed(make_env):
    env = make_env(score=0.4)
    a = submit(env)
    assert a.state is S.PENDING_APPROVAL and a.authorization is AuthorizationStatus.NOT_AUTHORIZED
    env.gate.approve("A-1", REVIEWER)
    assert a.state is S.APPROVED and a.authorization is AuthorizationStatus.AUTHORIZED
    env.gate.execute("A-1")
    assert a.state is S.EXECUTED


def test_review_flow_rejected_is_terminal_and_never_executes(make_env):
    env = make_env(score=0.4)
    a = submit(env)
    env.gate.reject("A-1", REVIEWER)
    assert a.state is S.REJECTED and a.authorization is AuthorizationStatus.NOT_AUTHORIZED
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")
    assert env.executor.executed == []


def test_block_flow_is_terminal(make_env):
    env = make_env(score=0.9)
    a = submit(env)
    assert a.state is S.BLOCKED and a.is_terminal
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")
    assert env.executor.executed == []


# ------------------------------------------------------------ missing approval / duplicate approval
def test_execution_without_approval_is_refused(make_env):
    env = make_env(score=0.4)
    submit(env)
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")
    assert env.executor.executed == []


def test_duplicate_approval_is_refused(make_env):
    env = make_env(score=0.4)
    submit(env)
    env.gate.approve("A-1", REVIEWER)
    with pytest.raises(InvalidTransitionError):
        env.gate.approve("A-1", REVIEWER)


@pytest.mark.parametrize("first,second", [("approve", "reject"), ("reject", "approve"), ("reject", "reject")])
def test_conflicting_or_repeated_review_decisions_are_refused(make_env, first, second):
    env = make_env(score=0.4)
    submit(env)
    getattr(env.gate, first)("A-1", REVIEWER)
    with pytest.raises(InvalidTransitionError):
        getattr(env.gate, second)("A-1", REVIEWER)


def test_approval_request_cannot_be_decided_twice():
    ar = ApprovalRequest("APR-1", "A-1", T0)
    ar.decide(ApprovalStatus.GRANTED, REVIEWER, T0)
    with pytest.raises(InvalidTransitionError):
        ar.decide(ApprovalStatus.REJECTED, REVIEWER, T0)


def test_unauthorized_reviewer_cannot_approve_and_state_is_unchanged(make_env):
    env = make_env(score=0.4)
    a = submit(env)
    with pytest.raises(AuthorizationError):
        env.gate.approve("A-1", "intruder-01")
    assert a.state is S.PENDING_APPROVAL and a.approval.status.value == "PENDING"


# ------------------------------------------------------------ missing risk result
def test_decision_without_risk_assessment_is_refused():
    a = _fresh(S.NORMALIZED)
    with pytest.raises(InvalidTransitionError):
        a.apply_decision(decide(None, ExternalSideEffect.NO, POLICY), T0)


def test_decision_must_be_derived_from_the_recorded_risk_score():
    a = _fresh(S.RISK_ASSESSED)
    a.risk_score = RiskScore(0.9)
    with pytest.raises(ValidationError):
        a.apply_decision(decide(RiskScore(0.1), ExternalSideEffect.NO, POLICY), T0)  # ALLOW built from another score
    assert a.state is S.RISK_ASSESSED


def test_assessor_reporting_no_estimate_fails_closed(make_env):
    env = make_env(score=None)
    a = submit(env)
    assert a.risk_score is None and a.decision.decision is DecisionType.BLOCK and a.state is S.BLOCKED


def test_assessor_returning_out_of_range_score_leaves_action_unexecutable(make_env):
    env = make_env(score=1.7)
    with pytest.raises(ValidationError):
        submit(env)
    assert env.gate.get("A-1").state is S.NORMALIZED
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")
    assert env.executor.executed == []


# ------------------------------------------------------------ missing authorization
def test_execution_without_authorization_is_refused_even_in_an_executable_state():
    a = _fresh(S.ALLOWED)
    a.authorization = AuthorizationStatus.NOT_AUTHORIZED
    with pytest.raises(AuthorizationError):
        a.start_execution(datetime(2026, 10, 8, 9, 5, tzinfo=timezone.utc))
    assert a.state is S.ALLOWED


# ------------------------------------------------------------ repeated execution / tool failure / audit order
def test_repeated_execution_is_refused_and_tool_runs_once(make_env):
    env = make_env(score=0.1)
    submit(env)
    env.gate.execute("A-1")
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")
    assert env.executor.executed == ["A-1"]


def test_tool_failure_is_recorded_and_terminal(make_env):
    env = make_env(score=0.1, failing=frozenset({"A-1"}))
    submit(env)
    a = env.gate.execute("A-1")
    assert a.state is S.EXECUTION_FAILED and env.executor.executed == []
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")
    assert [r.to_state for r in env.audit.records_for("A-1")][-2:] == [S.EXECUTING, S.EXECUTION_FAILED]


def test_execution_start_is_audited_before_the_tool_is_called(make_env):
    seen = {}

    class ProbingExecutor:
        executed: list = []

        def execute(self, action):
            seen["audited_events"] = [r.event for r in env.audit.records_for(action.action_id)]

    env = make_env(score=0.1, executor=ProbingExecutor())
    submit(env)
    env.gate.execute("A-1")
    assert E.TOOL_EXECUTION_STARTED in seen["audited_events"]
    assert E.TOOL_EXECUTION_COMPLETED not in seen["audited_events"]


def test_unknown_action_id_is_rejected(make_env):
    with pytest.raises(ValidationError):
        make_env().gate.execute("does-not-exist")
