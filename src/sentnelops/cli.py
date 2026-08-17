"""``sentnelops`` CLI — the full agent lifecycle from a terminal.

Credentials come from the environment:

    export SNOPS_API_KEY=snops_key_...
    export SNOPS_BASE_URL=https://api.sentnelops.com   # or your deployment

    sentnelops register --name prod-billing --owner finance-team \
        --env production --allowed-mcp stripe-mcp --risk-level high
    sentnelops list --env production --status active
    sentnelops approve <agent-id> --by ciso@example.com
    sentnelops activate <agent-id>
    sentnelops check <agent-id> stripe-mcp --tool refund.create
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .client import AIRClient
from .errors import SentnelOpsError

_ME = os.environ.get("USER", "cli")


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser(
        prog="sentnelops",
        description="SentnelOps agent identity registry")
    sub = p.add_subparsers(dest="cmd", required=True)

    reg = sub.add_parser("register", help="register an agent (token shown once)")
    reg.add_argument("--name", required=True)
    reg.add_argument("--owner", required=True)
    reg.add_argument("--env", required=True, dest="environment",
                     choices=["production", "staging", "dev"])
    reg.add_argument("--allowed-mcp", default="",
                     help="comma-separated MCP server names")
    reg.add_argument("--denied-mcp", default="")
    reg.add_argument("--risk-level", default="medium",
                     choices=["low", "medium", "high"])
    reg.add_argument("--created-by", default=_ME)

    ls = sub.add_parser("list", help="list agents")
    ls.add_argument("--env", dest="environment")
    ls.add_argument("--status")
    ls.add_argument("--risk-level")
    ls.add_argument("--owner")
    ls.add_argument("--limit", type=int, default=50)
    ls.add_argument("--offset", type=int, default=0)

    show = sub.add_parser("show", help="show one agent")
    show.add_argument("agent_id")

    aud = sub.add_parser("audit", help="show an agent's audit trail")
    aud.add_argument("agent_id")

    ap = sub.add_parser("approve", help="approve a draft agent (SoD enforced)")
    ap.add_argument("agent_id")
    ap.add_argument("--by", required=True, dest="approved_by",
                    help="approver identity — must differ from the creator")
    ap.add_argument("--note", default="")

    for name, help_ in (("activate", "approved → active"),
                        ("reactivate", "suspended → active (<30 days)"),
                        ("decommission", "terminal: revoke all tokens"),
                        ("rotate", "revoke tokens, mint a new one")):
        c = sub.add_parser(name, help=help_)
        c.add_argument("agent_id")
        c.add_argument("--actor", default=_ME)

    su = sub.add_parser("suspend", help="active → suspended (reason required)")
    su.add_argument("agent_id")
    su.add_argument("--reason", required=True)
    su.add_argument("--actor", default=_ME)

    ck = sub.add_parser("check", help="ask policy for a verdict")
    ck.add_argument("agent_id")
    ck.add_argument("mcp_server")
    ck.add_argument("--tool")

    args = p.parse_args()
    try:
        with AIRClient() as client:
            _run(client, args)
    except SentnelOpsError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def _run(client: AIRClient, args) -> None:
    if args.cmd == "register":
        agent = client.register(
            name=args.name, owner=args.owner,
            environment=args.environment, created_by=args.created_by,
            risk_level=args.risk_level,
            allowed_mcp=[s for s in args.allowed_mcp.split(",") if s],
            denied_mcp=[s for s in args.denied_mcp.split(",") if s])
        token = agent.pop("token")
        print("agent registered")
        print(f"  id:     {agent['id']}")
        print(f"  status: {agent['status']}")
        print(f"  token:  {token}")
        print("  (token is shown once — store it securely)")
    elif args.cmd == "list":
        _print(client.list(environment=args.environment, status=args.status,
                           risk_level=args.risk_level, owner=args.owner,
                           limit=args.limit, offset=args.offset))
    elif args.cmd == "show":
        _print(client.get(args.agent_id))
    elif args.cmd == "audit":
        _print(client.audit(args.agent_id))
    elif args.cmd == "approve":
        _print(client.approve(args.agent_id, approved_by=args.approved_by,
                              note=args.note))
    elif args.cmd == "activate":
        _print(client.activate(args.agent_id, actor=args.actor))
    elif args.cmd == "suspend":
        _print(client.suspend(args.agent_id, actor=args.actor,
                              reason=args.reason))
    elif args.cmd == "reactivate":
        _print(client.reactivate(args.agent_id, actor=args.actor))
    elif args.cmd == "decommission":
        _print(client.decommission(args.agent_id, actor=args.actor))
    elif args.cmd == "rotate":
        out = client.rotate(args.agent_id, actor=args.actor)
        token = out.pop("token")
        print(f"new token: {token}")
        print("(shown once — the old token is revoked)")
    elif args.cmd == "check":
        d = client.is_permitted(args.agent_id, args.mcp_server,
                                tool=args.tool)
        verdict = "PERMITTED" if d.permitted else "DENIED"
        print(f"{verdict}: {d.reason}"
              + (f"  [rule: {d.policy_rule}]" if d.policy_rule else ""))
        if not d.permitted:
            sys.exit(2)


if __name__ == "__main__":
    main()
