"""Validation rules (section 'Validation rules' of docs/a2/data_dictionary.md): valid and invalid inputs."""
from __future__ import annotations

import dataclasses
import math
from datetime import datetime, timedelta, timezone

import pytest
from conftest import TEXT, submit

from trustgate import (
    ActionState, AgentAction, AuditRecord, AuthorizationError, AuthorizationStatus, DecisionType, EventType,
    InvalidTransitionError, RiskScore, ValidationError,
)
from trustgate.adapters.simulated import InMemoryAuditStore
from trustgate.values import (
    ApprovalStatus, ExternalSideEffect, ensure_utc, normalize_text, normalize_tool_name, parse_enum, sha256_text,
    validate_identifier,
)

T0 = datetime(2026, 10, 8, 9, 0, 0, tzinfo=timezone.utc)


def _propose(**overrides):
    kw = dict(action_id="A-1", request_id="R-1", request_text=TEXT, tool_name="llm_generate", at=T0)
    kw.update(overrides)
    return AgentAction.propose(**kw)


# ---- enums
@pytest.mark.parametrize("bad", ["allow", "Allow", "PERMIT", "", None, 1, ["ALLOW"]])
def test_invalid_enum_values_are_rejected(bad):
    with pytest.raises(ValidationError):
        parse_enum(DecisionType, bad, "decision")


@pytest.mark.parametrize("good", ["ALLOW", "REVIEW", "BLOCK", DecisionType.BLOCK])
def test_valid_enum_values_are_accepted(good):
    assert parse_enum(DecisionType, good, "decision") is DecisionType(good if isinstance(good, str) else good.value)


# ---- identifiers
@pytest.mark.parametrize("field", ["action_id", "request_id"])
@pytest.mark.parametrize("bad", [None, "", " ", "has space", "-leading-dash", "a" * 65, 7, "semi;colon"])
def test_missing_or_malformed_identifiers_are_rejected(field, bad):
    with pytest.raises(ValidationError):
        _propose(**{field: bad})


@pytest.mark.parametrize("good", ["A-1", "a", "behavior.harmful_34", "urn:x:1", "a" * 64])
def test_valid_identifiers_are_accepted(good):
    assert validate_identifier(good, "id") == good


# ---- risk score
@pytest.mark.parametrize("bad", [-0.0001, 1.0001, 2, -1, math.nan, math.inf, -math.inf, "0.5", None, True, [0.5]])
def test_risk_score_outside_unit_interval_or_non_numeric_is_rejected(bad):
    with pytest.raises(ValidationError):
        RiskScore(bad)


@pytest.mark.parametrize("good,expected", [(0, 0.0), (1, 1.0), (0.5, 0.5), (0.35, 0.35)])
def test_risk_score_inside_unit_interval_is_accepted(good, expected):
    assert RiskScore(good).value == expected


def test_record_risk_rejects_a_raw_float():
    a = _propose()
    a.normalize(T0)
    with pytest.raises(ValidationError):
        a.record_risk(0.5, "m", T0)  # type: ignore[arg-type]


# ---- malformed tool action
@pytest.mark.parametrize("tool", [None, "", "   ", "Send Email", "send-email", "1tool", 5, "x" * 65])
def test_malformed_tool_name_is_rejected(tool):
    with pytest.raises(ValidationError):
        _propose(tool_name=tool)


@pytest.mark.parametrize("args", ["a=b", ["a"], 5, {1: "x"}, {"": "x"}])
def test_malformed_tool_arguments_are_rejected(args):
    with pytest.raises(ValidationError):
        _propose(tool_arguments=args)


@pytest.mark.parametrize("text", [None, "", "   \n\t", "abc\x00def", 42, b"bytes"])
def test_malformed_request_text_is_rejected(text):
    with pytest.raises(ValidationError):
        _propose(request_text=text)


def test_valid_action_is_accepted_and_normalized():
    a = _propose(request_text="  Cafe\u0301 report \n", tool_name=" Send_Email ", tool_arguments={"to": "x"})
    a.normalize(T0)
    assert a.request_text == "Caf\u00e9 report" and a.tool_name == "send_email" and a.state is ActionState.NORMALIZED
    assert normalize_tool_name("LLM_Generate") == "llm_generate"
    assert normalize_text(" a ", "t") == "a"


def test_duplicate_action_id_is_rejected(make_env):
    env = make_env()
    submit(env, "A-1")
    with pytest.raises(ValidationError):
        submit(env, "A-1")


def test_malformed_submission_creates_no_action_and_no_audit_record(make_env):
    env = make_env()
    with pytest.raises(ValidationError):
        env.gate.submit(action_id="A-1", request_id="R-1", request_text="", tool_name="llm_generate")
    assert env.audit.all_records() == []
    with pytest.raises(ValidationError):
        env.gate.get("A-1")


# ---- timestamps
@pytest.mark.parametrize("bad", [datetime(2026, 10, 8, 9, 0), "2026-10-08T09:00:00Z", None, 1_700_000_000])
def test_invalid_timestamps_are_rejected(bad):
    with pytest.raises(ValidationError):
        ensure_utc(bad, "timestamp")
    with pytest.raises(ValidationError):
        _propose(at=bad)


def test_aware_non_utc_timestamp_is_converted_to_utc():
    plus8 = datetime(2026, 10, 8, 17, 0, tzinfo=timezone(timedelta(hours=8)))
    assert ensure_utc(plus8, "t") == T0 and ensure_utc(plus8, "t").utcoffset() == timedelta(0)


def test_event_timestamp_going_backwards_is_rejected():
    a = _propose()
    with pytest.raises(ValidationError):
        a.normalize(T0 - timedelta(seconds=1))
    assert a.state is ActionState.PROPOSED


def _record(**kw):
    base = dict(audit_id="AUD-000001", action_id="A-1", request_id="R-1", event=EventType.ACTION_PROPOSED,
                from_state=None, to_state=ActionState.PROPOSED, timestamp=T0, decision=None, rule_id="",
                policy_version="p", model_version=None, text_sha256=sha256_text(TEXT))
    base.update(kw)
    return AuditRecord(**base)


def test_audit_record_rejects_naive_timestamp_and_bad_ids():
    with pytest.raises(ValidationError):
        _record(timestamp=datetime(2026, 10, 8, 9, 0))
    with pytest.raises(ValidationError):
        _record(audit_id="")
    with pytest.raises(ValidationError):
        _record(action_id=None)


def test_audit_store_rejects_duplicate_ids_backwards_time_and_foreign_objects():
    store = InMemoryAuditStore()
    store.append(_record())
    with pytest.raises(ValidationError):
        store.append(_record())  # same audit_id
    with pytest.raises(ValidationError):
        store.append(_record(audit_id="AUD-000002", timestamp=T0 - timedelta(seconds=1)))
    with pytest.raises(ValidationError):
        store.append({"audit_id": "x"})  # type: ignore[arg-type]
    assert len(store.all_records()) == 1


def test_audit_records_are_immutable():
    r = _record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.to_state = ActionState.EXECUTED  # type: ignore[misc]


# ---- the execution-gating validation rules, end to end
def test_execution_after_block_is_rejected(make_env):
    env = make_env(score=0.9)
    submit(env)
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")


def test_execution_after_review_without_approval_is_rejected(make_env):
    env = make_env(score=0.4)
    submit(env)
    with pytest.raises(InvalidTransitionError):
        env.gate.execute("A-1")


def test_execution_without_authorization_is_rejected(make_env):
    env = make_env(score=0.1)
    a = submit(env)
    a.authorization = AuthorizationStatus.NOT_AUTHORIZED  # tampering
    with pytest.raises(AuthorizationError):
        env.gate.execute("A-1")
    assert env.executor.executed == []


def test_unauthorized_reviewer_and_malformed_reviewer_ids_are_rejected(make_env):
    env = make_env(score=0.4)
    submit(env)
    for bad in ["intruder-01", "", None]:
        with pytest.raises((AuthorizationError, ValidationError)):
            env.gate.approve("A-1", bad)  # type: ignore[arg-type]


# ---- data minimisation: audit records carry a digest, never the request text
def test_audit_records_do_not_store_request_text(make_env):
    env = make_env(score=0.1)
    submit(env, text="SYNTHETIC secret-looking phrase 12345")
    for r in env.audit.all_records():
        assert "secret-looking" not in repr(r)
        assert r.text_sha256 == sha256_text("SYNTHETIC secret-looking phrase 12345")


def test_audit_records_carry_tool_name_and_risk_score_for_reconstruction(make_env):
    env = make_env(score=0.4)
    submit(env, "A-1", tool="send_email")
    last = env.audit.records_for("A-1")[-1]
    assert (last.tool_name, last.risk_score, last.rule_id, last.decision) == ("send_email", 0.4, "DT-08", DecisionType.REVIEW)


def test_enum_member_coverage_for_documented_value_objects():
    assert {e.value for e in ExternalSideEffect} == {"NO", "YES", "UNKNOWN"}
    assert {e.value for e in ApprovalStatus} == {"PENDING", "GRANTED", "REJECTED"}
