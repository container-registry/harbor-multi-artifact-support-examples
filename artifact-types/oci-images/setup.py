#!/usr/bin/env python3
"""Provision the OCI image example: multi-project example-images over the dockerhub proxy, plus a robot.

Idempotent. Writes .robot.env (mode 600) with a freshly rotated robot secret.
Usage: HARBOR_URL=https://harbor.example.com HARBOR_PASS=... ./setup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import harborlib as hl  # noqa: E402

MULTI = "example-images"


def provision(h):
    hl.say("Docker Hub proxy and the multi-project in front of it")
    hl.ensure_shared_proxy(h, "dockerhub")
    hl.ensure_multi_project(h, MULTI, [("dockerhub", 1)], public=False)
    hl.say("Robot that may push and pull")
    hl.robot_with_secret(h, "example-images", "OCI image example: push and pull example-images",
                         hl.grant(hl.PUSH, MULTI), Path(__file__).parent / ".robot.env")
    host = h.url.split("://", 1)[1]
    print(f"    push and pull -> {host}/{MULTI}/<image>\n    Docker Hub    -> {host}/{MULTI}/library/<image>")


if __name__ == "__main__":
    hl.example_main(__doc__, provision)
