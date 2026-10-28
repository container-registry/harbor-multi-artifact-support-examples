#!/usr/bin/env python3
"""Provision everything the demo pipeline needs on an 8gcr/Harbor instance.

Creates, idempotently:
  1. npm + Maven proxy-cache registry endpoints (npmjs.org, Maven Central)
  2. projects todomvc-npm, todomvc-maven (proxy cache, publishing allowed)
     and todomvc (plain OCI project for the container images)
  3. a trusted issuer for GitHub Actions OIDC, bound to the registry audience
  4. a system robot with NO static secret, linked to that trusted issuer
  5. a claim rule that lets only GITHUB_REPO's tokens become that robot

Existing objects are checked against what this script would create; a
mismatch stops with instructions instead of reporting success.

Usage:
  HARBOR_URL=https://8gcr.container-registry.dev HARBOR_PASS=... \\
  GITHUB_REPO=owner/repo ./scripts/setup-8gcr.py [--skip-wif]
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

GITHUB_OIDC = "https://token.actions.githubusercontent.com"
ENDPOINTS = [("npmjs", "npm", "https://registry.npmjs.org"),
             ("maven-central", "maven", "https://repo1.maven.org/maven2")]
PACKAGE_PROJECTS = [("todomvc-npm", "npmjs"), ("todomvc-maven", "maven-central")]
IMAGE_PROJECT = "todomvc"
ROBOT = "todomvc-ci"
ISSUER = "github-actions"
ROBOT_ACCESS = [{"resource": "repository", "action": a} for a in ("push", "pull")] + [
    {"resource": "artifact", "action": "read"}, {"resource": "tag", "action": "create"}]


def say(msg):
    print(f"\n==> {msg}")


def ok(msg):
    print(f"  ok {msg}")


def warn(msg):
    print(f"  !  {msg}")


def die(msg):
    sys.exit(f"  x  {msg}")


class Harbor:
    def __init__(self, url, user, password):
        self.api = f"{url}/api/v2.0"
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def call(self, method, path, body=None, expect=(200,)):
        req = urllib.request.Request(
            self.api + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        # Unredirected: urllib would otherwise replay admin credentials to a redirect target.
        req.add_unredirected_header("Authorization", self.auth)
        try:
            with urllib.request.urlopen(req) as resp:
                code, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        except urllib.error.URLError as e:
            die(f"{method} {path}: {e.reason}")
        if code not in expect:
            die(f"{method} {path} -> HTTP {code}: {raw.decode(errors='replace')}")
        return code, json.loads(raw) if raw.strip() else None

    def find(self, path, name):
        q = urllib.parse.quote(f"name={name}")
        _, items = self.call("GET", f"{path}?q={q}&page_size=100")
        return next((i for i in items or [] if i.get("name") == name), None)


def ensure_endpoints(h):
    say("Registry endpoints (upstreams to cache from)")
    ids = {}
    for name, typ, url in ENDPOINTS:
        reg = h.find("/registries", name)
        if reg is None:
            h.call("POST", "/registries", {"name": name, "type": typ, "url": url, "insecure": False},
                   expect=(201,))
            reg = h.find("/registries", name)
        if reg["type"] != typ or reg["url"].rstrip("/") != url:
            die(f"endpoint {name} is {reg['type']} -> {reg['url']}, expected {typ} -> {url}. "
                "Delete it and re-run.")
        if reg.get("insecure"):
            die(f"endpoint {name} skips TLS verification (insecure=true). Edit it or delete it and re-run.")
        ids[name] = reg["id"]
        ok(f"endpoint {name} id={reg['id']} -> {url}")
    return ids


def ensure_projects(h, endpoint_ids):
    say("Projects")
    for name, endpoint in PACKAGE_PROJECTS:
        rid = endpoint_ids[endpoint]
        code, _ = h.call("GET", f"/projects/{name}", expect=(200, 404))
        if code == 404:
            code, err = h.call("POST", "/projects", {
                "project_name": name, "registry_id": rid,
                "metadata": {"public": "true", "proxy_cache_allow_push": "true"}}, expect=(201, 400))
            if code == 400:
                die(f"project {name}: {err}. If it says 'unsupported registry type', add npm and "
                    "maven to PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE on the core container.")
        _, p = h.call("GET", f"/projects/{name}")
        # Both settings are fixed at creation, so a mismatch cannot be patched.
        if p.get("registry_id") != rid or (p.get("metadata") or {}).get("proxy_cache_allow_push") != "true":
            die(f"project {name} must proxy registry {rid} with publishing allowed. "
                "Delete it and re-run.")
        # The pipeline's preflight probes these anonymously; a private project skips publishing.
        if (p.get("metadata") or {}).get("public") != "true":
            die(f"project {name} is private, so the pipeline's anonymous preflight gets 401 and "
                "skips publishing. Make it public (Project -> Configuration) and re-run.")
        ok(f"project {name} (proxy cache of {endpoint}, public, publishing allowed)")
    code, _ = h.call("GET", f"/projects/{IMAGE_PROJECT}", expect=(200, 404))
    if code == 404:
        h.call("POST", "/projects", {"project_name": IMAGE_PROJECT, "metadata": {"public": "true"}},
               expect=(201,))
    _, p = h.call("GET", f"/projects/{IMAGE_PROJECT}")
    if p.get("registry_id"):
        die(f"project {IMAGE_PROJECT} is a proxy cache of registry {p['registry_id']}; pushes need a "
            "plain project. Delete it and re-run.")
    if (p.get("metadata") or {}).get("public") != "true":
        die(f"project {IMAGE_PROJECT} is private. Make it public (Project -> Configuration) and re-run.")
    ok(f"project {IMAGE_PROJECT} (OCI images, public)")


def ensure_issuer(h, audience):
    say("Trusted issuer (GitHub Actions OIDC)")
    issuer = h.find("/trusted-issuers", ISSUER)
    if issuer is None:
        # Online mode: Harbor fetches the discovery document and follows GitHub's key rotation.
        h.call("POST", "/trusted-issuers", {
            "name": ISSUER, "description": "GitHub Actions OIDC - keyless pushes from CI",
            "openid_config_url": f"{GITHUB_OIDC}/.well-known/openid-configuration",
            "offline_validation": False, "audience": audience}, expect=(201,))
        issuer = h.find("/trusted-issuers", ISSUER)
    if issuer.get("offline_validation"):
        die(f"trusted issuer {ISSUER} uses offline validation, so GitHub's key rotation would break CI. "
            "Delete it and re-run.")
    if issuer.get("issuer") != GITHUB_OIDC or issuer.get("audience") != audience:
        die(f"trusted issuer {ISSUER} is {issuer.get('issuer')} / aud {issuer.get('audience')}, "
            f"expected {GITHUB_OIDC} / aud {audience}. The audience is immutable; delete it and re-run.")
    ok(f"trusted issuer {ISSUER} id={issuer['id']}, audience {audience}")
    return issuer["id"]


def ensure_robot(h, issuer_id):
    say("Federated robot account")
    perms = [{"kind": "project", "namespace": n, "access": ROBOT_ACCESS}
             for n in [IMAGE_PROJECT] + [p for p, _ in PACKAGE_PROJECTS]]
    _, conf = h.call("GET", "/configurations")
    full_name = (conf.get("robot_name_prefix") or {}).get("value", "robot$") + ROBOT
    # Harbor stores and queries robots by the unprefixed name but returns the prefixed one.
    q = urllib.parse.quote(f"name={ROBOT}")
    _, robots = h.call("GET", f"/robots?q={q}&page_size=100")
    robot = next((r for r in robots or [] if r.get("name") == full_name and r.get("level") == "system"), None)
    if robot is None:
        _, created = h.call("POST", "/robots", {
            "name": ROBOT, "description": "Keyless CI robot (GitHub Actions)", "level": "system",
            "duration": -1, "trusted_issuer_id": issuer_id, "permissions": perms}, expect=(201,))
        _, robot = h.call("GET", f"/robots/{created['id']}")
    if robot.get("trusted_issuer_id") != issuer_id:
        die(f"robot {full_name} is linked to trusted issuer {robot.get('trusted_issuer_id')}, "
            f"expected {issuer_id}. Delete it and re-run.")
    # A robot found by name may predate a project; reconcile so CI never 401s on a missing grant.
    # The update must echo the stored name and level, prefix included.
    h.call("PUT", f"/robots/{robot['id']}", {
        "name": robot["name"], "level": robot["level"], "description": robot.get("description") or "",
        "duration": -1, "disable": False, "permissions": perms})
    _, robot = h.call("GET", f"/robots/{robot['id']}")
    if robot.get("disable") or robot.get("expires_at", -1) not in (-1, 0, None):
        die(f"robot {robot['name']} is still disabled or expiring after reconcile. Delete it and re-run.")
    ok(f"robot {robot['name']} id={robot['id']} (enabled, no expiry, no secret, push/pull on all demo projects)")
    return robot["id"]


def ensure_claim(h, issuer_id, robot_id, repo):
    say("Claim rule")
    _, rules = h.call("GET", f"/trusted-issuers/{issuer_id}/claims?robot_id={robot_id}")
    current = [r for r in rules or [] if r["claim_path"] == "repository"]
    if not current:
        h.call("POST", f"/trusted-issuers/{issuer_id}/claims", {"rules": [
            {"robot_id": robot_id, "claim_path": "repository", "value": repo}]}, expect=(201,))
    elif any(r["value"] != repo for r in current):
        die(f"robot {robot_id} already has repository = {current[0]['value']}, expected {repo}. "
            "Delete that claim rule and re-run.")
    ok(f"repository = {repo}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-wif", action="store_true", default=os.environ.get("SKIP_WIF") == "1",
                    help="only endpoints and projects (local dev has no GitHub OIDC)")
    args = ap.parse_args()
    url = os.environ.get("HARBOR_URL", "https://8gcr.container-registry.dev").rstrip("/")
    password = os.environ.get("HARBOR_PASS") or die("set HARBOR_PASS")
    repo = os.environ.get("GITHUB_REPO", "container-registry/harbor-multi-artifact-support-examples")
    # The registry hostname as audience scopes the token to this registry.
    audience = os.environ.get("AUDIENCE") or urllib.parse.urlsplit(url).netloc
    h = Harbor(url, os.environ.get("HARBOR_USER", "admin"), password)
    say(f"Target: {url} (audience: {audience})")
    h.call("GET", "/users/current")
    ok("authenticated")

    ensure_projects(h, ensure_endpoints(h))
    if args.skip_wif:
        say("--skip-wif: no trusted issuer or robot")
        return
    issuer_id = ensure_issuer(h, audience)
    ensure_claim(h, issuer_id, ensure_robot(h, issuer_id), repo)
    say("Done")
    print(f"    Images   -> {url}/{IMAGE_PROJECT}/{{todo-api,todo-ui}}\n"
          f"    npm      -> {url}/npm/todomvc-npm/\n"
          f"    Maven    -> {url}/maven/todomvc-maven\n"
          f"    CI auth  -> GitHub OIDC token, audience {audience}, repository {repo}; no stored secret")


if __name__ == "__main__":
    main()
