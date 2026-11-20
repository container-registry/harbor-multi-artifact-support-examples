#!/usr/bin/env python3
"""Provision the Helm example: private hosted project example-helm and a robot.

Idempotent. Writes .robot.env (mode 600) with a freshly rotated robot secret.
Usage: HARBOR_URL=https://harbor.example.com HARBOR_PASS=... ./setup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import harborlib as hl  # noqa: E402

HOSTED = "example-helm"


def provision(h):
    hl.say("Hosted project")
    hl.ensure_hosted_project(h, HOSTED, public=False)
    hl.say("Robot that may push and pull")
    hl.robot_with_secret(h, "example-helm", "Helm example: push and pull example-helm",
                         hl.grant(hl.PUSH, HOSTED), Path(__file__).parent / ".robot.env")
    print(f"    charts -> oci://{h.url.split('://', 1)[1]}/{HOSTED}")


if __name__ == "__main__":
    hl.example_main(__doc__, provision)
