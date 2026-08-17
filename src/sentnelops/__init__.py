"""SentnelOps Python SDK — identity, lifecycle, and policy for AI agents."""
from .client import DEFAULT_BASE_URL, AIRClient, Decision
from .errors import (
    APIError,
    AuthenticationError,
    LifecycleError,
    NotFoundError,
    PermissionDeniedError,
    PolicyViolation,
    RateLimitedError,
    SentnelOpsError,
    ValidationError,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "AIRClient",
    "APIError",
    "AuthenticationError",
    "Decision",
    "LifecycleError",
    "NotFoundError",
    "PermissionDeniedError",
    "PolicyViolation",
    "RateLimitedError",
    "SentnelOpsError",
    "ValidationError",
]
__version__ = "0.2.0"
