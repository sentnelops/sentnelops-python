# Policy checks

The SDK gives you two ways to ask the policy engine "may agent X call tool Y on MCP
server Z?" — one that returns a verdict, and one that raises on deny.

## `is_permitted` — ask for a verdict

```python
decision = client.is_permitted(agent_id, "stripe-mcp", tool="refund.create")
```

- `agent_id` — the agent whose scope and status are evaluated
- `mcp_server` — the MCP server name (as registered in your policy)
- `tool` — optional; omit it to check server-level access only

The result is a frozen dataclass:

```python
@dataclass(frozen=True)
class Decision:
    permitted: bool
    reason: str               # human-readable explanation, deny or allow
    policy_rule: str | None   # the rule that matched, when the engine names one
```

```python
if not decision.permitted:
    log.warning("policy denied %s: %s (rule=%s)",
                agent_id, decision.reason, decision.policy_rule)
```

The engine considers everything at once: the agent's lifecycle status (suspended and
decommissioned agents are denied), its `allowed_mcp` / `denied_mcp` scope, and tool-level
policy rules. Unlisted tools are denied by default.

## `require` — guard a code path in one line

`require` calls `is_permitted` and raises `PolicyViolation` on deny, so dangerous
operations read like an assertion:

```python
from sentnelops import PolicyViolation

def terminate_instance(client, agent_id, instance_id):
    client.require(agent_id, "aws-prod", tool="ec2.terminate")   # raises on deny
    # ...only reached when permitted...
    do_terminate(instance_id)
```

The exception carries the full decision for logging:

```python
try:
    client.require(agent_id, "aws-prod", tool="ec2.terminate")
except PolicyViolation as e:
    print(e)                        # the deny reason
    print(e.decision.policy_rule)   # which rule denied it
    # fail safe: skip the operation, page a human, etc.
```

On an allow, `require` returns the `Decision` — handy if you also want the matched rule.

A runnable version of this pattern is
[`examples/policy_gate.py`](../examples/policy_gate.py). The CLI equivalent is
`sentnelops check`, which exits `2` on deny so it can gate CI — see [CLI](cli.md).

## Advisory checks vs. runtime enforcement

These SDK checks are the **advisory, client-side complement** to SentnelOps enforcement —
not the enforcement itself:

- **Server-side (authoritative):** the transparent MCP proxy sits between your agents and
  their MCP servers and evaluates the *same* policy engine on every real call. Depending
  on mode it observes (records what *would* be blocked), blocks outright, or holds a call
  for human approval. An agent cannot skip it by not calling the SDK.
- **Client-side (this SDK):** `is_permitted` / `require` ask that same engine for a
  verdict *without making the call* — perfect for failing fast, gating a code path before
  expensive work, pre-flight checks in CI, or explaining a deny to a user.

Because both paths evaluate one engine, an SDK verdict today matches what the proxy will
do at runtime. Use the SDK check for ergonomics; rely on the proxy for guarantees.

## See also

- [Agent identity](agent-identity.md) — how `allowed_mcp` / `denied_mcp` scope is set
- [Lifecycle](lifecycle.md) — why a suspended agent is always denied
- [Errors](errors.md) — `PolicyViolation` and friends
