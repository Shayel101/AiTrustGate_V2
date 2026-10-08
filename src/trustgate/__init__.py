"""Public API of the AI Trust Gate domain (A2). Domain modules import only the standard library."""
from .entities import AgentAction, ApprovalRequest, AuditRecord, TRANSITIONS
from .errors import AuthorizationError, DomainError, InvalidTransitionError, InvariantViolation, ValidationError
from .gate import TrustGate
from .policy import DECISION_TABLE, PolicyConfig, decide, risk_band
from .values import (
    ActionState,
    ApprovalStatus,
    AuthorizationStatus,
    DecisionType,
    EventType,
    ExternalSideEffect,
    RiskBand,
    RiskScore,
    TrustDecision,
)

__all__ = [
    "AgentAction", "ApprovalRequest", "AuditRecord", "TRANSITIONS", "AuthorizationError", "DomainError",
    "InvalidTransitionError", "InvariantViolation", "ValidationError", "TrustGate", "DECISION_TABLE",
    "PolicyConfig", "decide", "risk_band", "ActionState", "ApprovalStatus", "AuthorizationStatus",
    "DecisionType", "EventType", "ExternalSideEffect", "RiskBand", "RiskScore", "TrustDecision",
]
