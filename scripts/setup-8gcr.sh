#!/usr/bin/env bash
#
# Provisions everything this demo needs on an 8gcr/Harbor instance:
#
#   1. npm + Maven proxy-cache registry endpoints (upstream: npmjs.org, Maven Central)
#   2. three projects  - todomvc-npm   (npm proxy cache, publishing allowed)
#                      - todomvc-maven (Maven proxy cache, publishing allowed)
#                      - todomvc       (plain OCI project for the container images)
#   3. a federated identity provider trusting GitHub Actions OIDC
#   4. a robot account with NO static secret, authorised purely by JWT claims
#
# Idempotent: safe to re-run. Existing objects are reported and reused.
#
# Usage:
#   HARBOR_URL=https://8gcr.container-registry.dev \
#   HARBOR_USER=admin HARBOR_PASS=... \
#   GITHUB_REPO=owner/repo \
#   ./scripts/setup-8gcr.sh

set -euo pipefail

HARBOR_URL="${HARBOR_URL:-https://8gcr.container-registry.dev}"
HARBOR_USER="${HARBOR_USER:-admin}"
HARBOR_PASS="${HARBOR_PASS:?set HARBOR_PASS}"
GITHUB_REPO="${GITHUB_REPO:-container-registry/harbor-multi-artifact-support-examples}"

# The OIDC "audience" the pipeline asks GitHub for. Using the registry hostname
# scopes the token to this registry, so a token minted for some other service
# cannot be replayed here.
_host="${HARBOR_URL#*://}"          # strip scheme
AUDIENCE="${AUDIENCE:-${_host%%/*}}"  # strip any path -> bare hostname

API="$HARBOR_URL/api/v2.0"
AUTH=(-u "$HARBOR_USER:$HARBOR_PASS")
JSON=(-H 'Content-Type: application/json')

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '    \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# POST that tolerates "already exists" (409) so the script can be re-run.
post() { # post <path> <json> <what>
  local code body
  body="$(mktemp)"
  code="$(curl -sS "${AUTH[@]}" "${JSON[@]}" -X POST "$API$1" -d "$2" -o "$body" -w '%{http_code}')"
  case "$code" in
    201) ok "$3 created" ;;
    409) ok "$3 already exists" ;;
    *)   warn "$3 -> HTTP $code: $(cat "$body")"; rm -f "$body"; return 1 ;;
  esac
  rm -f "$body"
}

id_of() { # id_of <path> <jq-ish name filter>
  curl -sS "${AUTH[@]}" "$API$1" |
    python3 -c "import sys,json;print(next((str(o['id']) for o in json.load(sys.stdin) if o.get('name')=='$2'),''))"
}

say "Target: $HARBOR_URL (audience: $AUDIENCE)"
curl -fsS "${AUTH[@]}" "$API/users/current" >/dev/null || die "cannot authenticate as $HARBOR_USER"
ok "authenticated"

# ---------------------------------------------------------------------------
# 1. Proxy-cache registry endpoints
# ---------------------------------------------------------------------------
say "Registry endpoints (upstreams to cache from)"
post /registries '{"name":"npmjs","type":"npm","url":"https://registry.npmjs.org","insecure":false}' "npm -> registry.npmjs.org" || true
post /registries '{"name":"maven-central","type":"maven","url":"https://repo1.maven.org/maven2","insecure":false}' "maven -> repo1.maven.org" || true

NPM_REG_ID="$(id_of /registries npmjs)"
MVN_REG_ID="$(id_of /registries maven-central)"
[ -n "$NPM_REG_ID" ] || die "npm registry endpoint missing"
[ -n "$MVN_REG_ID" ] || die "maven registry endpoint missing"
ok "npm endpoint id=$NPM_REG_ID, maven endpoint id=$MVN_REG_ID"

# ---------------------------------------------------------------------------
# 2. Projects
# ---------------------------------------------------------------------------
# proxy_cache_allow_push lets the SAME project both cache upstream packages and
# host our own. It can only be set at creation time - a project created without
# it cannot be updated later, it has to be deleted and recreated.
say "Projects"
if ! post /projects "{\"project_name\":\"todomvc-npm\",\"registry_id\":$NPM_REG_ID,\"metadata\":{\"public\":\"true\",\"proxy_cache_allow_push\":\"true\"}}" "project todomvc-npm"; then
  warn "npm proxy-cache project could not be created."
  warn "If the error says 'unsupported registry type npm', the core container is"
  warn "missing npm/maven in PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE - see docs/00-environment.md."
fi
if ! post /projects "{\"project_name\":\"todomvc-maven\",\"registry_id\":$MVN_REG_ID,\"metadata\":{\"public\":\"true\",\"proxy_cache_allow_push\":\"true\"}}" "project todomvc-maven"; then
  warn "maven proxy-cache project could not be created - same cause as above."
fi
post /projects '{"project_name":"todomvc","metadata":{"public":"true"}}' "project todomvc (OCI images)" || true

# ---------------------------------------------------------------------------
# 3. Federated identity provider - trust GitHub's OIDC issuer
# ---------------------------------------------------------------------------
# Online mode: Harbor fetches the discovery document itself and keeps the JWKS
# fresh, so GitHub's key rotation needs no action here.
say "Federated identity provider (GitHub Actions OIDC)"
post /federated-idps '{
  "name":"github-actions",
  "description":"GitHub Actions OIDC - keyless pushes from CI",
  "openid_config_url":"https://token.actions.githubusercontent.com/.well-known/openid-configuration",
  "offline_validation":false
}' "IdP github-actions" || true

IDP_ID="$(id_of /federated-idps github-actions)"
[ -n "$IDP_ID" ] || die "federated IdP missing"
ok "IdP id=$IDP_ID"

# ---------------------------------------------------------------------------
# 4. Robot with no secret - authorised by token claims alone
# ---------------------------------------------------------------------------
say "Federated robot account"
PERMS='[]'
PERMS="$(python3 - "$HARBOR_URL" <<'PY'
import json,sys
acc=[{"resource":"repository","action":a} for a in ("push","pull")]
acc+=[{"resource":"artifact","action":"read"},{"resource":"tag","action":"create"}]
print(json.dumps([{"kind":"project","namespace":n,"access":acc}
                  for n in ("todomvc","todomvc-npm","todomvc-maven")]))
PY
)"
# Projects that do not exist yet are rejected, so fall back to whatever exists.
if ! post /robots "{\"name\":\"todomvc-ci\",\"description\":\"Keyless CI robot (GitHub Actions WIF)\",\"level\":\"system\",\"duration\":-1,\"federatedidp_id\":$IDP_ID,\"permissions\":$PERMS}" "robot todomvc-ci"; then
  warn "retrying with only the projects that exist"
  post /robots "{\"name\":\"todomvc-ci\",\"description\":\"Keyless CI robot (GitHub Actions WIF)\",\"level\":\"system\",\"duration\":-1,\"federatedidp_id\":$IDP_ID,\"permissions\":[{\"kind\":\"project\",\"namespace\":\"todomvc\",\"access\":[{\"resource\":\"repository\",\"action\":\"push\"},{\"resource\":\"repository\",\"action\":\"pull\"},{\"resource\":\"artifact\",\"action\":\"read\"},{\"resource\":\"tag\",\"action\":\"create\"}]}]}" "robot todomvc-ci (todomvc only)" || true
fi

ROBOT_ID="$(curl -sS "${AUTH[@]}" "$API/robots" |
  python3 -c "import sys,json;print(next((str(r['id']) for r in json.load(sys.stdin) if r['name'] in ('robot_todomvc-ci','todomvc-ci')),''))")"
[ -n "$ROBOT_ID" ] || die "robot missing"
ok "robot id=$ROBOT_ID (no secret - it cannot be used without a valid OIDC token)"

# ---------------------------------------------------------------------------
# 5. Claim rules - what a token must prove to become this robot
# ---------------------------------------------------------------------------
# robot_id 0 = provider-wide rule, applied to every token from this IdP.
# A rule bound to a robot id is what actually selects that robot.
say "Claim rules"
post "/federated-idps/$IDP_ID/claims" \
  "{\"rules\":[{\"identity_provider_id\":$IDP_ID,\"robot_id\":0,\"claim_path\":\"aud\",\"value\":\"$AUDIENCE\"}]}" \
  "provider rule: aud = $AUDIENCE" || true
post "/federated-idps/$IDP_ID/claims" \
  "{\"rules\":[{\"identity_provider_id\":$IDP_ID,\"robot_id\":$ROBOT_ID,\"claim_path\":\"repository\",\"value\":\"$GITHUB_REPO\"}]}" \
  "robot rule: repository = $GITHUB_REPO" || true

say "Done"
cat <<EOF
    Images   -> $HARBOR_URL/todomvc/{todo-api,todo-ui}
    npm      -> $HARBOR_URL/npm/todomvc-npm/
    Maven    -> $HARBOR_URL/maven/todomvc-maven
    CI auth  -> GitHub OIDC token, audience "$AUDIENCE", repository "$GITHUB_REPO"
               no secret is stored anywhere.
EOF
