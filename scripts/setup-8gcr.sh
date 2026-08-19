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
JSON=(-H 'Content-Type: application/json')

# Credentials go in a mode-600 config file rather than on the curl command line.
# Anything passed as -u is visible in the process list to every other user on the
# host for the lifetime of the call, which would be an odd thing to do in a script
# whose whole subject is not storing credentials.
CURLRC="$(mktemp)"
chmod 600 "$CURLRC"
trap 'rm -f "$CURLRC"' EXIT
# curl's config parser treats \ and " inside a quoted value as escapes, so a
# password containing either would otherwise be read as something else.
_cred="$HARBOR_USER:$HARBOR_PASS"
_cred="${_cred//\\/\\\\}"
_cred="${_cred//\"/\\\"}"
printf 'user = "%s"\n' "$_cred" > "$CURLRC"
AUTH=(--config "$CURLRC")

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '    \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# POST that tolerates "already exists" (409) so the script can be re-run.
# A 409 means only that something with that name is there, not that it is
# configured the way this script wants. Where that distinction matters the caller
# reconciles afterwards rather than trusting the 409.
post() { # post <path> <json> <what>
  local code body
  body="$(mktemp)"
  code="$(curl -qsS "${AUTH[@]}" "${JSON[@]}" -X POST "$API$1" -d "$2" -o "$body" -w '%{http_code}')"
  case "$code" in
    201) ok "$3 created" ;;
    409) ok "$3 already exists" ;;
    *)   warn "$3 -> HTTP $code: $(cat "$body")"; rm -f "$body"; return 1 ;;
  esac
  rm -f "$body"
}

put() { # put <path> <json> <what>
  local code body
  body="$(mktemp)"
  code="$(curl -qsS "${AUTH[@]}" "${JSON[@]}" -X PUT "$API$1" -d "$2" -o "$body" -w '%{http_code}')"
  case "$code" in
    200) ok "$3" ;;
    *)   warn "$3 -> HTTP $code: $(cat "$body")"; rm -f "$body"; return 1 ;;
  esac
  rm -f "$body"
}

id_of() { # id_of <path> <jq-ish name filter>
  curl -qsS "${AUTH[@]}" "$API$1" |
    python3 -c "import sys,json;print(next((str(o['id']) for o in json.load(sys.stdin) if o.get('name')=='$2'),''))"
}

# A 409 from post() only means the name is taken. These check that what is there
# is what this script would have created, and stop with instructions when it is
# not, rather than reporting success over a setup that cannot work.
assert_registry() { # assert_registry <name> <expected type> <expected url>
  curl -qsS "${AUTH[@]}" "$API/registries" | NAME="$1" TYPE="$2" URL="$3" python3 -c "
import json,os,sys
name,typ,url=os.environ['NAME'],os.environ['TYPE'],os.environ['URL']
r=next((x for x in json.load(sys.stdin) if x.get('name')==name),None)
if r is None: sys.exit('registry '+name+' not found')
bad=[]
if r.get('type')!=typ: bad.append('type is '+str(r.get('type'))+', expected '+typ)
if r.get('url','').rstrip('/')!=url.rstrip('/'): bad.append('url is '+str(r.get('url'))+', expected '+url)
if bad: sys.exit('registry '+name+': '+'; '.join(bad)+'. Delete it and re-run.')
" || { die "$1 does not match the expected configuration"; return 1; }
  ok "$1 verified (type=$2)"
}

assert_idp() { # assert_idp <name> <expected issuer>
  curl -qsS "${AUTH[@]}" "$API/federated-idps" | NAME="$1" ISS="$2" python3 -c "
import json,os,sys
name,iss=os.environ['NAME'],os.environ['ISS']
d=next((x for x in json.load(sys.stdin) if x.get('name')==name),None)
if d is None: sys.exit('identity provider '+name+' not found')
if d.get('issuer')!=iss:
    sys.exit('identity provider '+name+': issuer is '+str(d.get('issuer'))+
             ', expected '+iss+'. Delete it and re-run.')
" || { die "$1 does not match the expected configuration"; return 1; }
  ok "$1 verified (issuer=$2)"
}

assert_project() { # assert_project <name> <expected registry id>
  curl -qsS "${AUTH[@]}" "$API/projects/$1" | NAME="$1" RID="$2" python3 -c "
import json,os,sys
name,rid=os.environ['NAME'],os.environ['RID']
p=json.load(sys.stdin)
bad=[]
if str(p.get('registry_id')) != rid:
    bad.append('bound to registry '+str(p.get('registry_id'))+', expected '+rid)
if (p.get('metadata') or {}).get('proxy_cache_allow_push') != 'true':
    bad.append('proxy_cache_allow_push is not true')
if bad:
    sys.exit('project '+name+': '+'; '.join(bad)+
             '. Both are fixed only at creation time, so delete the project and re-run.')
" || { die "$1 does not match the expected configuration"; return 1; }
  ok "$1 verified (proxy cache -> registry $2, publishing allowed)"
}

say "Target: $HARBOR_URL (audience: $AUDIENCE)"
curl -qfsS "${AUTH[@]}" "$API/users/current" >/dev/null || die "cannot authenticate as $HARBOR_USER"
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
assert_registry npmjs npm https://registry.npmjs.org
assert_registry maven-central maven https://repo1.maven.org/maven2
ok "npm endpoint id=$NPM_REG_ID, maven endpoint id=$MVN_REG_ID"

# ---------------------------------------------------------------------------
# 2. Projects
# ---------------------------------------------------------------------------
# proxy_cache_allow_push lets the SAME project both cache upstream packages and
# host our own. It can only be set at creation time - a project created without
# it cannot be updated later, it has to be deleted and recreated.
say "Projects"
if post /projects "{\"project_name\":\"todomvc-npm\",\"registry_id\":$NPM_REG_ID,\"metadata\":{\"public\":\"true\",\"proxy_cache_allow_push\":\"true\"}}" "project todomvc-npm"; then
  assert_project todomvc-npm "$NPM_REG_ID"
else
  warn "npm proxy-cache project could not be created."
  warn "If the error says 'unsupported registry type npm', the core container is"
  warn "missing npm/maven in PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE on the core container."
fi
if post /projects "{\"project_name\":\"todomvc-maven\",\"registry_id\":$MVN_REG_ID,\"metadata\":{\"public\":\"true\",\"proxy_cache_allow_push\":\"true\"}}" "project todomvc-maven"; then
  assert_project todomvc-maven "$MVN_REG_ID"
else
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
assert_idp github-actions https://token.actions.githubusercontent.com
ok "IdP id=$IDP_ID"

# ---------------------------------------------------------------------------
# 4. Robot with no secret - authorised by token claims alone
# ---------------------------------------------------------------------------
say "Federated robot account"

# Permissions are built from the projects that actually exist. On a registry
# where the npm/Maven projects could not be created yet, the robot is created
# with whatever is there and WIDENED on a later run once they appear. Creating it
# once and trusting the 409 on re-runs would leave it permanently short of
# push/pull on the package projects, and the CI publishes would then 401.
existing_projects() {
  local names=() n code
  for n in todomvc todomvc-npm todomvc-maven; do
    # A transport error or a 5xx is not the same as "absent". Treating it as
    # absent would silently provision a robot with too few grants.
    code="$(curl -qsS -o /dev/null -w '%{http_code}' "${AUTH[@]}" "$API/projects/$n")" ||
      die "cannot reach $API/projects/$n"
    case "$code" in
      200) names+=("$n") ;;
      404) ;;
      *)   die "cannot inspect project $n (HTTP $code)" ;;
    esac
  done
  printf '%s\n' "${names[@]}"
}

PROJECTS="$(existing_projects)"
[ -n "$PROJECTS" ] || die "none of the demo projects exist"
PERMS="$(printf '%s\n' "$PROJECTS" | python3 -c "
import json,sys
acc=[{'resource':'repository','action':a} for a in ('push','pull')]
acc+=[{'resource':'artifact','action':'read'},{'resource':'tag','action':'create'}]
names=[l.strip() for l in sys.stdin if l.strip()]
print(json.dumps([{'kind':'project','namespace':n,'access':acc} for n in names]))
")"
ok "granting on: $(echo "$PROJECTS" | tr '\n' ' ')"

ROBOT_BODY="{\"name\":\"todomvc-ci\",\"description\":\"Keyless CI robot (GitHub Actions WIF)\",\"level\":\"system\",\"duration\":-1,\"federatedidp_id\":$IDP_ID,\"permissions\":$PERMS}"
post /robots "$ROBOT_BODY" "robot todomvc-ci" || true

# Harbor stores a system robot under a configurable prefix, "robot$" by default,
# so the name to look up is not the name that was requested. Ask for the prefix
# rather than assuming one; guessing wrong finds nothing and aborts the script
# one step before the claim rules, leaving a robot no token can assume.
ROBOT_PREFIX="$(curl -qsS "${AUTH[@]}" "$API/configurations" |
  python3 -c "import sys,json;print(json.load(sys.stdin).get('robot_name_prefix',{}).get('value',''))")"
ROBOT_ID="$(curl -qsS "${AUTH[@]}" "$API/robots" |
  PREFIX="$ROBOT_PREFIX" python3 -c "
import sys,json,os
want={os.environ['PREFIX']+'todomvc-ci','todomvc-ci'}
print(next((str(r['id']) for r in json.load(sys.stdin) if r['name'] in want),''))")"
[ -n "$ROBOT_ID" ] || die "robot ${ROBOT_PREFIX}todomvc-ci not found in GET /robots"

# Reconcile rather than assume. A 409 above only says the name is taken, not that
# the robot grants what this script wants.
#
# The update must carry the robot's STORED name and level, prefix included, so
# echoing back the name that was requested at creation time is rejected with
# "cannot update the level or name of robot".
RECONCILE_BODY="$(curl -qsS "${AUTH[@]}" "$API/robots/$ROBOT_ID" |
  PERMS="$PERMS" python3 -c "
import json,os,sys
r=json.load(sys.stdin)
print(json.dumps({
    'name': r['name'],
    'level': r['level'],
    'description': r.get('description') or '',
    'duration': r.get('duration', -1),
    'disable': r.get('disable', False),
    'permissions': json.loads(os.environ['PERMS']),
}))")"
put "/robots/$ROBOT_ID" "$RECONCILE_BODY" "robot permissions reconciled" ||
  die "could not reconcile robot permissions; publishing would fail with a 401 later"

ok "robot id=$ROBOT_ID (no secret - it cannot be used without a valid OIDC token)"

# ---------------------------------------------------------------------------
# 5. Claim rules - what a token must prove to become this robot
# ---------------------------------------------------------------------------
# robot_id 0 = provider-wide rule, applied to every token from this IdP.
# A rule bound to a robot id is what actually selects that robot.
#
# These are NOT tolerated failures. Without them the robot cannot be assumed by
# any token, so a script that reported success while a rule was missing would
# hand you a setup that fails only later, in CI, as an opaque 401.
say "Claim rules"
post "/federated-idps/$IDP_ID/claims" \
  "{\"rules\":[{\"identity_provider_id\":$IDP_ID,\"robot_id\":0,\"claim_path\":\"aud\",\"value\":\"$AUDIENCE\"}]}" \
  "provider rule: aud = $AUDIENCE" || die "could not install the aud claim rule"
post "/federated-idps/$IDP_ID/claims" \
  "{\"rules\":[{\"identity_provider_id\":$IDP_ID,\"robot_id\":$ROBOT_ID,\"claim_path\":\"repository\",\"value\":\"$GITHUB_REPO\"}]}" \
  "robot rule: repository = $GITHUB_REPO" || die "could not install the repository claim rule"

# Consider narrowing further for a production setup, for example a rule on
# `ref` (refs/heads/main) or `workflow_ref`, so that only the publishing workflow
# on the expected branch can assume this robot. Harbor requires every rule bound
# to the robot to match, so added rules narrow rather than widen.

say "Done"
cat <<EOF
    Images   -> $HARBOR_URL/todomvc/{todo-api,todo-ui}
    npm      -> $HARBOR_URL/npm/todomvc-npm/
    Maven    -> $HARBOR_URL/maven/todomvc-maven
    CI auth  -> GitHub OIDC token, audience "$AUDIENCE", repository "$GITHUB_REPO"
               no secret is stored anywhere.
EOF
