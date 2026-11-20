"""Idempotent provisioning helpers shared by every example's setup script.

Each ensure_* function creates the object when it is missing and otherwise checks
it against what it would create; a mismatch stops with instructions instead of
reporting success. Only the Python standard library is used.

Usage from an example two levels below the repository root:

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
    import harborlib as hl
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GITHUB_OIDC = "https://token.actions.githubusercontent.com"
# Upstreams shared by every example: name -> (endpoint type, URL, project public).
# The endpoint and its read-only proxy-cache project carry the same name.
SHARED_PROXIES = {
    "npmjs": ("npm", "https://registry.npmjs.org", True),
    "maven-central": ("maven", "https://repo1.maven.org/maven2", True),
    "dockerhub": ("docker-hub", "https://hub.docker.com", False),
}
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
        self.url = url.rstrip("/")
        self.api = f"{self.url}/api/v2.0"
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


def connect():
    """Harbor client from HARBOR_URL, HARBOR_USER and HARBOR_PASS, after a login check."""
    url = os.environ.get("HARBOR_URL", "https://demo.container-registry.com").rstrip("/")
    password = os.environ.get("HARBOR_PASS") or die("set HARBOR_PASS")
    h = Harbor(url, os.environ.get("HARBOR_USER", "admin"), password)
    return h


def audience(h):
    """The registry host: the audience every keyless token here is minted for."""
    return os.environ.get("AUDIENCE") or urllib.parse.urlsplit(h.url).netloc


def check_login(h):
    h.call("GET", "/users/current")
    ok("authenticated")


def ensure_endpoint(h, name, typ, url):
    reg = h.find("/registries", name)
    if reg is None:
        h.call("POST", "/registries", {"name": name, "type": typ, "url": url, "insecure": False},
               expect=(201,))
        reg = h.find("/registries", name)
    if reg["type"] != typ or reg["url"].rstrip("/") != url or reg.get("insecure"):
        die(f"endpoint {name} is {reg['type']} -> {reg['url']} (insecure={reg.get('insecure')}), "
            f"expected {typ} -> {url} with TLS verification. Delete it and re-run.")
    ok(f"endpoint {name} id={reg['id']} {typ} -> {url}")
    return reg["id"]


def ensure_proxy_project(h, name, endpoint_name, endpoint_id, public):
    """A read-only proxy cache. Publishing into a proxy is going away (8gcr #658)."""
    want = str(public).lower()
    p = h.project(name, {"registry_id": endpoint_id, "metadata": {"public": want}})
    got = p.get("metadata") or {}
    # registry_id is fixed at creation, so a mismatch cannot be patched.
    if p.get("registry_id") != endpoint_id or got.get("proxy_cache_allow_push") == "true":
        die(f"project {name} must be a read-only proxy cache of registry {endpoint_id}. "
            "Delete it and re-run.")
    if got.get("public") != want:
        die(f"project {name} has public={got.get('public')}, expected {want}. "
            "Change it under Project -> Configuration and re-run.")
    ok(f"project {name} (proxy cache of {endpoint_name}, public={want})")


def ensure_shared_proxy(h, name):
    """Endpoint plus read-only proxy-cache project for one of SHARED_PROXIES."""
    typ, url, public = SHARED_PROXIES[name]
    ensure_proxy_project(h, name, name, ensure_endpoint(h, name, typ, url), public)


def ensure_hosted_project(h, name, public=True):
    want = str(public).lower()
    p = h.project(name, {"metadata": {"public": want}})
    meta = p.get("metadata") or {}
    if p.get("registry_id") or meta.get("multi_project") == "true" or meta.get("public") != want:
        die(f"project {name} must be a plain project with public={want}. Delete or fix it and re-run.")
    ok(f"project {name} (hosted, {'public' if public else 'private'})")


def ensure_multi_project(h, name, subs, public=False):
    """subs: [(sub-project name, rank)]. Sub-project resolution covers OCI pulls only."""
    want = str(public).lower()
    p = h.project(name, {"metadata": {"public": want, "multi_project": "true"}})
    meta = p.get("metadata") or {}
    if meta.get("multi_project") != "true" or p.get("registry_id"):
        die(f"project {name} exists but is not a multi-project; the flag is create-only. "
            "Delete it and re-run.")
    if meta.get("public") != want:
        die(f"project {name} has public={meta.get('public')}, expected {want}. "
            "Change it under Project -> Configuration and re-run.")
    _, refs = h.call("GET", f"/projects/{name}/subprojects")
    have = {r["sub_project_name"]: r for r in refs or []}
    for sub, rank in subs:
        if sub not in have:
            h.call("POST", f"/projects/{name}/subprojects",
                   {"sub_project_name": sub, "rank": rank}, expect=(201,))
        elif have[sub]["rank"] != rank:
            h.call("PUT", f"/projects/{name}/subprojects/{have[sub]['sub_project_id']}", {"rank": rank})
        ok(f"{name} -> sub-project {sub} rank {rank}")
    extra = set(have) - {s for s, _ in subs}
    if extra:
        die(f"{name} also resolves through {sorted(extra)}; remove them so pulls stay predictable.")


def ensure_issuer(h, name, body, aud):
    """body: online {"openid_config_url": ...} or offline {"issuer", "jwks_keys", "offline_validation": True}."""
    issuer = h.find("/trusted-issuers", name)
    if issuer is None:
        h.call("POST", "/trusted-issuers", {"name": name, "audience": aud, **body}, expect=(201,))
        issuer = h.find("/trusted-issuers", name)
    want_iss = body.get("issuer", GITHUB_OIDC)
    if issuer.get("issuer") != want_iss or issuer.get("audience") != aud or \
            bool(issuer.get("offline_validation")) != bool(body.get("offline_validation")):
        die(f"trusted issuer {name} is {issuer.get('issuer')} / aud {issuer.get('audience')} / "
            f"offline={issuer.get('offline_validation')}, expected {want_iss} / aud {aud}. "
            "The audience is immutable; delete it and re-run.")
    want_cfg = body.get("openid_config_url")
    if want_cfg and issuer.get("openid_config_url") != want_cfg:
        die(f"trusted issuer {name} reads {issuer.get('openid_config_url')}, expected {want_cfg}. "
            "Fix it under Administration -> Trusted Issuers, or delete it and re-run.")
    if body.get("offline_validation"):
        # A recreated cluster signs with new keys; replace the pinned set.
        h.call("PUT", f"/trusted-issuers/{issuer['id']}", {"jwks_keys": body["jwks_keys"]})
    ok(f"trusted issuer {name} id={issuer['id']} {want_iss}, audience {aud}, "
       f"{'offline (pinned keys)' if body.get('offline_validation') else 'online (follows key rotation)'}")
    return issuer["id"]


def _robot_prefix(h):
    _, conf = h.call("GET", "/configurations")
    return (conf.get("robot_name_prefix") or {}).get("value", "robot$")


def _find_system_robot(h, name):
    full_name = _robot_prefix(h) + name
    # Harbor stores and queries robots by the unprefixed name but returns the prefixed one.
    q = urllib.parse.quote(f"name={name}")
    _, robots = h.call("GET", f"/robots?q={q}&page_size=100")
    return full_name, next((r for r in robots or []
                            if r.get("name") == full_name and r.get("level") == "system"), None)


def ensure_federated_robot(h, name, desc, issuer_id, perms):
    """A system robot with no secret, usable only through a token of the trusted issuer."""
    full_name, robot = _find_system_robot(h, name)
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


def robot_with_secret(h, name, desc, perms, env_file):
    """A system robot with a secret, written to env_file (mode 600) as HARBOR_ROBOT_USER/SECRET.

    Harbor never returns an existing robot's secret, so every run rotates it.
    """
    full_name, robot = _find_system_robot(h, name)
    if robot is None:
        _, robot = h.call("POST", "/robots", {
            "name": name, "description": desc, "level": "system", "duration": -1,
            "permissions": perms}, expect=(201,))
        secret = robot["secret"]
    else:
        if robot.get("trusted_issuer_id"):
            die(f"robot {full_name} is a federated robot, not one with a secret. Delete it and re-run.")
        h.call("PUT", f"/robots/{robot['id']}", {
            "name": robot["name"], "level": robot["level"], "description": desc,
            "duration": -1, "disable": False, "permissions": perms})
        secret = h.call("PATCH", f"/robots/{robot['id']}", {})[1]["secret"]
    path = Path(env_file)
    write_secret_file(path, f"HARBOR_ROBOT_USER='{full_name}'\nHARBOR_ROBOT_SECRET='{secret}'\n")
    ok(f"robot {full_name} id={robot['id']}, secret rotated and written to {path.name} (mode 600)")
    return full_name, secret


def pkg_url(h, fmt, project):
    """Package endpoint URL. v2.16.0 serves /<fmt>/; later builds /pkg/<fmt>/ (set PKG_ROOT=/pkg)."""
    return f"{h.url}{os.environ.get('PKG_ROOT', '')}/{fmt}/{project}"


def write_secret_file(path, content):
    """Write content to path with mode 600, also when the file already exists."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def grant(access, *projects):
    return [{"kind": "project", "namespace": p, "access": access} for p in projects]


def example_main(doc, provision):
    """Shared entry point for artifact-type setup scripts: connect, check login, provision(h)."""
    import argparse
    argparse.ArgumentParser(description=doc.splitlines()[0]).parse_args()
    h = connect()
    say(f"Target: {h.url}")
    check_login(h)
    provision(h)
    say("Done")
