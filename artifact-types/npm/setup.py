#!/usr/bin/env python3
"""Provision the npm example: read-only npmjs proxy, hosted example-npm, a publishing robot.

Idempotent. Writes .robot.env (mode 600) with a freshly rotated robot secret.
Usage: HARBOR_URL=https://harbor.example.com HARBOR_PASS=... ./setup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import harborlib as hl  # noqa: E402

HOSTED = "example-npm"


def provision(h):
    hl.say("Proxy and hosted project")
    hl.ensure_shared_proxy(h, "npmjs")
    hl.ensure_hosted_project(h, HOSTED)
    hl.say("Robot that may publish to the hosted project")
    hl.robot_with_secret(h, "example-npm", "npm example: publish to example-npm",
                         hl.grant(hl.PUSH, HOSTED), Path(__file__).parent / ".robot.env")
    print(f"    resolve -> {hl.pkg_url(h, 'npm', 'npmjs')}/\n    publish -> {hl.pkg_url(h, 'npm', HOSTED)}/")


if __name__ == "__main__":
    hl.example_main(__doc__, provision)
