"""A self-hosted MCP server validating incoming agent JWTs.

If you self-host SentnelOps, your MCP server can share the SentnelOps signing
secret and verify calling agents locally — no network round trip, no API key.
``AIRClient.verify_token`` is a staticmethod: decode + verify (HS256) and
return the claims, or raise ``jwt.InvalidTokenError``.

Hosted-platform users don't need this: the hosted SentnelOps proxy validates
agent tokens before your MCP server ever sees the call.

Run it (demo mode — mints a token locally, then verifies it):

    export SNOPS_SIGNING_SECRET=your-shared-hs256-secret
    python examples/verify_caller.py
"""
import os
import sys
import time

import jwt  # PyJWT — installed with the sentnelops package

from sentnelops import AIRClient

# The HS256 secret your SentnelOps deployment signs agent tokens with.
# Distribute it to your MCP servers via your secret manager — never hardcode.
SECRET = os.environ.get("SNOPS_SIGNING_SECRET", "demo-secret-do-not-use")


def handle_mcp_request(authorization_header: str) -> dict:
    """What your MCP server does on every incoming call.

    Returns the verified claims, or raises jwt.InvalidTokenError — in a real
    server you'd translate that into a 401 response.
    """
    token = authorization_header.removeprefix("Bearer ").strip()

    claims = AIRClient.verify_token(
        token,
        secret=SECRET,
        issuer="sentnelops.com",   # the default; override if your deployment
    )                              # issues tokens under a different issuer

    agent_id = claims["sub"]       # `sub` is the calling agent's id
    print(f"verified caller: agent {agent_id}")
    return claims


def main() -> int:
    # --- demo only: mint a token the way SentnelOps would ----------------
    demo_token = jwt.encode(
        {"sub": "agt_example", "iss": "sentnelops.com",
         "iat": int(time.time()), "exp": int(time.time()) + 300},
        SECRET, algorithm="HS256")

    # --- the part that belongs in your MCP server -------------------------
    try:
        claims = handle_mcp_request(f"Bearer {demo_token}")
        print(f"claims: {claims}")
    except jwt.InvalidTokenError as e:
        # Bad signature, wrong issuer, expired — reject the call with a 401.
        print(f"rejected caller: {e}", file=sys.stderr)
        return 1

    # A tampered token must fail:
    try:
        handle_mcp_request(f"Bearer {demo_token[:-2]}xx")
    except jwt.InvalidTokenError:
        print("tampered token correctly rejected")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
