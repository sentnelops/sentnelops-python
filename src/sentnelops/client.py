"""SentnelOps — agent identity, lifecycle, and policy checks for AI agents.

Quickstart::

    from sentnelops import AIRClient

    with AIRClient(api_key="snops_key_...") as client:
        agent = client.register(
            name="prod-billing", owner="finance-team",
            environment="production", created_by="priya@example.com",
            allowed_mcp=["stripe-mcp"], denied_mcp=["payroll-mcp"],
            risk_level="high")
        print(agent["id"], agent["token"])   # token is shown exactly once

        decision = client.is_permitted(agent["id"], "stripe-mcp",
                                       tool="refund.create")
        if not decision.permitted:
            print("denied:", decision.reason)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

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

DEFAULT_BASE_URL = "https://api.sentnelops.com"

_ERROR_BY_STATUS = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: LifecycleError,
    422: ValidationError,
}


@dataclass(frozen=True)
class Decision:
    """The verdict of a policy check."""
    permitted: bool
    reason: str
    policy_rule: str | None = None


def _raise_for(response: httpx.Response) -> None:
    if response.is_success:
        return
    status = response.status_code
    code = None
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):    # not JSON / not an object
        detail = response.text
    if isinstance(detail, dict):            # lifecycle errors: {code, detail}
        code = detail.get("code")
        message = detail.get("detail") or str(detail)
    else:
        message = str(detail or f"HTTP {status}")
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        raise RateLimitedError(message, status_code=status,
                               retry_after=float(retry_after)
                               if retry_after else None)
    cls = _ERROR_BY_STATUS.get(status, APIError)
    raise cls(message, status_code=status, code=code)


class AIRClient:
    """Client for the SentnelOps Agent Identity Registry.

    Args:
        api_key: your org api key (``snops_key_...``). Falls back to the
            ``SNOPS_API_KEY`` environment variable.
        base_url: API root. Falls back to ``SNOPS_BASE_URL``, then the
            hosted platform (``https://api.sentnelops.com``). Point this at
            your own deployment when self-hosting.
        timeout: per-request timeout in seconds.
    """

    def __init__(self, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 10.0):
        api_key = api_key or os.environ.get("SNOPS_API_KEY")
        if not api_key:
            raise SentnelOpsError(
                "no api key: pass api_key= or set SNOPS_API_KEY")
        base_url = (base_url or os.environ.get("SNOPS_BASE_URL")
                    or DEFAULT_BASE_URL)
        from . import __version__
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}",
                     "User-Agent": f"sentnelops-python/{__version__}"})

    # -- identity ----------------------------------------------------------

    def register(self, *, name: str, owner: str, environment: str,
                 created_by: str, allowed_mcp: list[str] | None = None,
                 denied_mcp: list[str] | None = None,
                 risk_level: str = "medium") -> dict:
        """Register an agent and mint its credential.

        Returns the agent record with one extra key, ``token`` — the
        agent's JWT, shown exactly once. Store it securely; it is never
        retrievable again (rotate to get a new one).

        Production agents start in ``draft`` and must be approved (by
        someone other than ``created_by``) and activated before policy
        will permit their calls; dev and staging agents start active.
        """
        r = self._http.post("/agents", json={
            "name": name, "owner": owner, "environment": environment,
            "risk_level": risk_level, "allowed_mcp": allowed_mcp or [],
            "denied_mcp": denied_mcp or [], "created_by": created_by})
        _raise_for(r)
        data = r.json()
        return {**data["agent"], "token": data["token"]}

    def get(self, agent_id: str) -> dict:
        """Fetch one agent by id."""
        r = self._http.get(f"/agents/{agent_id}")
        _raise_for(r)
        return r.json()

    def list(self, *, environment: str | None = None,
             risk_level: str | None = None, status: str | None = None,
             owner: str | None = None, limit: int = 50,
             offset: int = 0) -> list[dict]:
        """List the org's agents, newest first, with optional filters."""
        params = {k: v for k, v in {
            "environment": environment, "risk_level": risk_level,
            "status": status, "owner": owner}.items() if v is not None}
        params.update({"limit": limit, "offset": offset})
        r = self._http.get("/agents", params=params)
        _raise_for(r)
        return r.json()

    def update(self, agent_id: str, *, actor: str,
               owner: str | None = None, risk_level: str | None = None,
               allowed_mcp: list[str] | None = None,
               denied_mcp: list[str] | None = None) -> dict:
        """Update mutable fields (never status — use the lifecycle calls).

        Scope changes are rejected while the agent is suspended.
        """
        body = {k: v for k, v in {
            "owner": owner, "risk_level": risk_level,
            "allowed_mcp": allowed_mcp, "denied_mcp": denied_mcp}.items()
            if v is not None}
        body["actor"] = actor
        r = self._http.patch(f"/agents/{agent_id}", json=body)
        _raise_for(r)
        return r.json()

    # -- lifecycle ---------------------------------------------------------

    def approve(self, agent_id: str, *, approved_by: str,
                note: str = "") -> dict:
        """``draft → approved``. The approver must differ from the creator
        (segregation of duties) or the API answers 403 — raised as
        :class:`PermissionDeniedError` with ``code="segregation_of_duties"``."""
        r = self._http.post(f"/agents/{agent_id}/approve",
                            json={"approved_by": approved_by, "note": note})
        _raise_for(r)
        return r.json()

    def activate(self, agent_id: str, *, actor: str) -> dict:
        """``approved → active``. Approval cannot be skipped."""
        r = self._http.post(f"/agents/{agent_id}/activate",
                            json={"actor": actor})
        _raise_for(r)
        return r.json()

    def suspend(self, agent_id: str, *, actor: str, reason: str) -> dict:
        """``active → suspended``. Reason is mandatory; the agent's scope
        is frozen and policy denies its calls until reactivation."""
        r = self._http.post(f"/agents/{agent_id}/suspend",
                            json={"actor": actor, "reason": reason})
        _raise_for(r)
        return r.json()

    def reactivate(self, agent_id: str, *, actor: str) -> dict:
        """``suspended → active`` while the suspension is under 30 days;
        older suspensions require a fresh approval first."""
        r = self._http.post(f"/agents/{agent_id}/reactivate",
                            json={"actor": actor})
        _raise_for(r)
        return r.json()

    def decommission(self, agent_id: str, *, actor: str) -> dict:
        """Terminal state: revokes every token, keeps the full history."""
        r = self._http.delete(f"/agents/{agent_id}",
                              params={"actor": actor})
        _raise_for(r)
        return r.json()

    def rotate(self, agent_id: str, *, actor: str) -> dict:
        """Revoke the agent's current tokens and mint a new one.

        Returns the agent record plus ``token`` (the new JWT, shown once).
        The old token stops working at the proxy within seconds.
        """
        r = self._http.post(f"/agents/{agent_id}/rotate",
                            params={"actor": actor})
        _raise_for(r)
        data = r.json()
        return {**data["agent"], "token": data["token"]}

    def mark_reviewed(self, agent_id: str, *, actor: str) -> dict:
        """Record a completed access review; the next review is scheduled
        by risk level (high 30d / medium 90d / low 180d)."""
        r = self._http.post(f"/agents/{agent_id}/review",
                            json={"actor": actor})
        _raise_for(r)
        return r.json()

    def audit(self, agent_id: str) -> list[dict]:
        """The agent's append-only audit trail, newest first."""
        r = self._http.get(f"/agents/{agent_id}/audit")
        _raise_for(r)
        return r.json()

    # -- policy ------------------------------------------------------------

    def is_permitted(self, agent_id: str, mcp_server: str,
                     tool: str | None = None) -> Decision:
        """Ask the policy engine for a verdict without making the call."""
        r = self._http.post("/policy/check", json={
            "agent_id": agent_id, "mcp_server": mcp_server, "tool": tool})
        _raise_for(r)
        d = r.json()
        return Decision(d["permitted"], d["reason"], d.get("policy_rule"))

    def require(self, agent_id: str, mcp_server: str,
                tool: str | None = None) -> Decision:
        """Like :meth:`is_permitted`, but raises :class:`PolicyViolation`
        on deny — for guarding a code path in one line::

            client.require(agent_id, "aws-prod", tool="ec2.terminate")
        """
        decision = self.is_permitted(agent_id, mcp_server, tool)
        if not decision.permitted:
            raise PolicyViolation(decision.reason, decision=decision)
        return decision

    # -- for MCP servers validating callers ---------------------------------

    @staticmethod
    def verify_token(token: str, secret: str,
                     issuer: str = "sentnelops.com") -> dict:
        """Decode and verify an agent JWT (HS256).

        For self-hosted deployments where your MCP server shares the
        SentnelOps signing secret and wants to validate callers directly.
        Returns the claims (``sub`` is the agent id) or raises
        ``jwt.InvalidTokenError``.
        """
        import jwt
        return jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)

    # -- plumbing ------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AIRClient:  # noqa: PYI034 — typing.Self needs 3.11+
        return self

    def __exit__(self, *exc) -> None:
        self.close()
