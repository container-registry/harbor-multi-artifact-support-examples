#!/usr/bin/env python3
"""Provision a Homebrew pull-through proxy on an 8gcr/Harbor instance.

Creates, idempotently:
  1. registry endpoint `homebrew` (formula metadata from formulae.brew.sh,
     bottles from ghcr.io)
  2. private proxy-cache project `brew-priv` bound to it
  3. project robot `brew-puller` that can pull and nothing else

then writes the settings an intranet brew client needs to an env file
(mode 600) and checks that the robot can read formula metadata through the
proxy. Harbor never returns an existing robot secret, so every run rotates it.

Usage:
  HARBOR_URL=https://8gcr.container-registry.dev HARBOR_PASS=... \\
    ./homebrew/setup-homebrew.py [--out brew.env]
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "homebrew"
UPSTREAM = "https://formulae.brew.sh/api"
PROJECT = "brew-priv"
ROBOT = "brew-puller"
PULL_ONLY = [{"kind": "project", "namespace": PROJECT,
              "access": [{"resource": "repository", "action": "pull"}]}]


def die(msg):
    sys.exit(f"  x {msg}")


def ok(msg):
    print(f"  ok {msg}")


def basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class Harbor:
    def __init__(self, url, user, password):
        self.url = url.rstrip("/")
        self.auth = basic(user, password)

    def call(self, method, path, body=None, expect=(200,)):
        req = urllib.request.Request(
            f"{self.url}/api/v2.0{path}", method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": self.auth, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                code, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        if code not in expect:
            die(f"{method} {path} -> HTTP {code}: {raw.decode(errors='replace')}")
        return code, json.loads(raw) if raw.strip() else None


def ensure_endpoint(h):
    q = urllib.parse.quote(f"name={ENDPOINT}")
    find = lambda: next((r for r in h.call("GET", f"/registries?q={q}")[1] or []
                         if r["name"] == ENDPOINT), None)
    reg = find()
    if reg is None:
        h.call("POST", "/registries", {"name": ENDPOINT, "type": "homebrew",
                                       "url": UPSTREAM, "insecure": False}, expect=(201,))
        reg = find()
    if reg["type"] != "homebrew" or reg["url"].rstrip("/") != UPSTREAM:
        die(f"endpoint {ENDPOINT} is {reg['type']} -> {reg['url']}, "
            f"expected homebrew -> {UPSTREAM}. Delete it and re-run.")
    ok(f"endpoint {ENDPOINT} id={reg['id']} -> {UPSTREAM}")
    return reg["id"]


def ensure_project(h, registry_id):
    code, _ = h.call("GET", f"/projects/{PROJECT}", expect=(200, 404))
    if code == 404:
        h.call("POST", "/projects", {"project_name": PROJECT, "registry_id": registry_id,
                                     "metadata": {"public": "false"}}, expect=(201,))
    _, p = h.call("GET", f"/projects/{PROJECT}")
    # The upstream binding is fixed at creation, so a mismatch cannot be patched.
    if p.get("registry_id") != registry_id:
        die(f"project {PROJECT} proxies registry {p.get('registry_id')}, expected "
            f"{registry_id}. Delete the project and re-run.")
    # Not made private here: anonymous consumers of a public project would break silently.
    if (p.get("metadata") or {}).get("public") != "false":
        die(f"project {PROJECT} is public, so anyone can pull without the robot. "
            "Make it private or delete it, then re-run.")
    ok(f"project {PROJECT} id={p['project_id']} (private, proxy cache)")
    return p["project_id"]


def ensure_robot(h, project_id):
    q = urllib.parse.quote(f"Level=project,ProjectID={project_id}")
    _, robots = h.call("GET", f"/robots?q={q}&page_size=100")
    robot = next((r for r in robots or [] if r["name"].endswith(f"{PROJECT}+{ROBOT}")), None)
    if robot is None:
        _, created = h.call("POST", "/robots", {
            "name": ROBOT, "description": "intranet brew clients (pull only)",
            "duration": -1, "level": "project", "permissions": PULL_ONLY}, expect=(201,))
        ok(f"robot {created['name']} created")
        return created["name"], created["secret"]
    if robot["permissions"] != PULL_ONLY:
        die(f"robot {robot['name']} has permissions {robot['permissions']}, expected "
            "repository pull on this project only. Delete it and re-run.")
    _, sec = h.call("PATCH", f"/robots/{robot['id']}", {})
    ok(f"robot {robot['name']} exists, secret rotated")
    return robot["name"], sec["secret"]


def client_env(url, name, secret):
    parts = urllib.parse.urlsplit(url)
    enc = lambda s: urllib.parse.quote(s, safe="")
    base = f"{parts.scheme}://{parts.netloc}/homebrew/{PROJECT}"
    # brew sends no credentials to HOMEBREW_API_DOMAIN, so they ride in the URL.
    api = f"{parts.scheme}://{enc(name)}:{enc(secret)}@{parts.netloc}/homebrew/{PROJECT}/api"
    token = base64.b64encode(f"{name}:{secret}".encode()).decode()
    return (f"HOMEBREW_API_DOMAIN={api}\n"
            f"HOMEBREW_ARTIFACT_DOMAIN={base}\n"
            "HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1\n"
            f"HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN={token}\n"
            # brew update git-fetches brew itself from github.com, which the proxy does not serve.
            "HOMEBREW_NO_AUTO_UPDATE=1\n")


def check_metadata(url, name, secret):
    req = urllib.request.Request(f"{url}/homebrew/{PROJECT}/api/formula/jq.json",
                                 headers={"Authorization": basic(name, secret)})
    try:
        with urllib.request.urlopen(req) as resp:
            version = json.load(resp)["versions"]["stable"]
    except urllib.error.HTTPError as e:
        die(f"robot cannot read formula metadata: HTTP {e.code} {e.read().decode(errors='replace')}")
    ok(f"robot reads formula metadata through the proxy (jq {version})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="brew.env", help="client env file to write")
    args = ap.parse_args()
    url = os.environ.get("HARBOR_URL", "https://8gcr.container-registry.dev").rstrip("/")
    password = os.environ.get("HARBOR_PASS") or die("set HARBOR_PASS")
    h = Harbor(url, os.environ.get("HARBOR_USER", "admin"), password)
    print(f"==> {url}")
    h.call("GET", "/users/current")
    project_id = ensure_project(h, ensure_endpoint(h))
    name, secret = ensure_robot(h, project_id)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # The mode above applies only to a new file; an existing one keeps its own.
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(client_env(url, name, secret))
    ok(f"client settings written to {args.out} (contains the robot secret)")
    check_metadata(url, name, secret)


if __name__ == "__main__":
    main()
