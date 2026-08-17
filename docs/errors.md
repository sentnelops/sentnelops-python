# Errors

Every non-2xx API response maps to a typed exception, so you catch exactly the failure
you care about instead of parsing status codes. All of them subclass `SentnelOpsError`
and are importable from the package root:

```python
from sentnelops import (
    SentnelOpsError, AuthenticationError, PermissionDeniedError,
    NotFoundError, LifecycleError, ValidationError,
    RateLimitedError, APIError, PolicyViolation,
)
```

Every instance carries:

- `str(e)` — the human-readable message from the API
- `e.status_code` — the HTTP status (`None` for client-side errors)
- `e.code` — a machine-readable code when the API provides one
  (e.g. `segregation_of_duties`, `terminal_state`)

## The table

| Exception | HTTP | When it happens | What to do |
|---|---|---|---|
| `AuthenticationError` | 401 | Missing, invalid, or revoked API key | Check `SNOPS_API_KEY`; if the key was rotated, fetch the new one from your secret manager |
| `PermissionDeniedError` | 403 | Authenticated but not allowed: your principal's role is too low, or a governance rule refused (self-approval carries `e.code == "segregation_of_duties"`) | Use a principal with the required role — or, for SoD, have a *different person* approve |
| `NotFoundError` | 404 | Unknown id — or a resource belonging to another org (the API deliberately answers both identically) | Verify the agent id and that you're using the right org's key / base URL |
| `LifecycleError` | 409 | An invalid lifecycle transition — skipping approval, touching a terminal agent, editing frozen scope | Inspect `e.code` and fix the workflow; see [Lifecycle](lifecycle.md) |
| `ValidationError` | 422 | The request body did not validate (bad enum value, missing field) | Fix the arguments; the message names the offending field |
| `RateLimitedError` | 429 | Too many requests | Wait `e.retry_after` seconds (see below), then retry |
| `APIError` | 5xx / other | Any other non-2xx response, including server errors and unexpected shapes | Retry with backoff; if persistent, check platform status |
| `PolicyViolation` | — (client-side) | Raised by `client.require(...)` when the policy verdict is a deny | Handle the deny: skip the operation, log `e.decision`, alert a human |
| `SentnelOpsError` | — | Base class; also raised directly when the client is constructed with no API key at all | Catch-all; set `SNOPS_API_KEY` or pass `api_key=` |

## `RateLimitedError.retry_after`

When the API rate-limits you it sends a `Retry-After` header; the SDK parses it into
`retry_after` (a `float`, seconds — or `None` if the header was absent):

```python
import time
from sentnelops import RateLimitedError

try:
    agents = client.list()
except RateLimitedError as e:
    time.sleep(e.retry_after or 1.0)
    agents = client.list()
```

## Branching on `e.code`

Lifecycle and governance refusals carry a machine-readable code so you can
branch on the exact rule:

```python
from sentnelops import LifecycleError, PermissionDeniedError

try:
    client.approve(agent_id, approved_by=me)
except PermissionDeniedError as e:
    if e.code == "segregation_of_duties":
        print("someone else has to approve this one")
    else:
        raise
except LifecycleError as e:
    print(f"invalid transition: {e.code} — {e}")
```

Known codes and their meanings are listed in [Lifecycle](lifecycle.md).

## `PolicyViolation.decision`

`PolicyViolation` carries the full `Decision` (`permitted`, `reason`, `policy_rule`) —
see [Policy checks](policy-checks.md).

## One catch-all

Everything the SDK raises — including `PolicyViolation` — inherits from
`SentnelOpsError`, so a single `except SentnelOpsError` at the top of a script covers all
failure modes (this is exactly what the CLI does).

Note: transport-level failures (DNS, connection refused, timeouts) come from `httpx`
directly (e.g. `httpx.ConnectError`, `httpx.TimeoutException`) and are not wrapped.
