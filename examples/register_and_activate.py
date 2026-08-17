"""Register a production agent, then approve and activate it.

Production agents start in ``draft`` and must clear two gates before policy
will permit their calls:

  1. approve  — by a DIFFERENT person than the creator (segregation of duties)
  2. activate — approval cannot be skipped

Run it:

    export SNOPS_API_KEY=snops_key_...
    # optional, for self-hosted deployments:
    # export SNOPS_BASE_URL=https://snops.internal.example
    python examples/register_and_activate.py
"""
import os
import sys

from sentnelops import AIRClient, LifecycleError

# Who is doing what. In a real workflow these are two different humans (or a
# human and a CI identity) — the API rejects self-approval.
CREATOR = os.environ.get("SNOPS_CREATOR", "priya@example.com")
APPROVER = os.environ.get("SNOPS_APPROVER", "ciso@example.com")


def main() -> int:
    # The client picks up SNOPS_API_KEY / SNOPS_BASE_URL from the environment.
    with AIRClient() as client:
        # -- 1. Register -------------------------------------------------
        # Production agents are born in "draft": registered, credentialed,
        # but not yet permitted to do anything.
        agent = client.register(
            name="prod-billing",
            owner="finance-team",
            environment="production",
            created_by=CREATOR,
            allowed_mcp=["stripe-mcp"],
            denied_mcp=["payroll-mcp"],
            risk_level="high",          # high risk => 30-day review cadence
        )
        agent_id = agent["id"]
        print(f"registered {agent_id} (status: {agent['status']})")

        # The token is shown EXACTLY ONCE — the server keeps only a hash.
        # In real code, write it to your secret manager here, not stdout.
        print(f"one-time token: {agent['token']}")
        print("(store it securely — it is never retrievable again)")

        # -- 2. Approve (as a second identity) ---------------------------
        # Segregation of duties: approved_by must differ from created_by,
        # otherwise the API answers with code "segregation_of_duties".
        try:
            client.approve(agent_id, approved_by=APPROVER,
                           note="scope reviewed: stripe-mcp only")
        except LifecycleError as e:
            print(f"approval rejected ({e.code}): {e}", file=sys.stderr)
            return 1
        print(f"approved by {APPROVER}")

        # -- 3. Activate --------------------------------------------------
        updated = client.activate(agent_id, actor=CREATOR)
        print(f"activated (status: {updated['status']})")

        # The whole story is on the audit trail, newest first.
        for event in client.audit(agent_id):
            print(f"  audit: {event}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
