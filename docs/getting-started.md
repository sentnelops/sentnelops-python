# Getting started

## Install

```bash
pip install sentnelops
```

Python 3.10+. Dependencies: `httpx` and `PyJWT`, nothing else.

## Authentication

The client authenticates with your **org API key** (`snops_key_...`). Get one by
registering an org at https://platform.sentnelops.com/register — it is shown exactly once.

Two ways to supply credentials:

```bash
# Environment (recommended — also what the CLI uses)
export SNOPS_API_KEY=snops_key_...
export SNOPS_BASE_URL=https://api.sentnelops.com   # optional; this is the default
```

```python
# Or constructor arguments
from sentnelops import AIRClient

client = AIRClient(
    api_key="snops_key_...",                  # falls back to SNOPS_API_KEY
    base_url="https://snops.internal.example",  # falls back to SNOPS_BASE_URL,
                                                # then https://api.sentnelops.com
    timeout=10.0,                             # per-request timeout, seconds
)
```

Self-hosting? Point `base_url` / `SNOPS_BASE_URL` at your deployment — the SDK is
otherwise identical.

## Context-manager usage

`AIRClient` holds an HTTP connection pool. Use it as a context manager so it closes
cleanly, or call `client.close()` yourself:

```python
with AIRClient() as client:
    agents = client.list(environment="production")
```

## Your first agent, end to end

**Dev agents start `active` immediately** — register and go:

```python
with AIRClient() as client:
    agent = client.register(
        name="local-experiment",
        owner="ml-platform",
        environment="dev",
        created_by="dev@example.com",
    )
    print(agent["status"])   # "active"
    print(agent["token"])    # the agent's JWT — shown exactly once
```

**Production agents start in `draft`** (dev and staging self-activate) and must pass
two more gates before policy will permit their calls:

```python
with AIRClient() as client:
    # 1. Register — created_by records who is asking.
    agent = client.register(
        name="prod-billing", owner="finance-team",
        environment="production", created_by="priya@example.com",
        allowed_mcp=["stripe-mcp"], risk_level="high",
    )
    token = agent["token"]   # store securely NOW — never shown again

    # 2. Approve — MUST be a different person than created_by.
    #    Segregation of duties: self-approval is rejected with a
    #    PermissionDeniedError (code "segregation_of_duties").
    client.approve(agent["id"], approved_by="ciso@example.com",
                   note="reviewed scope, high-risk cadence applies")

    # 3. Activate — approval cannot be skipped.
    client.activate(agent["id"], actor="priya@example.com")

    # Now policy will consider its calls.
    d = client.is_permitted(agent["id"], "stripe-mcp", tool="refund.create")
    print(d.permitted, d.reason)
```

A runnable version of this flow is in
[`examples/register_and_activate.py`](../examples/register_and_activate.py).

## Where next

- [Agent identity](agent-identity.md) — record fields, token semantics, rotation
- [Lifecycle](lifecycle.md) — the full state machine and its rules
- [Policy checks](policy-checks.md) — guarding code paths with `require`
- [CLI](cli.md) — the same flow from a terminal
