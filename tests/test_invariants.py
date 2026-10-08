"""INV-01..INV-06 (docs/a2/invariants.md): each has a passing case, a deliberately violating input, and detection."""
from __future__ import annotations

import dataclasses

import pytest
from conftest import REVIEWER, submit

from trustgate import (
    ActionState, ApprovalStatus, AuthorizationStatus, DecisionType, EventType, ExternalSideEffect, InvariantViolation,
    PolicyConfig, RiskScore,
)
from trustgate.adapters.simulated import InMemoryAuditStore
from trustgate.entities import ActionEvent
from trustgate.invariants import (
    assert_invariants,
    check_all,
    inv_audit_complete,
    inv_blocked_never_executes,
    inv_decision_matches_policy,
    inv_execution_once_and_terminal_final,
    inv_execution_requires_authorization,
    inv_review_requires_granted_approval,
)


def _executed(env):  # ALLOW -> EXECUTED
    submit(env, "A-ok")
    env.gate.execute("A-ok")
    return env.gate.get("A-ok")


def _blocked(env):
    return submit(env, "A-blk")  # env built with score 0.9


def _pending(env):
    return submit(env, "A-rev")  # env built with score 0.4


def _approved_executed(env):
    submit(env, "A-apr")
    env.gate.approve("A-apr", REVIEWER)
    env.gate.execute("A-apr")
    return env.gate.get("A-apr")


# ---------------------------------------------------------------- INV-01
def test_inv01_valid_blocked_action_holds(make_env):
    env = make_env(score=0.9)
    a = _blocked(env)
    assert a.decision.decision is DecisionType.BLOCK
    assert inv_blocked_never_executes(a)


def test_inv01_valid_non_block_actions_are_vacuously_true(make_env):
    assert inv_blocked_never_executes(_executed(make_env(score=0.1)))


@pytest.mark.parametrize("violation", ["state_executed", "authorized", "execution_event"])
def test_inv01_violation_is_detected(make_env, violation):
    env = make_env(score=0.9)
    a = _blocked(env)
    if violation == "state_executed":
        a.state = ActionState.EXECUTED
    elif violation == "authorized":
        a.authorization = AuthorizationStatus.AUTHORIZED
    else:
        a.history.append(ActionEvent(EventType.TOOL_EXECUTION_STARTED, ActionState.BLOCKED, ActionState.EXECUTING, a.history[-1].at))
    assert not inv_blocked_never_executes(a)
    assert "INV-01" in check_all(a, env.audit.records_for(a.action_id), env.policy)


# ---------------------------------------------------------------- INV-02
def test_inv02_valid_pending_and_approved_executed_hold(make_env):
    assert inv_review_requires_granted_approval(_pending(make_env(score=0.4)))
    assert inv_review_requires_granted_approval(_approved_executed(make_env(score=0.4)))


@pytest.mark.parametrize("violation", ["no_approval_object", "rejected", "pending", "granted_without_reviewer"])
def test_inv02_violation_is_detected(make_env, violation):
    env = make_env(score=0.4)
    a = _pending(env)
    a.state = ActionState.EXECUTED  # executed although the action is a REVIEW action
    if violation == "no_approval_object":
        a.approval = None
    elif violation == "rejected":
        a.approval.status = ApprovalStatus.REJECTED
    elif violation == "granted_without_reviewer":
        a.approval.status = ApprovalStatus.GRANTED
    assert not inv_review_requires_granted_approval(a)


# ---------------------------------------------------------------- INV-03
def test_inv03_valid_allow_and_approved_paths_hold(make_env):
    assert inv_execution_requires_authorization(_executed(make_env(score=0.1)))
    assert inv_execution_requires_authorization(_approved_executed(make_env(score=0.4)))
    assert inv_execution_requires_authorization(_pending(make_env(score=0.4)))


@pytest.mark.parametrize("violation", ["executed_unauthorized", "authorized_without_decision", "authorized_pending_review"])
def test_inv03_violation_is_detected(make_env, violation):
    env = make_env(score=0.1)
    a = _executed(env)
    if violation == "executed_unauthorized":
        a.authorization = AuthorizationStatus.NOT_AUTHORIZED
    elif violation == "authorized_without_decision":
        a.decision = None
    else:
        env2 = make_env(score=0.4)
        a = _pending(env2)
        a.authorization = AuthorizationStatus.AUTHORIZED  # forged before any approval
    assert not inv_execution_requires_authorization(a)


# ---------------------------------------------------------------- INV-04
def test_inv04_valid_decisions_match_policy(make_env):
    for score, tool in [(0.1, "llm_generate"), (0.4, "llm_generate"), (0.9, "llm_generate"), (0.1, "send_email")]:
        env = make_env(score=score)
        a = submit(env, "A-x", tool=tool)
        assert inv_decision_matches_policy(a, env.policy)


@pytest.mark.parametrize("violation", ["flipped_decision", "changed_score", "stricter_policy_than_recorded"])
def test_inv04_violation_is_detected(make_env, violation):
    env = make_env(score=0.9)
    a = submit(env, "A-x")
    policy = env.policy
    if violation == "flipped_decision":
        a.decision = dataclasses.replace(a.decision, decision=DecisionType.ALLOW)
    elif violation == "changed_score":
        a.risk_score = RiskScore(0.1)
    else:
        policy = PolicyConfig(block_above=0.95, reviewer_ids=frozenset({REVIEWER}))  # recorded BLOCK no longer matches
    assert not inv_decision_matches_policy(a, policy)


# ---------------------------------------------------------------- INV-05
def test_inv05_valid_audit_is_complete_for_every_flow(make_env):
    for score in (0.1, 0.4, 0.9):
        env = make_env(score=score)
        a = submit(env, "A-x")
        assert inv_audit_complete(a, env.audit.records_for("A-x"))


@pytest.mark.parametrize("violation", ["drop_last", "no_records", "wrong_state_only"])
def test_inv05_violation_is_detected(make_env, violation):
    env = make_env(score=0.9)
    a = submit(env, "A-x")
    records = env.audit.records_for("A-x")
    if violation == "drop_last":
        records = records[:-1]  # the BLOCK decision itself is not audited
    elif violation == "no_records":
        records = []
    else:
        records = [dataclasses.replace(r, to_state=ActionState.ALLOWED) if r.event is EventType.ACTION_BLOCKED else r for r in records]
    assert not inv_audit_complete(a, records)


def test_inv05_gate_refuses_to_proceed_when_audit_store_drops_records(make_env):
    class DroppingStore(InMemoryAuditStore):
        def append(self, record):  # silently loses everything
            return None

    env = make_env(score=0.9, audit=DroppingStore())
    with pytest.raises(InvariantViolation, match="INV-05"):
        submit(env, "A-x")


# ---------------------------------------------------------------- INV-06
def test_inv06_valid_histories_hold(make_env):
    assert inv_execution_once_and_terminal_final(_executed(make_env(score=0.1)))
    assert inv_execution_once_and_terminal_final(_blocked(make_env(score=0.9)))


@pytest.mark.parametrize("violation", ["double_start", "event_after_terminal"])
def test_inv06_violation_is_detected(make_env, violation):
    env = make_env(score=0.1)
    a = _executed(env)
    t = a.history[-1].at
    if violation == "double_start":
        a.history.append(ActionEvent(EventType.TOOL_EXECUTION_STARTED, ActionState.EXECUTED, ActionState.EXECUTING, t))
    else:
        a.history.append(ActionEvent(EventType.ACTION_ALLOWED, ActionState.EXECUTED, ActionState.ALLOWED, t))
    assert not inv_execution_once_and_terminal_final(a)


# ---------------------------------------------------------------- aggregate
def test_check_all_is_empty_for_valid_flows_and_assert_raises_for_violations(make_env):
    env = make_env(score=0.9)
    a = _blocked(env)
    assert check_all(a, env.audit.records_for(a.action_id), env.policy) == []
    assert_invariants(a, env.audit.records_for(a.action_id), env.policy)
    a.state = ActionState.EXECUTED
    with pytest.raises(InvariantViolation, match="INV-01"):
        assert_invariants(a, env.audit.records_for(a.action_id), env.policy)


def test_side_effect_authority_is_policy_not_agent(make_env):
    env = make_env(score=0.1)
    a = submit(env, "A-x", tool="send_email", args={"external_side_effect": "NO"})
    assert a.decision.external_side_effect is ExternalSideEffect.YES
    assert a.decision.decision is DecisionType.REVIEW
