#!/usr/bin/env python3
"""Provision everything the TodoMVC example needs on an 8gcr / Harbor Next 2.16 instance.

  setup-8gcr.py        registry side and keyless CI (run once, and after every demo reset)
  setup-8gcr.py kind   trust the current kind cluster (run after every `kind create cluster`)

The default run creates, idempotently:
  1. proxy-cache endpoints for npmjs.org, Maven Central and Docker Hub
  2. read-only proxy-cache projects npmjs, maven-central and dockerhub
  3. hosted projects todomvc-npm and todomvc-maven for what CI publishes
  4. multi-project todomvc: holds the app images and the Helm chart, and resolves
     anything it does not hold through its sub-project dockerhub (OCI only)
  5. trusted issuer for GitHub Actions OIDC, audience = registry host
  6. two secretless robots: todomvc-ci (push) for this repository's main branch,
     and todomvc-ci-pr (pull only) for its pull_request runs
The kind run reads the cluster's issuer and signing keys with kubectl and creates
an offline trusted issuer plus the pull-only robot todomvc-k8s for the service
account todomvc/todomvc.

Existing objects are checked against what this script would create; a mismatch
stops with instructions instead of reporting success.

Usage:
  HARBOR_URL=https://demo.container-registry.com HARBOR_PASS=... ./scripts/setup-8gcr.py
  HARBOR_URL=https://demo.container-registry.com HARBOR_PASS=... ./scripts/setup-8gcr.py kind
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GITHUB_OIDC = "https://token.actions.githubusercontent.com"
ENDPOINTS = [("npmjs", "npm", "https://registry.npmjs.org"),
             ("maven-central", "maven", "https://repo1.maven.org/maven2"),
             ("dockerhub", "docker-hub", "https://hub.docker.com")]
# (project, endpoint, public). Read-only: publishing into a proxy cache is going
# away (8gcr #658), so what CI publishes goes into HOSTED_PROJECTS instead.
PROXY_PROJECTS = [("npmjs", "npmjs", True), ("maven-central", "maven-central", True),
                  ("dockerhub", "dockerhub", False)]
# Public so `docker build`, which gets no credential, can resolve from them too.
HOSTED_PROJECTS = ["todomvc-npm", "todomvc-maven"]
MULTI_PROJECT = "todomvc"
SUB_PROJECTS = [("dockerhub", 1)]
CI_ISSUER = "github-actions"
KIND_ISSUER = "kind-todomvc"
K8S_SUBJECT = "system:serviceaccount:todomvc:todomvc"
PUSH = [{"resource": "repository", "action": a} for a in ("push", "pull")] + [
    {"resource": "artifact", "action": "read"}, {"resource": "tag", "action": "create"}]
PULL = [{"resource": "repository", "action": "pull"}, {"resource": "artifact", "action": "read"}]


def say(msg):
    print(f"\n==> {msg}")


def ok(msg):
    print(f"  ok {msg}")


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

    def project(self, name, body):
        code, _ = self.call("GET", f"/projects/{name}", expect=(200, 404))
        if code == 404:
            self.call("POST", "/projects", {"project_name": name, **body}, expect=(201,))
        return self.call("GET", f"/projects/{name}")[1]


def ensure_endpoints(h):
    say("Registry endpoints (upstreams to cache from)")
    ids = {}
    for name, typ, url in ENDPOINTS:
        reg = h.find("/registries", name)
        if reg is None:
            h.call("POST", "/registries", {"name": name, "type": typ, "url": url, "insecure": False},
                   expect=(201,))
            reg = h.find("/registries", name)
        if reg["type"] != typ or reg["url"].rstrip("/") != url or reg.get("insecure"):
            die(f"endpoint {name} is {reg['type']} -> {reg['url']} (insecure={reg.get('insecure')}), "
                f"expected {typ} -> {url} with TLS verification. Delete it and re-run.")
        ids[name] = reg["id"]
        ok(f"endpoint {name} id={reg['id']} {typ} -> {url}")
    return ids


def ensure_projects(h, endpoint_ids):
    say("Proxy-cache projects (read-only)")
    for name, endpoint, public in PROXY_PROJECTS:
        rid = endpoint_ids[endpoint]
        want = str(public).lower()
        p = h.project(name, {"registry_id": rid, "metadata": {"public": want}})
        got = p.get("metadata") or {}
        # registry_id is fixed at creation, so a mismatch cannot be patched.
        if p.get("registry_id") != rid or got.get("proxy_cache_allow_push") == "true":
            die(f"project {name} must be a read-only proxy cache of registry {rid}. Delete it and re-run.")
        if got.get("public") != want:
            die(f"project {name} has public={got.get('public')}, expected {want}. "
                "Change it under Project -> Configuration and re-run.")
        ok(f"project {name} (proxy cache of {endpoint}, public={want})")

    say("Hosted projects")
    for name in HOSTED_PROJECTS:
        p = h.project(name, {"metadata": {"public": "true"}})
        meta = p.get("metadata") or {}
        if p.get("registry_id") or meta.get("multi_project") == "true" or meta.get("public") != "true":
            die(f"project {name} must be a plain public project. Delete or fix it and re-run.")
        ok(f"project {name} (hosted, public)")

    say("Multi-project")
    p = h.project(MULTI_PROJECT, {"metadata": {"public": "false", "multi_project": "true"}})
    if (p.get("metadata") or {}).get("multi_project") != "true" or p.get("registry_id"):
        die(f"project {MULTI_PROJECT} exists but is not a multi-project; the flag is create-only. "
            "Delete it and re-run.")
    # Private on purpose: the Kubernetes side has to prove it can authenticate.
    if (p.get("metadata") or {}).get("public") != "false":
        die(f"project {MULTI_PROJECT} is public. Make it private (Project -> Configuration) and re-run.")
    _, refs = h.call("GET", f"/projects/{MULTI_PROJECT}/subprojects")
    have = {r["sub_project_name"]: r for r in refs or []}
    for sub, rank in SUB_PROJECTS:
        if sub not in have:
            h.call("POST", f"/projects/{MULTI_PROJECT}/subprojects",
                   {"sub_project_name": sub, "rank": rank}, expect=(201,))
        elif have[sub]["rank"] != rank:
            h.call("PUT", f"/projects/{MULTI_PROJECT}/subprojects/{have[sub]['sub_project_id']}",
                   {"rank": rank})
        ok(f"{MULTI_PROJECT} -> sub-project {sub} rank {rank}")
    extra = set(have) - {s for s, _ in SUB_PROJECTS}
    if extra:
        die(f"{MULTI_PROJECT} also resolves through {sorted(extra)}; remove them so pulls stay predictable.")
    ok(f"multi-project {MULTI_PROJECT} (private; own pushes first, then sub-projects by rank)")


def ensure_issuer(h, name, body, audience):
    issuer = h.find("/trusted-issuers", name)
    if issuer is None:
        h.call("POST", "/trusted-issuers", {"name": name, "audience": audience, **body}, expect=(201,))
        issuer = h.find("/trusted-issuers", name)
    want_iss = body.get("issuer", GITHUB_OIDC)
    if issuer.get("issuer") != want_iss or issuer.get("audience") != audience or \
            bool(issuer.get("offline_validation")) != bool(body.get("offline_validation")):
        die(f"trusted issuer {name} is {issuer.get('issuer')} / aud {issuer.get('audience')} / "
            f"offline={issuer.get('offline_validation')}, expected {want_iss} / aud {audience}. "
            "The audience is immutable; delete it and re-run.")
    if body.get("offline_validation"):
        # A recreated cluster signs with new keys; replace the pinned set.
        h.call("PUT", f"/trusted-issuers/{issuer['id']}", {"jwks_keys": body["jwks_keys"]})
    ok(f"trusted issuer {name} id={issuer['id']} {want_iss}, audience {audience}, "
       f"{'offline (pinned keys)' if body.get('offline_validation') else 'online (follows key rotation)'}")
    return issuer["id"]


def ensure_robot(h, name, desc, issuer_id, perms):
    _, conf = h.call("GET", "/configurations")
    full_name = (conf.get("robot_name_prefix") or {}).get("value", "robot$") + name
    # Harbor stores and queries robots by the unprefixed name but returns the prefixed one.
    q = urllib.parse.quote(f"name={name}")
    _, robots = h.call("GET", f"/robots?q={q}&page_size=100")
    robot = next((r for r in robots or [] if r.get("name") == full_name and r.get("level") == "system"), None)
    if robot is None:
        _, created = h.call("POST", "/robots", {
            "name": name, "description": desc, "level": "system", "duration": -1,
            "trusted_issuer_id": issuer_id, "permissions": perms}, expect=(201,))
        _, robot = h.call("GET", f"/robots/{created['id']}")
    if robot.get("trusted_issuer_id") != issuer_id:
        die(f"robot {full_name} is linked to trusted issuer {robot.get('trusted_issuer_id')}, "
            f"expected {issuer_id}. Delete it and re-run.")
    # Reconcile permissions; the update must echo the stored, prefixed name and level.
    h.call("PUT", f"/robots/{robot['id']}", {
        "name": robot["name"], "level": robot["level"], "description": desc,
        "duration": -1, "disable": False, "permissions": perms})
    _, robot = h.call("GET", f"/robots/{robot['id']}")
    if robot.get("disable") or robot.get("expires_at", -1) not in (-1, 0, None):
        die(f"robot {robot['name']} is still disabled or expiring after reconcile. Delete it and re-run.")
    return robot


def ensure_claims(h, issuer_id, robot, want):
    _, rules = h.call("GET", f"/trusted-issuers/{issuer_id}/claims?robot_id={robot['id']}")
    stale = [r for r in rules or [] if want.get(r["claim_path"]) != r["value"]]
    if stale:
        h.call("DELETE", f"/trusted-issuers/{issuer_id}/claims", {"rules": stale})
    have = {r["claim_path"] for r in rules or [] if r not in stale}
    missing = [{"robot_id": robot["id"], "claim_path": k, "value": v}
               for k, v in want.items() if k not in have]
    if missing:
        h.call("POST", f"/trusted-issuers/{issuer_id}/claims", {"rules": missing}, expect=(201,))
    _, rules = h.call("GET", f"/trusted-issuers/{issuer_id}/claims?robot_id={robot['id']}")
    if {r["claim_path"]: r["value"] for r in rules or []} != want:
        die(f"robot {robot['name']} claim rules are {rules}, expected {want}.")
    ok(f"robot {robot['name']} id={robot['id']} <- " + ", ".join(f"{k} = {v}" for k, v in want.items()))


def grant(access, *projects):
    return [{"kind": "project", "namespace": p, "access": access} for p in projects]


def setup_ci(h, url, audience, repo):
    ensure_projects(h, ensure_endpoints(h))
    say("Trusted issuer: GitHub Actions OIDC")
    # Online: Harbor reads the discovery document and follows GitHub's key rotation.
    issuer_id = ensure_issuer(h, CI_ISSUER, {
        "description": "GitHub Actions OIDC, keyless CI",
        "openid_config_url": f"{GITHUB_OIDC}/.well-known/openid-configuration",
        "offline_validation": False}, audience)
    say("Secretless robots for CI")
    push = ensure_robot(h, "todomvc-ci", "Keyless CI publishing (GitHub Actions)", issuer_id,
                        grant(PUSH, MULTI_PROJECT, *HOSTED_PROJECTS))
    # Only main may push. A pull_request token carries refs/pull/<n>/merge and never matches.
    ensure_claims(h, issuer_id, push, {"repository": repo, "ref": "refs/heads/main"})
    pr = ensure_robot(h, "todomvc-ci-pr", "Keyless CI pull requests, read only (GitHub Actions)",
                      issuer_id, grant(PULL, MULTI_PROJECT, *HOSTED_PROJECTS))
    ensure_claims(h, issuer_id, pr, {"repository": repo, "event_name": "pull_request"})
    say("Done")
    host = urllib.parse.urlsplit(url).netloc
    # v2.16.0 serves packages under /npm/ and /maven/; later builds move them to /pkg/<format>/.
    pkg = url + os.environ.get("PKG_ROOT", "")
    print(f"    images, chart -> {host}/{MULTI_PROJECT}/{{todo-api,todo-ui,charts/todomvc}}\n"
          f"    base images   -> {host}/{MULTI_PROJECT}/library/<image> (via dockerhub)\n"
          f"    npm           -> resolve {pkg}/npm/npmjs/, publish @todomvc/* to {pkg}/npm/todomvc-npm/\n"
          f"    Maven         -> mirror {pkg}/maven/maven-central, deploy to {pkg}/maven/todomvc-maven\n"
          f"    CI auth       -> GitHub OIDC token, audience {audience}, repository {repo}")


def kubectl_json(context, path):
    cmd = ["kubectl", "get", "--raw", path] + (["--context", context] if context else [])
    try:
        return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        die(f"{' '.join(cmd)}: {getattr(e, 'stderr', '') or e}")


def setup_kind(h, audience, context):
    say(f"Trusted issuer: kind cluster ({context or 'current kubectl context'})")
    discovery = kubectl_json(context, "/.well-known/openid-configuration")
    jwks = kubectl_json(context, "/openid/v1/jwks")
    # Offline: Harbor cannot reach a kind API server, and every kind cluster shares
    # the same issuer URL, so the pinned keys are what identify this cluster.
    issuer_id = ensure_issuer(h, KIND_ISSUER, {
        "description": "kind cluster service accounts (offline JWKS)",
        "issuer": discovery["issuer"], "offline_validation": True, "jwks_keys": jwks}, audience)
    say("Secretless robot for the cluster")
    robot = ensure_robot(h, "todomvc-k8s", "Keyless pulls from Kubernetes (Flux and kubelet)",
                         issuer_id, grant(PULL, MULTI_PROJECT))
    ensure_claims(h, issuer_id, robot, {"sub": K8S_SUBJECT})
    say("Done")
    print(f"    kid(s) pinned: {', '.join(k['kid'] for k in jwks['keys'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", nargs="?", choices=["ci", "kind"], default="ci")
    ap.add_argument("--context", default=os.environ.get("KUBE_CONTEXT", "kind-todomvc"),
                    help="kubectl context of the kind cluster (kind target only)")
    args = ap.parse_args()
    url = os.environ.get("HARBOR_URL", "https://demo.container-registry.com").rstrip("/")
    password = os.environ.get("HARBOR_PASS") or die("set HARBOR_PASS")
    repo = os.environ.get("GITHUB_REPO", "container-registry/harbor-multi-artifact-support-examples")
    # The registry host as audience scopes every token to this registry.
    audience = os.environ.get("AUDIENCE") or urllib.parse.urlsplit(url).netloc
    h = Harbor(url, os.environ.get("HARBOR_USER", "admin"), password)
    say(f"Target: {url} (audience: {audience})")
    h.call("GET", "/users/current")
    ok("authenticated")
    if args.target == "kind":
        setup_kind(h, audience, args.context)
    else:
        setup_ci(h, url, audience, repo)


if __name__ == "__main__":
    main()
