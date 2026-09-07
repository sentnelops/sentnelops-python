# sentnelops-python

**Python SDK for SentnelOps — agent identity, lifecycle governance, policy checks, and caller verification for AI agents.**

![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

## What is SentnelOps

SentnelOps is an AI agent runtime governance platform. It acts as an MCP firewall between AI agents (Claude Code, Cursor, custom agents) and the systems they access, giving every agent an identity, enforcing YAML policies on every tool call before it executes, and producing an audit-ready evidence trail.

This SDK is the control-plane client for that platform: it registers agents in the identity registry, drives their lifecycle (approve, activate, suspend, rotate, decommission), asks the policy engine for advisory verdicts before your code acts, and — for self-hosted deployments — verifies agent JWTs inside your own MCP servers.

## Where the SDK sits

The SDK and CLI talk HTTPS to the SentnelOps API (`https://api.sentnelops.com` by default, or your own deployment via `SNOPS_BASE_URL`). Runtime enforcement is done server-side by the MCP proxy; the SDK's policy checks query the same engine without making the call.

```
 you / your app / CI
        │
        ▼
 sentnelops SDK & CLI ──── HTTPS ────▶ SentnelOps API
 (register, lifecycle,                 (agent registry +
  is_permitted/require)                 policy engine)
                                            ▲
                                            │ same policy engine
 AI agent ── MCP ──▶ SentnelOps MCP proxy ──┘
                     (authoritative runtime      ──▶ your MCP servers
                      enforcement — not this SDK)

 self-hosted only: your MCP server can also call
 AIRClient.verify_token(...) to validate agent JWTs locally.
```

## Install

The package is not yet on PyPI. Install from GitHub:

```bash
pip install git+https://github.com/sentnelops/sentnelops-python.git
```

Python 3.10+. Dependencies: `httpx` and `PyJWT`, nothing else. Installing also puts the `sentnelops` CLI on your path.

## Quickstart

Get an org API key (`snops_key_...`) by registering at https://platform.sentnelops.com/register, then:

```bash
export SNOPS_API_KEY=snops_key_...
# optional, for self-hosted deployments:
# export SNOPS_BASE_URL=https://snops.internal.example
```

### 1. Register, approve, activate

Production agents start in `draft` and must be approved by a *different* person than the creator (segregation of duties), then activated, before policy will permit their calls. Dev and staging agents start `active` immediately.

```python
from sentnelops import AIRClient, PermissionDeniedError

with AIRClient() as client:   # picks up SNOPS_API_KEY / SNOPS_BASE_URL
    agent = client.register(
        name="prod-billing",
        owner="finance-team",
        environment="production",
        created_by="priya@example.com",
        allowed_mcp=["stripe-mcp"],
        denied_mcp=["payroll-mcp"],
        risk_level="high",          # high risk => 30-day review cadence
    )
    agent_id = agent["id"]

    # The token is shown EXACTLY ONCE — the server keeps only a hash.
    # In real code, write it to your secret manager, not stdout.
    print(f"one-time token: {agent['token']}")

    # approved_by must differ from created_by, or the API answers 403
    # with code "segregation_of_duties".
    client.approve(agent_id, approved_by="ciso@example.com",
                   note="scope reviewed: stripe-mcp only")
    client.activate(agent_id, actor="priya@example.com")

    # The whole story is on the append-only audit trail, newest first.
    for event in client.audit(agent_id):
        print(f"  audit: {event}")
```

Runnable version: [`examples/register_and_activate.py`](examples/register_and_activate.py).

### 2. Gate a code path on policy

`is_permitted` returns a `Decision`; `require` raises `PolicyViolation` on deny, so nothing below it runs unless policy says yes.

```python
from sentnelops import AIRClient, PolicyViolation

with AIRClient() as client:
    decision = client.is_permitted(agent_id, "stripe-mcp", tool="refund.create")
    print(decision.permitted, decision.reason, decision.policy_rule)

    try:
        client.require(agent_id, "aws-prod", tool="ec2.terminate")
        # ... the actual dangerous work goes here ...
    except PolicyViolation as e:
        print(f"blocked by policy: {e}")
        if e.decision and e.decision.policy_rule:
            print(f"  matched rule: {e.decision.policy_rule}")
```

These checks are advisory and client-side; the MCP proxy enforces the same policy engine on the real calls, so an agent cannot skip enforcement by not calling the SDK. Runnable version: [`examples/policy_gate.py`](examples/policy_gate.py).

### 3. Verify a caller (self-hosted MCP servers)

If you self-host SentnelOps and your MCP server shares the signing secret, it can validate calling agents locally — no network round trip, no API key. `verify_token` is a `@staticmethod`.

```python
import jwt  # PyJWT — installed with this SDK
from sentnelops import AIRClient

def handle_mcp_request(authorization_header: str) -> dict:
    token = authorization_header.removeprefix("Bearer ").strip()
    claims = AIRClient.verify_token(token, secret=SECRET,
                                    issuer="sentnelops.com")  # the default
    agent_id = claims["sub"]   # `sub` is the calling agent's id
    return claims              # raises jwt.InvalidTokenError on bad tokens
```

Hosted-platform users don't need this: the hosted proxy validates agent tokens before your MCP server sees the call. Runnable version: [`examples/verify_caller.py`](examples/verify_caller.py).

### 4. The same flow from a terminal

```bash
sentnelops register --name prod-billing --owner finance-team \
    --env production --allowed-mcp stripe-mcp --risk-level high
sentnelops approve agt_01j9x4m2e8 --by ciso@example.com
sentnelops activate agt_01j9x4m2e8 --actor priya@example.com

sentnelops check agt_01j9x4m2e8 stripe-mcp --tool refund.create
# PERMITTED: agent scope allows stripe-mcp; tool rule matched  [rule: stripe.refunds]
```

`sentnelops check` exits `2` on a deny (`1` on errors), so it can gate CI pipelines:

```bash
sentnelops check "$AGENT_ID" aws-prod --tool ec2.terminate || exit 1
```

## API overview

Everything importable from the package root: `AIRClient`, `Decision`, `DEFAULT_BASE_URL`, and the exception classes below.

### `AIRClient`

Construct with `AIRClient(api_key=None, base_url=None, timeout=10.0)`. `api_key` falls back to `SNOPS_API_KEY`, `base_url` to `SNOPS_BASE_URL`, then `https://api.sentnelops.com`. Use as a context manager (or call `close()`).

| Method | What it does |
|---|---|
| `register(name=, owner=, environment=, created_by=, allowed_mcp=, denied_mcp=, risk_level=)` | Register an agent; returns the record plus a one-time `token` (the agent's JWT) |
| `get(agent_id)` | Fetch one agent |
| `list(environment=, risk_level=, status=, owner=, limit=, offset=)` | List agents, newest first, with filters |
| `update(agent_id, actor=, owner=, risk_level=, allowed_mcp=, denied_mcp=)` | Update mutable fields (never `status`; scope is frozen while suspended) |
| `approve(agent_id, approved_by=, note="")` | `draft → approved`; approver must differ from creator |
| `activate(agent_id, actor=)` | `approved → active`; approval cannot be skipped |
| `suspend(agent_id, actor=, reason=)` | `active → suspended`; reason mandatory, policy denies its calls |
| `reactivate(agent_id, actor=)` | `suspended → active`, only while the suspension is under 30 days |
| `decommission(agent_id, actor=)` | Terminal; revokes every token, keeps history |
| `rotate(agent_id, actor=)` | Revoke current tokens, mint a new one (returned once as `token`) |
| `mark_reviewed(agent_id, actor=)` | Record an access review; next one scheduled by risk level (high 30d / medium 90d / low 180d) |
| `audit(agent_id)` | Append-only audit trail, newest first |
| `is_permitted(agent_id, mcp_server, tool=None)` | Ask the policy engine; returns `Decision(permitted, reason, policy_rule)` |
| `require(agent_id, mcp_server, tool=None)` | Like `is_permitted`, but raises `PolicyViolation` on deny |
| `verify_token(token, secret, issuer="sentnelops.com")` *(static)* | Decode + verify an agent JWT (HS256); returns claims or raises `jwt.InvalidTokenError` |

### Errors

Every non-2xx response maps to a typed exception; all subclass `SentnelOpsError` and carry `status_code` and a machine-readable `code` when the API provides one (e.g. `segregation_of_duties`, `terminal_state`, `scope_frozen`).

| Exception | When |
|---|---|
| `AuthenticationError` | 401 — missing, invalid, or revoked credential |
| `PermissionDeniedError` | 403 — role too low, or a governance rule refused (self-approval) |
| `NotFoundError` | 404 — unknown id, or another org's resource |
| `LifecycleError` | 409 — invalid lifecycle transition |
| `ValidationError` | 422 — request body did not validate |
| `RateLimitedError` | 429 — carries `retry_after` (seconds) |
| `APIError` | any other non-2xx |
| `PolicyViolation` | client-side, from `require()` on deny; carries `.decision` |

### CLI commands

`register`, `list`, `show`, `audit`, `approve`, `activate`, `suspend`, `reactivate`, `decommission`, `rotate`, `check`. Credentials come from `SNOPS_API_KEY` / `SNOPS_BASE_URL`; `--actor` / `--created-by` default to `$USER`. Full reference: [docs/cli.md](docs/cli.md).

## Documentation

| Doc | What's in it |
|---|---|
| [Getting started](docs/getting-started.md) | Install, auth, first agent end-to-end |
| [Agent identity](docs/agent-identity.md) | The identity model, one-time tokens, rotation, `verify_token` |
| [Lifecycle](docs/lifecycle.md) | The state machine `draft → approved → active ⇄ suspended → decommissioned` and its rules |
| [Policy checks](docs/policy-checks.md) | `is_permitted`, `require`, `Decision`, advisory vs. enforcement |
| [Errors](docs/errors.md) | Every exception class and what to do about it |
| [CLI](docs/cli.md) | Every subcommand with examples |

Runnable examples live in [`examples/`](examples/). Tests run offline against an `httpx.MockTransport` — `pip install -e ".[dev]" && pytest`.

## Learn more

- [SentnelOps](https://sentnelops.com) — the platform
- [What is AI agent runtime governance?](https://sentnelops.com/learn/ai-agent-runtime-governance)
- [Add policy enforcement to an MCP server](https://sentnelops.com/learn/add-policy-enforcement-to-mcp-server)
- [Platform quickstart](https://sentnelops.com/docs/quickstart)
- Sibling SDKs: [sentnelops-go](https://github.com/sentnelops/sentnelops-go), [sentnelops-node](https://github.com/sentnelops/sentnelops-node)

## License

MIT — see [LICENSE](LICENSE).
