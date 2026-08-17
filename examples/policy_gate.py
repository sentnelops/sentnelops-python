"""Guard a dangerous operation with client.require(...).

``require`` asks the SentnelOps policy engine for a verdict and raises
``PolicyViolation`` on a deny — so the risky code path below it is only ever
reached when policy says yes. This is the advisory, client-side complement to
the server-side MCP proxy, which enforces the same policy on the real calls.

Run it:

    export SNOPS_API_KEY=snops_key_...
    export SNOPS_AGENT_ID=agt_...        # an agent you registered
    python examples/policy_gate.py
"""
import os
import sys

from sentnelops import AIRClient, PolicyViolation

AGENT_ID = os.environ.get("SNOPS_AGENT_ID", "agt_example")


def terminate_instance(client: AIRClient, instance_id: str) -> None:
    """Terminate an EC2 instance — but only if policy permits it."""
    # One line, fail-closed: raises PolicyViolation on deny, returns the
    # Decision on allow. Nothing below runs unless the check passes.
    decision = client.require(AGENT_ID, "aws-prod", tool="ec2.terminate")
    print(f"permitted ({decision.reason})"
          + (f" [rule: {decision.policy_rule}]" if decision.policy_rule else ""))

    # ... the actual dangerous work would go here ...
    print(f"terminating {instance_id} (not really — this is a demo)")


def main() -> int:
    with AIRClient() as client:
        try:
            terminate_instance(client, "i-0abc123def456")
        except PolicyViolation as e:
            # Fail safe: log the full decision and do NOT do the thing.
            print(f"blocked by policy: {e}", file=sys.stderr)
            if e.decision and e.decision.policy_rule:
                print(f"  matched rule: {e.decision.policy_rule}",
                      file=sys.stderr)
            return 2  # same convention as `sentnelops check`
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
