#!/usr/bin/env python3
"""Provision the Homebrew example: private proxy of formulae.brew.sh and ghcr.io bottles, plus brew.env.

Idempotent. Rotates the pull-only robot's secret and writes the brew client settings
to brew.env (mode 600). Usage: HARBOR_URL=https://harbor.example.com HARBOR_PASS=... ./setup.py
"""
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import harborlib as hl  # noqa: E402

PROXY = "brew-proxy"
HERE = Path(__file__).parent


def client_env(url, user, secret):
    parts = urllib.parse.urlsplit(url)
    enc = lambda s: urllib.parse.quote(s, safe="")  # noqa: E731
    base = f"{parts.scheme}://{parts.netloc}/homebrew/{PROXY}"
    # brew sends no credentials to HOMEBREW_API_DOMAIN, so they ride in the URL.
    api = f"{parts.scheme}://{enc(user)}:{enc(secret)}@{parts.netloc}/homebrew/{PROXY}/api"
    token = base64.b64encode(f"{user}:{secret}".encode()).decode()
    return (f"HOMEBREW_API_DOMAIN={api}\n"
            f"HOMEBREW_ARTIFACT_DOMAIN={base}\n"
            "HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1\n"
            f"HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN={token}\n"
            # brew update git-fetches brew itself from github.com, which the proxy does not serve.
            "HOMEBREW_NO_AUTO_UPDATE=1\n")


def provision(h):
    hl.say("Homebrew proxy")
    rid = hl.ensure_endpoint(h, "homebrew", "homebrew", "https://formulae.brew.sh/api")
    hl.ensure_proxy_project(h, PROXY, "homebrew", rid, public=False)
    hl.say("Pull-only robot and brew client settings")
    user, secret = hl.robot_with_secret(h, "example-brew", "Homebrew example: pull from brew-proxy",
                                        hl.grant(hl.PULL, PROXY), HERE / ".robot.env")
    out = HERE / "brew.env"
    out.touch(mode=0o600)
    out.write_text(client_env(h.url, user, secret))
    hl.ok(f"brew client settings written to {out.name} (mode 600)")
    req = urllib.request.Request(f"{h.url}/homebrew/{PROXY}/api/formula/jq.json", headers={
        "Authorization": "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()})
    try:
        with urllib.request.urlopen(req) as resp:
            hl.ok(f"robot reads formula metadata through the proxy (jq {json.load(resp)['versions']['stable']})")
    except (urllib.error.HTTPError, json.JSONDecodeError) as e:
        hl.die(f"robot cannot read formula metadata: {e}")


if __name__ == "__main__":
    hl.example_main(__doc__, provision)
