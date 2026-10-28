# Harbor setup

[← Concepts](01-concepts.md) · [npm →](../npm/README.md)

Everything in this page is done through the Harbor API with `curl`. All of it is
also scripted, idempotently, in [`scripts/setup-8gcr.py`](../scripts/setup-8gcr.py):

```bash
HARBOR_URL=https://8gcr.container-registry.dev \
HARBOR_USER=admin HARBOR_PASS=... \
GITHUB_REPO=container-registry/harbor-multi-artifact-support-examples \
./scripts/setup-8gcr.py
```

Read the script rather than trusting this page if the two ever disagree; the
script is what was run against the live instance.

Shared setup for the commands below:

```bash
export HARBOR_URL=https://8gcr.container-registry.dev
export API="$HARBOR_URL/api/v2.0"
export PASS=...                       # admin password
```

## 1. Registry endpoints

A registry endpoint is a named upstream. It is not itself reachable by clients;
it exists to be bound to a project.

```bash
curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/registries" \
  -d '{"name":"npmjs","type":"npm","url":"https://registry.npmjs.org","insecure":false}'

curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/registries" \
  -d '{"name":"maven-central","type":"maven","url":"https://repo1.maven.org/maven2","insecure":false}'
```

Both return `201`. Harbor health-checks them, and both report `healthy`.

![Registry endpoints in the portal](images/portal-registries.png)

The provider dropdown in **Administration → Registries → New Endpoint** may not
offer npm or Maven. That list comes from `GET /api/v2.0/replication/adapters`,
which is filtered by the `REPLICATION_ADAPTER_WHITELIST` environment variable on
core rather than by what the build supports, so on a deployment that has not been
given the package formats the same list also omits `quay`, `gitlab` and `dtr`.
`POST /registries` accepts the types either way, which is why this page uses the
API throughout.

Note the endpoint ids for the next step:

```bash
curl -su "admin:$PASS" "$API/registries" | python3 -c \
  'import sys,json;[print(r["id"], r["name"], r["type"]) for r in json.load(sys.stdin)]'
```

## 2. Projects

Three projects, two of them proxy caches bound to the endpoints above.

```bash
# npm proxy cache that also accepts pushes. Substitute the real registry id.
curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/projects" \
  -d '{"project_name":"todomvc-npm","registry_id":1,
       "metadata":{"public":"true","proxy_cache_allow_push":"true"}}'

# Maven, same shape.
curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/projects" \
  -d '{"project_name":"todomvc-maven","registry_id":2,
       "metadata":{"public":"true","proxy_cache_allow_push":"true"}}'

# Plain project for container images. No registry_id: this one is native only.
curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/projects" \
  -d '{"project_name":"todomvc","metadata":{"public":"true"}}'
```

![Projects list](images/portal-projects.png)

The **Type** column distinguishes the two kinds. `todomvc-npm` and `todomvc-maven`
show as `Proxy Cache`; a project created without `registry_id`, like `todomvc` or
the built-in `library`, shows as `Project`.

### `proxy_cache_allow_push` is create-only

This flag can only be set in the `POST` that creates the project. Harbor will not
apply it through `PUT /api/v2.0/projects/<name>`. A project created without it
stays read-through forever, and the only remedy is to delete it and create it
again, which discards whatever is cached in it. Set it when you create the project
or accept that you will start over.

Why it is needed at all, and what the precedence between your packages and
upstream packages is, is explained in [01-concepts.md](01-concepts.md).

### What a populated proxy cache looks like

After a build has resolved dependencies through the project, its **Repositories**
tab lists everything that was pulled from upstream and everything that was
published locally, side by side.

![npm repositories in todomvc-npm](images/portal-npm-repositories.png)

![Maven repositories in todomvc-maven](images/portal-maven-repositories.png)

Repository names carry the format as a path segment:
`todomvc-npm/npm/left-pad`, `todomvc-maven/maven/org/apache/commons/commons-lang3`.
That is how one project holds several package formats without their names
colliding.

## 3. Trusted issuer

This is what makes the pipeline secretless. Harbor is told to trust GitHub's OIDC
issuer for tokens minted for one audience: the registry hostname.

```bash
curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/trusted-issuers" \
  -d '{"name":"github-actions",
       "description":"GitHub Actions OIDC - keyless pushes from CI",
       "openid_config_url":"https://token.actions.githubusercontent.com/.well-known/openid-configuration",
       "offline_validation":false,
       "audience":"8gcr.container-registry.dev"}'
```

`offline_validation:false` means Harbor fetches the discovery document itself and
keeps the JWKS current. GitHub rotates its signing keys, and with online
validation that rotation needs no action here. Offline validation would require
you to paste and maintain the keys.

`audience` is required and immutable. A trusted issuer is identified by issuer
plus audience, and a token is routed to the trusted issuer whose `iss` and `aud`
it carries, so a token minted for any other audience matches nothing. `aud` and
`iss` are therefore properties of the trusted issuer, not claim rules; the API
rejects them as claim rules.

Using the registry hostname as the audience is deliberate. GitHub will mint a
token with whatever `aud` the workflow asks for, so a token minted for some other
service cannot be replayed against this registry, and vice versa. The script takes
it from `HARBOR_URL`'s host, port included, so an instance on a non-default port
gets an audience like `registry.example.com:8180` and the workflow has to ask for
exactly that string. The pipeline requests exactly this audience; see
[`.github/actions/8gcr-token/action.yml`](../.github/actions/8gcr-token/action.yml).

Both `openid_config_url` and `issuer` must be HTTPS. An issuer you run yourself
in a lab therefore has to go in as `offline_validation:true` with `issuer` and
`jwks_keys` supplied directly.

The trusted issuer is visible under **Administration → Trusted Issuers**.

## 4. A robot account with no secret

An ordinary Harbor robot has a generated password that you have to store
somewhere. This one does not. It is linked to the trusted issuer by
`trusted_issuer_id`, Harbor returns no secret for it, and it can only be assumed
by presenting a valid token from that issuer.

```bash
ISSUER_ID=9   # from GET /api/v2.0/trusted-issuers

curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/robots" -d @- <<JSON
{
  "name": "todomvc-ci",
  "description": "Keyless CI robot (GitHub Actions)",
  "level": "system",
  "duration": -1,
  "trusted_issuer_id": $ISSUER_ID,
  "permissions": [
    {"kind":"project","namespace":"todomvc",
     "access":[{"resource":"repository","action":"push"},
               {"resource":"repository","action":"pull"},
               {"resource":"artifact","action":"read"},
               {"resource":"tag","action":"create"}]},
    {"kind":"project","namespace":"todomvc-npm",
     "access":[{"resource":"repository","action":"push"},
               {"resource":"repository","action":"pull"},
               {"resource":"artifact","action":"read"},
               {"resource":"tag","action":"create"}]},
    {"kind":"project","namespace":"todomvc-maven",
     "access":[{"resource":"repository","action":"push"},
               {"resource":"repository","action":"pull"},
               {"resource":"artifact","action":"read"},
               {"resource":"tag","action":"create"}]}
  ]
}
JSON
```

`duration: -1` means non-expiring. That is safe here precisely because there is no
secret to leak: the robot is unusable without a fresh, correctly-claimed token.

A permission entry naming a project that does not exist is rejected, so create the
projects first. The setup script **reconciles the robot's permissions with a
`PUT` on every run**, so a robot created before a project existed is widened
later instead of failing CI with a 401.

Two naming quirks, both handled by the script:

- Harbor stores a system robot under the configured `robot_name_prefix`
  (`bot_` on 8gcr, `robot$` by default) and returns the prefixed name, but the
  `GET /robots?q=name=...` query matches the **unprefixed** name.
- An update must carry the robot's **stored**, prefixed name, or it is rejected
  with `cannot update the level or name of robot`.

## 5. Claim rule

A claim rule is what connects a token to a robot. Without one the issuer is
trusted but no token maps to anything.

```bash
ROBOT_ID=31   # from GET /api/v2.0/robots

curl -su "admin:$PASS" -H 'Content-Type: application/json' \
  -X POST "$API/trusted-issuers/$ISSUER_ID/claims" \
  -d "{\"rules\":[{\"robot_id\":$ROBOT_ID,\"claim_path\":\"repository\",
        \"value\":\"container-registry/harbor-multi-artifact-support-examples\"}]}"
```

The `repository` claim is GitHub's `owner/repo`. Tokens from any other repository
pass the issuer and audience check but match no robot, so they authenticate as
nobody. To narrow further, add a rule on `ref` (`refs/heads/main`) or
`environment`; every rule bound to the robot must match. Two robots on the same
trusted issuer cannot have identical claim sets.

## 6. Check it

JSON or XML, not HTML, is the success signal. The portal answers `200 text/html`
for any path it does not recognise, so a path that lands on it looks like a
success to `curl -f` and like a parse error to npm.

```console
$ curl -su "admin:$PASS" "$HARBOR_URL/npm/todomvc-npm/-/whoami"
{"username":"admin"}

$ curl -s "$HARBOR_URL/maven/todomvc-maven/org/apache/commons/commons-lang3/maven-metadata.xml"
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>org.apache.commons</groupId>
  <artifactId>commons-lang3</artifactId>
  ...

$ curl -so /dev/null -w '%{http_code}\n' "$HARBOR_URL/v2/"
401
```

`401` from `/v2/` is correct: that is the OCI distribution API asking for a
token, which is what `docker login` answers. The Maven check deliberately asks for
an upstream coordinate rather than one of your own: nothing has been published yet
at this point, and an empty project answers `404` for its own artifacts while the
proxy cache is working perfectly.

The equivalent check the pipeline runs before it publishes anything is in
[06-pipeline.md](06-pipeline.md#preflight).

## Next

- [03: npm](../npm/README.md)
- [04: Maven](../maven/README.md)
- [05: Images and keyless auth](../images/README.md)
