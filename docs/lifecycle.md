# Lifecycle

Every agent moves through a strict state machine. Illegal transitions are rejected by
the API and raised by the SDK as `LifecycleError` (409) — or `PermissionDeniedError`
(403) for self-approval — each with a machine-readable `code` telling you exactly
which rule you hit.

## The state machine

```
                approve            activate
   draft ────────────────▶ approved ────────▶ active
     (production agents                         │  ▲
      start here; dev and               suspend │  │ reactivate
      staging agents start                      ▼  │ (< 30 days)
      active)                              suspended
                                                │
              any non-terminal state ───────────┴──▶ decommissioned
                          decommission               (terminal)
```

## Transitions

| Method | Transition | Rules |
|---|---|---|
| `approve(agent_id, approved_by=..., note="")` | `draft → approved` | `approved_by` **must differ from the creator** (segregation of duties) |
| `activate(agent_id, actor=...)` | `approved → active` | Approval cannot be skipped |
| `suspend(agent_id, actor=..., reason=...)` | `active → suspended` | `reason` is mandatory; scope freezes; policy denies the agent's calls |
| `reactivate(agent_id, actor=...)` | `suspended → active` | Only while the suspension is **under 30 days** old |
| `decommission(agent_id, actor=...)` | `* → decommissioned` | Terminal; revokes every token; history is kept |

Every transition is recorded in the append-only audit trail with the acting identity —
retrieve it with `client.audit(agent_id)`.

## Errors for illegal transitions

Invalid transitions surface as `LifecycleError` (HTTP 409); self-approval is the
one exception — the API treats it as a permission refusal (HTTP 403), so it
surfaces as `PermissionDeniedError`. Both carry a machine-readable `e.code`:

```python
from sentnelops import PermissionDeniedError

try:
    client.approve(agent_id, approved_by="priya@example.com")  # priya also created it
except PermissionDeniedError as e:
    print(e.code)   # "segregation_of_duties"
```

| `code` | Raised as | You tried to... |
|---|---|---|
| `segregation_of_duties` | `PermissionDeniedError` | Approve an agent you created yourself |
| `terminal_state` | `LifecycleError` | Transition a decommissioned agent — there is no way back |
| `scope_frozen` | `LifecycleError` | Change `allowed_mcp` / `denied_mcp` (via `update`) while suspended |

Other invalid jumps — activating a `draft` without approval, suspending a non-active
agent, reactivating something that isn't suspended — are also `LifecycleError`s; the
message names the current state and the transition you attempted.

## Suspension freezes scope

Suspension is an incident posture: policy denies the agent's calls **and** its scope is
frozen — `update` calls that touch `allowed_mcp`/`denied_mcp` are rejected
(`scope_frozen`) so nobody widens permissions on a benched agent. Reactivation restores
the agent exactly as it was.

## The 30-day stale-suspension rule

`reactivate` works only while the suspension is under 30 days old. Older suspensions are
treated as effectively retired: they need a **fresh approval** (by someone other than the
creator, as always) before returning to service. This prevents long-forgotten agents from
quietly coming back with stale scope.

## Risk-based review cadence

Active agents are due for periodic access review, scheduled by `risk_level`:

| Risk | Review every |
|---|---|
| `high` | 30 days |
| `medium` | 90 days |
| `low` | 180 days |

When a review is done, record it — the next one is scheduled automatically:

```python
client.mark_reviewed(agent_id, actor="ciso@example.com")
```

Agents that blow past their review deadline get flagged by the platform's daily sweep and
show up in the dashboard; the audit trail records each flag once per deadline.

## See also

- [Getting started](getting-started.md) — the draft → approve → activate walkthrough
- [Errors](errors.md) — the full exception table
- [CLI](cli.md) — every transition as a terminal command
