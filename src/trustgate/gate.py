"""Application service: orchestrates request -> assessment -> decision -> approval -> execution -> audit."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from .entities import AgentAction, AuditRecord
from .errors import AuthorizationError, ValidationError
from .invariants import assert_invariants
from .policy import PolicyConfig, decide
from .ports import AuditStore, Clock, RiskAssessor, ToolExecutor
from .values import RiskScore


class TrustGate:
    def __init__(
        self,
        risk_assessor: RiskAssessor,
        tool_executor: ToolExecutor,
        audit_store: AuditStore,
        policy: PolicyConfig,
        clock: Clock,
    ) -> None:
        self._assessor = risk_assessor
        self._executor = tool_executor
        self._audit_store = audit_store
        self._policy = policy
        self._clock = clock
        self._actions: dict[str, AgentAction] = {}

    @property
    def policy(self) -> PolicyConfig:
        return self._policy

    def get(self, action_id: str) -> AgentAction:
        try:
            return self._actions[action_id]
        except KeyError:
            raise ValidationError(f"unknown action_id {action_id!r}") from None

    def _audit(self, action: AgentAction) -> None:
        ev = action.history[-1]
        d = action.decision
        self._audit_store.append(AuditRecord(
            audit_id=self._audit_store.next_audit_id(),
            action_id=action.action_id,
            request_id=action.request_id,
            event=ev.event,
            from_state=ev.from_state,
            to_state=ev.to_state,
            timestamp=ev.at,
            decision=d.decision if d else None,
            rule_id=d.rule_id if d else "",
            policy_version=self._policy.policy_version,
            model_version=action.model_version,
            text_sha256=action.text_sha256,
            tool_name=action.tool_name,
            risk_score=None if action.risk_score is None else action.risk_score.value,
        ))
        assert_invariants(action, self._audit_store.records_for(action.action_id), self._policy)

    def submit(
        self,
        *,
        action_id: str,
        request_id: str,
        request_text: str,
        tool_name: str,
        tool_arguments: Optional[Mapping[str, Any]] = None,
    ) -> AgentAction:
        """Propose, normalize, assess and decide. Returns the action in ALLOWED, PENDING_APPROVAL or BLOCKED."""
        action = AgentAction.propose(
            action_id=action_id, request_id=request_id, request_text=request_text,
            tool_name=tool_name, tool_arguments=tool_arguments, at=self._clock(),
        )
        if action.action_id in self._actions:
            raise ValidationError(f"duplicate action_id {action.action_id!r}")
        self._actions[action.action_id] = action
        self._audit(action)

        action.normalize(self._clock())
        self._audit(action)

        raw = self._assessor.assess(action.request_text, action.tool_name, action.tool_arguments)
        score = None if raw is None else RiskScore(raw)  # out-of-range -> ValidationError; action never executes
        action.record_risk(score, self._assessor.model_version, self._clock())
        self._audit(action)

        decision = decide(score, self._policy.side_effect_for(action.tool_name), self._policy, self._assessor.model_version)
        action.apply_decision(decision, self._clock())
        self._audit(action)
        return action

    def _require_reviewer(self, reviewer_id: str) -> None:
        if reviewer_id not in self._policy.reviewer_ids:
            raise AuthorizationError("reviewer is not authorized by the policy configuration")

    def approve(self, action_id: str, reviewer_id: str) -> AgentAction:
        self._require_reviewer(reviewer_id)
        action = self.get(action_id)
        action.grant_approval(reviewer_id, self._clock())
        self._audit(action)
        return action

    def reject(self, action_id: str, reviewer_id: str) -> AgentAction:
        self._require_reviewer(reviewer_id)
        action = self.get(action_id)
        action.reject_approval(reviewer_id, self._clock())
        self._audit(action)
        return action

    def execute(self, action_id: str) -> AgentAction:
        """Write-ahead audit of ToolExecutionStarted, then call the (outside-boundary) tool."""
        action = self.get(action_id)
        action.start_execution(self._clock())
        self._audit(action)
        try:
            self._executor.execute(action)
        except Exception:  # the tool is outside the trust boundary; any failure is recorded, never trusted
            action.fail_execution(self._clock())
        else:
            action.complete_execution(self._clock())
        self._audit(action)
        return action
