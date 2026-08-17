# Agent identity

Every agent in SentnelOps is a first-class identity: owned, scoped, auditable, and
revocable. This page covers the agent record, token semantics, and how self-hosted MCP
servers can validate callers directly.

## The agent record

`client.register(...)` creates the record and mints the credential. `client.get(agent_id)`
and `client.list(...)` return records with these fields:

| Field | Set by | Meaning |
|---|---|---|
| `id` | server | The agent's stable identifier — use it in every other call |
| `name` | you | Human-readable name |
| `owner` | you | The team or person accountable for the agent |
| `environment` | you | `production`, `staging`, or `dev` — drives the starting lifecycle state |
| `status` | server | Lifecycle state (see [Lifecycle](lifecycle.md)) |
| `risk_level` | you | `low`, `medium` (default), or `high` — drives review cadence |
| `allowed_mcp` | you | MCP servers the agent may call |
| `denied_mcp` | you | MCP servers explicitly denied (deny wins) |
| `created_by` | you | Who registered it — matters for segregation of duties |

Mutable fields (`owner`, `risk_level`, `allowed_mcp`, `denied_mcp`) change via
`client.update(agent_id, actor=..., ...)`. Status never changes via `update` — only
through the lifecycle methods. Scope changes are rejected while the agent is suspended.

## One-time tokens

Registration returns the agent record **plus one extra key, `token`** — the agent's JWT:

```python
agent = client.register(name="etl-bot", owner="data", environment="dev",
                        created_by="dev@example.com")
token = agent["token"]   # shown exactly once
```

- The token is shown **exactly once**. It is stored only as a hash server-side and can
  never be retrieved again — not by you, not by support.
- Store it in a secret manager immediately. If you lose it, rotate.
- The token is what the *agent* presents when calling MCP tools through the SentnelOps
  proxy. It is distinct from your org API key (which authenticates *you*, the SDK/CLI).

## Rotation

```python
out = client.rotate(agent_id, actor="priya@example.com")
new_token = out["token"]   # again: shown once
```

`rotate` revokes the agent's current tokens and mints a new one. The old token stops
working at the proxy **within seconds** — rotation is the fast path when a credential
leaks. Rotate routinely, and always pass a real `actor` so the audit trail says who did it.

## Decommission revokes everything

`client.decommission(agent_id, actor=...)` is terminal: every token the agent ever had is
revoked, and the record plus full audit history is kept forever. There is no
un-decommission — register a new agent instead. See [Lifecycle](lifecycle.md).

## `verify_token` — for self-hosted MCP servers

If you self-host SentnelOps and your MCP server shares the SentnelOps signing secret, it
can validate calling agents directly without a network round trip:

```python
from sentnelops import AIRClient
import jwt  # PyJWT — installed with this SDK

try:
    claims = AIRClient.verify_token(
        incoming_bearer_token,
        secret=os.environ["MY_SIGNING_SECRET"],   # the shared HS256 secret
        issuer="sentnelops.com",                  # default; override if you changed it
    )
    agent_id = claims["sub"]   # the calling agent's id
except jwt.InvalidTokenError:
    ...  # reject the request
```

Notes:

- It is a `@staticmethod` — no client instance or API key required.
- Verification is **HS256 with a shared secret**. Hosted-platform users don't need this:
  the hosted proxy validates tokens for you and never shares its signing secret.
- Raises `jwt.InvalidTokenError` (from PyJWT) on bad signature, wrong issuer, or expiry.

Runnable example: [`examples/verify_caller.py`](../examples/verify_caller.py).

## See also

- [Lifecycle](lifecycle.md) — what `status` can be and how it changes
- [Policy checks](policy-checks.md) — how scope becomes decisions
