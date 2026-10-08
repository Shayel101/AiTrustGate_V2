"""Policy configuration and the decision rule (see docs/a2/decision_table.md)."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional

from .errors import ValidationError
from .values import (
    DecisionType,
    ExternalSideEffect,
    RiskBand,
    RiskScore,
    TrustDecision,
    normalize_tool_name,
    validate_identifier,
)

POLICY_VERSION = "policy-0.2.0"

# A1 evidence: sklearn LogisticRegression labels "harmful" when P(harmful) > 0.5.
A1_DECISION_BOUNDARY = 0.50
# PROJECT DESIGN DECISION (not A1 evidence, not tuned on any data): lower edge of the REVIEW band.
DEFAULT_REVIEW_LOWER = 0.35

D = DecisionType
B = RiskBand
S = ExternalSideEffect

# PROJECT DESIGN DECISION: (risk band, external side effect) -> (rule id, decision). Mirrors decision_table.md.
DECISION_TABLE: dict[tuple[RiskBand, ExternalSideEffect], tuple[str, DecisionType]] = {
    (B.UNKNOWN, S.NO): ("DT-01", D.BLOCK),
    (B.UNKNOWN, S.YES): ("DT-02", D.BLOCK),
    (B.UNKNOWN, S.UNKNOWN): ("DT-03", D.BLOCK),
    (B.HIGH, S.NO): ("DT-04", D.BLOCK),
    (B.HIGH, S.YES): ("DT-05", D.BLOCK),
    (B.HIGH, S.UNKNOWN): ("DT-06", D.BLOCK),
    (B.MEDIUM, S.NO): ("DT-07", D.REVIEW),
    (B.MEDIUM, S.YES): ("DT-08", D.REVIEW),
    (B.MEDIUM, S.UNKNOWN): ("DT-09", D.REVIEW),
    (B.LOW, S.NO): ("DT-10", D.ALLOW),
    (B.LOW, S.YES): ("DT-11", D.REVIEW),
    (B.LOW, S.UNKNOWN): ("DT-12", D.REVIEW),
}


@dataclass(frozen=True, eq=False)
class PolicyConfig:
    """Immutable, versioned policy. Authority for tool side effects and reviewer identities."""

    policy_version: str = POLICY_VERSION
    review_lower: float = DEFAULT_REVIEW_LOWER
    block_above: float = A1_DECISION_BOUNDARY
    tool_side_effects: Mapping[str, ExternalSideEffect] = field(
        default_factory=lambda: {"llm_generate": ExternalSideEffect.NO}
    )
    reviewer_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_lower <= self.block_above <= 1.0:
            raise ValidationError("policy: require 0 <= review_lower <= block_above <= 1")
        registry = {normalize_tool_name(k): v for k, v in self.tool_side_effects.items()}
        for name, effect in registry.items():
            if not isinstance(effect, ExternalSideEffect):
                raise ValidationError(f"policy: side effect for {name!r} must be ExternalSideEffect")
        object.__setattr__(self, "tool_side_effects", MappingProxyType(registry))
        object.__setattr__(self, "reviewer_ids", frozenset(validate_identifier(r, "reviewer_id") for r in self.reviewer_ids))

    def side_effect_for(self, tool_name: str) -> ExternalSideEffect:
        """Tools missing from the registry are UNKNOWN (treated conservatively by the decision table)."""
        return self.tool_side_effects.get(tool_name, ExternalSideEffect.UNKNOWN)


def risk_band(score: Optional[RiskScore], policy: PolicyConfig) -> RiskBand:
    if score is None:
        return RiskBand.UNKNOWN
    if score.value > policy.block_above:
        return RiskBand.HIGH
    if score.value >= policy.review_lower:
        return RiskBand.MEDIUM
    return RiskBand.LOW


def decide(
    score: Optional[RiskScore],
    effect: ExternalSideEffect,
    policy: PolicyConfig,
    model_version: Optional[str] = None,
) -> TrustDecision:
    band = risk_band(score, policy)
    rule_id, decision = DECISION_TABLE[(band, effect)]
    return TrustDecision(decision, rule_id, score, band, effect, policy.policy_version, model_version)
