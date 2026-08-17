"""Typed errors for the SentnelOps SDK.

Every non-2xx API response maps to one of these, so callers can catch
exactly the failure they care about instead of parsing status codes.
"""
from __future__ import annotations


class SentnelOpsError(Exception):
    """Base class for every error raised by this SDK."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        #: machine-readable error code when the API provides one
        #: (e.g. ``segregation_of_duties``, ``terminal_state``)
        self.code = code


class AuthenticationError(SentnelOpsError):
    """401 — missing, invalid, or revoked credential."""


class PermissionDeniedError(SentnelOpsError):
    """403 — authenticated, but not allowed: the principal's role is too
    low, or a governance rule refused the action (e.g. self-approval —
    ``code="segregation_of_duties"``)."""


class NotFoundError(SentnelOpsError):
    """404 — unknown id, or a resource that belongs to another org
    (the API deliberately answers both the same way)."""


class LifecycleError(SentnelOpsError):
    """409 — an invalid lifecycle transition, e.g. activating a draft
    agent without approval, or self-approving your own registration.
    ``code`` carries the API's machine-readable reason."""


class ValidationError(SentnelOpsError):
    """422 — the request body did not validate."""


class RateLimitedError(SentnelOpsError):
    """429 — slow down; ``retry_after`` is the wait in seconds."""

    def __init__(self, message: str, *, retry_after: float | None = None,
                 **kw):
        super().__init__(message, **kw)
        self.retry_after = retry_after


class APIError(SentnelOpsError):
    """Any other non-2xx response (5xx, unexpected shapes)."""


class PolicyViolation(SentnelOpsError):
    """Raised by :meth:`sentnelops.AIRClient.require` when the policy
    decision is a deny. Carries the decision for logging."""

    def __init__(self, message: str, *, decision=None, **kw):
        super().__init__(message, **kw)
        self.decision = decision
