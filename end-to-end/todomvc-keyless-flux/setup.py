#!/usr/bin/env python3
"""Provision everything the TodoMVC example needs on an 8gcr / Harbor Next 2.16 instance.

  setup.py        registry side and keyless CI (idempotent)
  setup.py kind   trust the current kind cluster (run after every `kind create cluster`)

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
  HARBOR_URL=https://demo.container-registry.com HARBOR_PASS=... ./setup.py
  HARBOR_URL=https://demo.container-registry.com HARBOR_PASS=... ./setup.py kind
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import harborlib as hl  # noqa: E402

PROXIES = ["npmjs", "maven-central", "dockerhub"]  # from hl.SHARED_PROXIES
# Public so `docker build`, which gets no credential, can resolve from them too.
HOSTED_PROJECTS = ["todomvc-npm", "todomvc-maven"]
MULTI_PROJECT = "todomvc"
SUB_PROJECTS = [("dockerhub", 1)]
CI_ISSUER = "github-actions"
KIND_ISSUER = "kind-todomvc"
K8S_SUBJECT = "system:serviceaccount:todomvc:todomvc"


def setup_projects(h):
    hl.say("Registry endpoints (upstreams to cache from)")
    ids = {n: hl.ensure_endpoint(h, n, *hl.SHARED_PROXIES[n][:2]) for n in PROXIES}
    hl.say("Proxy-cache projects (read-only)")
    for n in PROXIES:
        hl.ensure_proxy_project(h, n, n, ids[n], hl.SHARED_PROXIES[n][2])
    hl.say("Hosted projects")
    for name in HOSTED_PROJECTS:
        hl.ensure_hosted_project(h, name)
    hl.say("Multi-project")
    # Private on purpose: the Kubernetes side has to prove it can authenticate.
    hl.ensure_multi_project(h, MULTI_PROJECT, SUB_PROJECTS, public=False)
    hl.ok(f"multi-project {MULTI_PROJECT} (private; own pushes first, then sub-projects by rank)")


def setup_ci(h, aud, repo):
    setup_projects(h)
    hl.say("Trusted issuer: GitHub Actions OIDC")
    # Online: Harbor reads the discovery document and follows GitHub's key rotation.
    issuer_id = hl.ensure_issuer(h, CI_ISSUER, {
        "description": "GitHub Actions OIDC, keyless CI",
        "openid_config_url": f"{hl.GITHUB_OIDC}/.well-known/openid-configuration",
        "offline_validation": False}, aud)
    hl.say("Secretless robots for CI")
    push = hl.ensure_federated_robot(h, "todomvc-ci", "Keyless CI publishing (GitHub Actions)", issuer_id,
                                     hl.grant(hl.PUSH, MULTI_PROJECT, *HOSTED_PROJECTS))
    # Only main may push. A pull_request token carries refs/pull/<n>/merge and never matches.
    hl.ensure_claims(h, issuer_id, push, {"repository": repo, "ref": "refs/heads/main"})
    pr = hl.ensure_federated_robot(h, "todomvc-ci-pr", "Keyless CI pull requests, read only (GitHub Actions)",
                                   issuer_id, hl.grant(hl.PULL, MULTI_PROJECT, *HOSTED_PROJECTS))
    hl.ensure_claims(h, issuer_id, pr, {"repository": repo, "event_name": "pull_request"})
    hl.say("Done")
    host = urllib.parse.urlsplit(h.url).netloc
    # v2.16.0 serves packages under /npm/ and /maven/; later builds move them to /pkg/<format>/.
    pkg = h.url + os.environ.get("PKG_ROOT", "")
    print(f"    images, chart -> {host}/{MULTI_PROJECT}/{{todo-api,todo-ui,charts/todomvc}}\n"
          f"    base images   -> {host}/{MULTI_PROJECT}/library/<image> (via dockerhub)\n"
          f"    npm           -> resolve {pkg}/npm/npmjs/, publish @todomvc/* to {pkg}/npm/todomvc-npm/\n"
          f"    Maven         -> mirror {pkg}/maven/maven-central, deploy to {pkg}/maven/todomvc-maven\n"
          f"    CI auth       -> GitHub OIDC token, audience {aud}, repository {repo}")


def kubectl_json(context, path):
    cmd = ["kubectl", "get", "--raw", path] + (["--context", context] if context else [])
    try:
        return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        hl.die(f"{' '.join(cmd)}: {getattr(e, 'stderr', '') or e}")


def setup_kind(h, aud, context):
    hl.say(f"Trusted issuer: kind cluster ({context or 'current kubectl context'})")
    discovery = kubectl_json(context, "/.well-known/openid-configuration")
    jwks = kubectl_json(context, "/openid/v1/jwks")
    # Offline: Harbor cannot reach a kind API server, and every kind cluster shares
    # the same issuer URL, so the pinned keys are what identify this cluster.
    issuer_id = hl.ensure_issuer(h, KIND_ISSUER, {
        "description": "kind cluster service accounts (offline JWKS)",
        "issuer": discovery["issuer"], "offline_validation": True, "jwks_keys": jwks}, aud)
    hl.say("Secretless robot for the cluster")
    robot = hl.ensure_federated_robot(h, "todomvc-k8s", "Keyless pulls from Kubernetes (Flux and kubelet)",
                                      issuer_id, hl.grant(hl.PULL, MULTI_PROJECT))
    hl.ensure_claims(h, issuer_id, robot, {"sub": K8S_SUBJECT})
    hl.say("Done")
    print(f"    kid(s) pinned: {', '.join(k['kid'] for k in jwks['keys'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", nargs="?", choices=["ci", "kind"], default="ci")
    ap.add_argument("--context", default=os.environ.get("KUBE_CONTEXT", "kind-todomvc"),
                    help="kubectl context of the kind cluster (kind target only)")
    args = ap.parse_args()
    repo = os.environ.get("GITHUB_REPO", "container-registry/harbor-multi-artifact-support-examples")
    h = hl.connect()
    aud = hl.audience(h)
    hl.say(f"Target: {h.url} (audience: {aud})")
    hl.check_login(h)
    if args.target == "kind":
        setup_kind(h, aud, args.context)
    else:
        setup_ci(h, aud, repo)


if __name__ == "__main__":
    main()
