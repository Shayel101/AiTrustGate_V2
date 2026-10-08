"""Shared fixtures: deterministic gate, policy, simulated adapters (no real tools, no real reviewers)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from trustgate import ExternalSideEffect, PolicyConfig, TrustGate
from trustgate.adapters.simulated import FixedRiskAssessor, InMemoryAuditStore, SimulatedToolExecutor, TickingClock

REVIEWER = "reviewer-sim-01"
TEXT = "SYNTHETIC test request text"


@pytest.fixture
def policy() -> PolicyConfig:
    return PolicyConfig(
        tool_side_effects={"llm_generate": ExternalSideEffect.NO, "send_email": ExternalSideEffect.YES},
        reviewer_ids=frozenset({REVIEWER}),
    )


@pytest.fixture
def make_env(policy):
    """Factory: make_env(score=0.1) -> env with gate, audit, executor, clock for a stipulated risk score."""

    def _make(score=0.1, failing=frozenset(), audit=None, executor=None):
        audit = audit or InMemoryAuditStore()
        executor = executor or SimulatedToolExecutor(failing_action_ids=failing)
        clock = TickingClock()
        gate = TrustGate(FixedRiskAssessor(default=score), executor, audit, policy, clock)
        return SimpleNamespace(gate=gate, audit=audit, executor=executor, clock=clock, policy=policy)

    return _make


def submit(env, action_id="A-1", tool="llm_generate", text=TEXT, args=None):
    return env.gate.submit(action_id=action_id, request_id=f"R-{action_id}", request_text=text,
                           tool_name=tool, tool_arguments=args)
