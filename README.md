# sentnelops

**License: MIT** · **Python 3.10+** · **PyPI: `sentnelops`**

Give your AI agents an identity, a lifecycle, and least-privilege tool policy — in a few
lines of Python. SentnelOps is a control plane for AI agents: a registry where every agent
is a first-class, owned, auditable identity; a lifecycle state machine with segregation of
duties; tool-level policy over MCP servers; and runtime enforcement through a transparent
MCP proxy. This SDK is the developer surface for all of it. It is free to use against the
hosted platform ([platform.sentnelops.com](https://platform.sentnelops.com)) and works
identically against self-hosted deployments — just point `SNOPS_BASE_URL` at your own API.

## Install

```bash
pip install sentnelops
```

## 60-second quickstart

```python
from sentnelops import AIRClient, PolicyViolation

with AIRClient(api_key="snops_key_...") as client:   # or set SNOPS_API_KEY
    # 1. Register an agent — its credential is minted here, shown exactly once.
    agent = client.register(
        name="prod-billing",
        owner="finance-team",
        environment="production",
        created_by="priya@example.com",
        allowed_mcp=["stripe-mcp"],
        denied_mcp=["payroll-mcp"],
        risk_level="high",
    )
    print(agent["id"])
    print(agent["token"])   # store this securely — it is never retrievable again

    # 2. Ask policy for a verdict before doing something.
    decision = client.is_permitted(agent["id"], "stripe-mcp", tool="refund.create")
    if not decision.permitted:
        print("denied:", decision.reason)

    # 3. Or guard a code path in one line — raises PolicyViolation on deny.
    try:
        client.require(agent["id"], "stripe-mcp", tool="refund.create")
        # ... perform the refund ...
    except PolicyViolation as e:
        print("blocked:", e.decision.reason)
```

Production agents start in `draft` and must be approved by a *different* person than the
creator, then activated, before policy will permit their calls. See
[docs/getting-started.md](docs/getting-started.md) for the full flow.

## CLI

Everything the client does is also a terminal command:

```bash
export SNOPS_API_KEY=snops_key_...

sentnelops register --name prod-billing --owner finance-team \
    --env production --allowed-mcp stripe-mcp --risk-level high

sentnelops check agt_01j9x4 stripe-mcp --tool refund.create
# PERMITTED: agent scope allows stripe-mcp; tool rule matched  [rule: stripe.refunds]
```

`sentnelops check` exits with status `2` on a deny, so it can gate CI pipelines.
Full reference: [docs/cli.md](docs/cli.md).

## Features

- **Agent identity registry** — every agent has an owner, environment, risk level, and scope.
- **Lifecycle with segregation of duties** — `draft → approved → active ⇄ suspended → decommissioned`; the approver must differ from the creator.
- **One-time, revocable tokens + rotation** — the agent JWT is shown exactly once; rotation revokes the old token within seconds; decommission revokes everything.
- **Policy checks** — `is_permitted` / `require` return a typed `Decision` from the same engine that powers server-side enforcement.
- **Audit trail** — an append-only history of every registration, transition, and rotation.
- **Typed errors** — one exception class per failure mode, with machine-readable codes.
- **Zero dependency drama** — just `httpx` and `PyJWT`.

## Documentation

| Doc | What's in it |
|---|---|
| [Getting started](docs/getting-started.md) | Install, auth, first agent end-to-end |
| [Agent identity](docs/agent-identity.md) | The identity model, tokens, rotation, `verify_token` |
| [Lifecycle](docs/lifecycle.md) | The state machine, transitions, and their errors |
| [Policy checks](docs/policy-checks.md) | `is_permitted`, `require`, `Decision`, `PolicyViolation` |
| [Errors](docs/errors.md) | Every exception class and what to do about it |
| [CLI](docs/cli.md) | Every subcommand with examples |

Runnable examples live in [`examples/`](examples/).

## Getting an API key

Register an org at **https://platform.sentnelops.com/register** — self-serve, no sales
call. Your org API key (`snops_key_...`) is shown exactly once at registration; store it
in a secret manager and pass it via `SNOPS_API_KEY`.

## License

MIT — see [LICENSE](LICENSE).
