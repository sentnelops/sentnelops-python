"""Offline tests — every request is served by an httpx.MockTransport,
so the suite runs with no network and no credentials."""
from __future__ import annotations

import json

import httpx
import pytest

from sentnelops import (
    AIRClient,
    AuthenticationError,
    LifecycleError,
    NotFoundError,
    PolicyViolation,
    RateLimitedError,
)

AGENT = {"id": "a-1", "name": "prod-billing", "owner": "finance",
         "environment": "production", "risk_level": "high",
         "allowed_mcp": ["stripe-mcp"], "denied_mcp": [],
         "status": "draft", "created_by": "priya@example.com"}


def make_client(handler) -> AIRClient:
    client = AIRClient(api_key="snops_key_test", base_url="http://t")
    client._http = httpx.Client(
        base_url="http://t", transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer snops_key_test"})
    return client


def test_register_returns_agent_with_one_time_token():
    def handler(request):
        assert request.url.path == "/agents"
        body = json.loads(request.content)
        assert body["name"] == "prod-billing"
        assert body["denied_mcp"] == []
        return httpx.Response(201, json={"agent": AGENT, "token": "jwt-1"})

    with make_client(handler) as c:
        agent = c.register(name="prod-billing", owner="finance",
                           environment="production",
                           created_by="priya@example.com",
                           allowed_mcp=["stripe-mcp"], risk_level="high")
    assert agent["id"] == "a-1" and agent["token"] == "jwt-1"


def test_lifecycle_calls_hit_the_right_endpoints():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path,
                     dict(request.url.params)))
        return httpx.Response(200, json=AGENT)

    with make_client(handler) as c:
        c.approve("a-1", approved_by="ciso@example.com", note="ok")
        c.activate("a-1", actor="priya@example.com")
        c.suspend("a-1", actor="ciso@example.com", reason="incident")
        c.reactivate("a-1", actor="ciso@example.com")
        c.decommission("a-1", actor="ciso@example.com")

    paths = [p for _, p, _ in seen]
    assert paths == ["/agents/a-1/approve", "/agents/a-1/activate",
                     "/agents/a-1/suspend", "/agents/a-1/reactivate",
                     "/agents/a-1"]
    assert seen[-1][0] == "DELETE"
    assert seen[-1][2] == {"actor": "ciso@example.com"}


def test_lifecycle_conflict_maps_to_typed_error_with_code():
    def handler(request):
        return httpx.Response(409, json={"detail": {
            "code": "segregation_of_duties",
            "detail": "creator cannot approve their own agent"}})

    with make_client(handler) as c, pytest.raises(LifecycleError) as e:
        c.approve("a-1", approved_by="priya@example.com")
    assert e.value.code == "segregation_of_duties"
    assert e.value.status_code == 409


def test_error_mapping_401_404_429():
    responses = {
        "/agents/x1": httpx.Response(401, json={"detail": "invalid api key"}),
        "/agents/x2": httpx.Response(404, json={"detail": "agent not found"}),
        "/agents/x3": httpx.Response(429, json={"detail": "rate limited"},
                                     headers={"Retry-After": "7"}),
    }

    def handler(request):
        return responses[request.url.path]

    with make_client(handler) as c:
        with pytest.raises(AuthenticationError):
            c.get("x1")
        with pytest.raises(NotFoundError):
            c.get("x2")
        with pytest.raises(RateLimitedError) as e:
            c.get("x3")
    assert e.value.retry_after == 7.0


def test_require_raises_policy_violation_on_deny():
    def handler(request):
        return httpx.Response(200, json={
            "permitted": False, "reason": "server 'payroll-mcp' is denied",
            "policy_rule": "denied_mcp"})

    with make_client(handler) as c:
        d = c.is_permitted("a-1", "payroll-mcp")
        assert not d.permitted and d.policy_rule == "denied_mcp"
        with pytest.raises(PolicyViolation) as e:
            c.require("a-1", "payroll-mcp")
    assert e.value.decision.reason == "server 'payroll-mcp' is denied"


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("SNOPS_API_KEY", raising=False)
    from sentnelops import SentnelOpsError
    with pytest.raises(SentnelOpsError, match="SNOPS_API_KEY"):
        AIRClient()


def test_verify_token_round_trip():
    import jwt as pyjwt
    token = pyjwt.encode({"sub": "a-1", "iss": "sentnelops.com"},
                         "s3cret-thats-long-enough-for-tests",
                         algorithm="HS256")
    claims = AIRClient.verify_token(token,
                                    "s3cret-thats-long-enough-for-tests")
    assert claims["sub"] == "a-1"
    with pytest.raises(pyjwt.InvalidTokenError):
        AIRClient.verify_token(token, "wrong-secret-also-long-enough!!")
