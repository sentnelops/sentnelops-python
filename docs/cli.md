# CLI

Installing the package gives you the `sentnelops` command — the full agent lifecycle from
a terminal. Credentials come from the environment:

```bash
export SNOPS_API_KEY=snops_key_...
export SNOPS_BASE_URL=https://api.sentnelops.com   # optional; or your own deployment
```

Most commands print the resulting record as JSON. Any API error prints `error: ...` to
stderr and exits `1`. Where a command takes `--actor` or `--created-by`, it defaults to
your shell `$USER` — pass a real identity in shared environments so the audit trail is
attributable.

## register

`--env` is one of `production`, `staging`, `dev`; `--risk-level` is `low`/`medium`/`high`
(default `medium`); MCP lists are comma-separated.

```bash
$ sentnelops register --name prod-billing --owner finance-team \
    --env production --allowed-mcp stripe-mcp --denied-mcp payroll-mcp \
    --risk-level high --created-by priya@example.com
agent registered
  id:     agt_01j9x4m2e8
  status: draft
  token:  eyJhbGciOiJIUzI1NiIs...
  (token is shown once — store it securely)
```

## list

Optional filters: `--env`, `--status`, `--risk-level`, `--owner`; paging with
`--limit` (default 50) and `--offset`.

```bash
$ sentnelops list --env production --status active
[
  {
    "id": "agt_01j9x4m2e8",
    "name": "prod-billing",
    "owner": "finance-team",
    "environment": "production",
    "status": "active",
    "risk_level": "high"
  }
]
```

## show / audit

```bash
$ sentnelops show agt_01j9x4m2e8          # one agent, as JSON
$ sentnelops audit agt_01j9x4m2e8         # append-only trail, newest first
[
  {"event": "activated", "actor": "priya@example.com", "at": "2026-08-17T09:14:02Z"},
  {"event": "approved",  "actor": "ciso@example.com",  "at": "2026-08-17T09:12:40Z"},
  {"event": "registered","actor": "priya@example.com", "at": "2026-08-17T09:11:05Z"}
]
```

## Lifecycle: approve, activate, suspend, reactivate, decommission

```bash
$ sentnelops approve agt_01j9x4m2e8 --by ciso@example.com --note "scope reviewed"
$ sentnelops activate agt_01j9x4m2e8 --actor priya@example.com
$ sentnelops suspend agt_01j9x4m2e8 --reason "anomalous refund volume" --actor soc@example.com
$ sentnelops reactivate agt_01j9x4m2e8 --actor soc@example.com     # only < 30 days in
$ sentnelops decommission agt_01j9x4m2e8 --actor priya@example.com # terminal, revokes all tokens
```

Segregation of duties is enforced: `approve --by` must differ from the agent's creator,
or the command fails. `suspend --reason` is mandatory. Each prints the updated record.

## rotate

```bash
$ sentnelops rotate agt_01j9x4m2e8 --actor priya@example.com
new token: eyJhbGciOiJIUzI1NiIs...
(shown once — the old token is revoked)
```

## check — and gating CI

```bash
$ sentnelops check agt_01j9x4m2e8 stripe-mcp --tool refund.create
PERMITTED: agent scope allows stripe-mcp; tool rule matched  [rule: stripe.refunds]

$ sentnelops check agt_01j9x4m2e8 payroll-mcp
DENIED: payroll-mcp is in the agent's denied_mcp list
```

`check` exits `2` on a deny (and `1` on errors), so it drops straight into a pipeline:

```bash
sentnelops check "$AGENT_ID" aws-prod --tool ec2.terminate || exit 1
```

## See also

- [Getting started](getting-started.md) — the same flow in Python
- [Lifecycle](lifecycle.md) — what each transition means and when it's rejected
- [Errors](errors.md) — what the failure messages correspond to
