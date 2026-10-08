"""Domain errors for the AI Trust Gate (A2)."""
from __future__ import annotations


class DomainError(Exception):
    """Base class for every error raised by the trust-gate domain."""


class ValidationError(DomainError):
    """Input or value violates a domain validation rule."""


class InvalidTransitionError(DomainError):
    """The requested (state, event) -> state transition is not in the state model."""


class AuthorizationError(DomainError):
    """The caller or action lacks the authorization required for the operation."""


class InvariantViolation(DomainError):
    """A domain invariant (INV-xx) does not hold."""
