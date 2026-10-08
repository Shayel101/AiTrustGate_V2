"""Value objects and enumerations of the AI Trust Gate domain (A2).

Standard library only: the domain must not depend on any ML/LLM library.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TypeVar

from .errors import ValidationError

E = TypeVar("E", bound=Enum)


class DecisionType(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"  # A2 design extension; A1 only has ALLOW/BLOCK
    BLOCK = "BLOCK"


class RiskBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"  # no usable risk estimate


class ExternalSideEffect(str, Enum):
    NO = "NO"
    YES = "YES"
    UNKNOWN = "UNKNOWN"


class AuthorizationStatus(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"


class ActionState(str, Enum):
    PROPOSED = "PROPOSED"
    NORMALIZED = "NORMALIZED"
    RISK_ASSESSED = "RISK_ASSESSED"
    ALLOWED = "ALLOWED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class EventType(str, Enum):
    ACTION_PROPOSED = "ActionProposed"
    ACTION_NORMALIZED = "ActionNormalized"
    RISK_ASSESSED = "RiskAssessed"
    ACTION_ALLOWED = "ActionAllowed"
    HUMAN_APPROVAL_REQUESTED = "HumanApprovalRequested"
    ACTION_BLOCKED = "ActionBlocked"
    HUMAN_APPROVAL_GRANTED = "HumanApprovalGranted"
    HUMAN_APPROVAL_REJECTED = "HumanApprovalRejected"
    TOOL_EXECUTION_STARTED = "ToolExecutionStarted"
    TOOL_EXECUTION_COMPLETED = "ToolExecutionCompleted"
    TOOL_EXECUTION_FAILED = "ToolExecutionFailed"
    AUDIT_RECORDED = "AuditRecorded"  # emitted by the audit store; not an AgentAction transition


TERMINAL_STATES = frozenset({
    ActionState.BLOCKED, ActionState.REJECTED, ActionState.EXECUTED, ActionState.EXECUTION_FAILED,
})
EXECUTION_STATES = frozenset({ActionState.EXECUTING, ActionState.EXECUTED, ActionState.EXECUTION_FAILED})


def parse_enum(enum_cls: type[E], value: object, field: str) -> E:
    """Strict enum parsing: exact member or exact value string, nothing else."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            pass
    raise ValidationError(f"{field}: {value!r} is not one of {[m.value for m in enum_cls]}")


@dataclass(frozen=True)
class RiskScore:
    """Estimated probability-like risk in [0, 1]; null is not allowed (use None for 'no estimate')."""

    value: float

    def __post_init__(self) -> None:
        v = self.value
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValidationError(f"risk_score: expected a number, got {v!r}")
        f = float(v)
        if not math.isfinite(f) or not 0.0 <= f <= 1.0:
            raise ValidationError(f"risk_score: {v!r} is outside [0, 1]")
        object.__setattr__(self, "value", f)


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_identifier(value: object, field: str) -> str:
    """Identifiers (action_id, request_id, reviewer_id, ...) are validated, never auto-generated here."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValidationError(f"{field}: {value!r} is not a valid identifier (pattern {_ID_RE.pattern})")
    return value


def normalize_tool_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"tool_name: expected str, got {type(value).__name__}")
    name = value.strip().lower()
    if not _TOOL_RE.match(name):
        raise ValidationError(f"tool_name: {value!r} does not match {_TOOL_RE.pattern}")
    return name


def normalize_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field}: expected str, got {type(value).__name__}")
    text = unicodedata.normalize("NFC", value).strip()
    if not text or "\x00" in text:
        raise ValidationError(f"{field}: must be non-empty text without NUL characters")
    return text


def ensure_utc(value: object, field: str) -> datetime:
    """Timestamps must be timezone-aware; they are converted to UTC."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field}: expected a timezone-aware datetime, got {value!r}")
    return value.astimezone(timezone.utc)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TrustDecision:
    """Immutable outcome of policy evaluation; carries the evidence it was derived from."""

    decision: DecisionType
    rule_id: str
    risk_score: Optional[RiskScore]
    risk_band: RiskBand
    external_side_effect: ExternalSideEffect
    policy_version: str
    model_version: Optional[str]
