# 02: Registry setup

[← 01: Concepts](01-concepts.md) · [03: Maven and npm →](03-maven-and-npm.md)

[`scripts/setup-8gcr.py`](../scripts/setup-8gcr.py) is the only provisioning
step. It is idempotent and checks every existing object against what it would
create, so it is safe to rerun. **The demo instance is wiped every Sunday at
03:17 UTC; rerun the setup after a reset.**

Requirements on the instance: 8gcr / Harbor Next 2.16 with the features
*Multi-Format Artifacts* and *Federated Robot Accounts* enabled. Check them
with `GET /api/v2.0/features`:

```console
$ curl -s -u "admin:$HARBOR_PASS" https://demo.container-registry.com/api/v2.0/features \
    | jq -r '.features[] | select(.section=="commercial" and .enabled) | .key'
enable_commercial_branding
enable_commercial_federated_robot_accounts
enable_commercial_multi_format_artifacts
enable_commercial_pgx_monitoring
```

## Run it

```console
$ export HARBOR_URL=https://demo.container-registry.com HARBOR_PASS=...
$ export API=$HARBOR_URL/api/v2.0      # used by the curl examples below
$ ./scripts/setup-8gcr.py

==> Target: https://demo.container-registry.com (audience: demo.container-registry.com)
  ok authenticated

==> Registry endpoints (upstreams to cache from)
  ok endpoint npmjs id=1 npm -> https://registry.npmjs.org
  ok endpoint maven-central id=2 maven -> https://repo1.maven.org/maven2
  ok endpoint dockerhub id=3 docker-hub -> https://hub.docker.com

==> Proxy-cache projects
  ok project todomvc-npm (proxy cache of npmjs, public=true, publishing allowed)
  ok project todomvc-maven (proxy cache of maven-central, public=true, publishing allowed)
  ok project dockerhub (proxy cache of dockerhub, public=false, publishing refused)

==> Multi-project
  ok todomvc -> sub-project dockerhub rank 1
  ok multi-project todomvc (private; own pushes first, then sub-projects by rank)

==> Trusted issuer: GitHub Actions OIDC
  ok trusted issuer github-actions id=1 https://token.actions.githubusercontent.com, audience demo.container-registry.com, online (follows key rotation)

==> Secretless robots for CI
  ok robot robot$todomvc-ci id=1 <- repository = container-registry/harbor-multi-artifact-support-examples, ref = refs/heads/main
  ok robot robot$todomvc-ci-pr id=2 <- repository = container-registry/harbor-multi-artifact-support-examples, event_name = pull_request

==> Done
    images, chart -> demo.container-registry.com/todomvc/{todo-api,todo-ui,charts/todomvc}
    base images   -> demo.container-registry.com/todomvc/library/<image> (via dockerhub)
    npm           -> https://demo.container-registry.com/npm/todomvc-npm/
    Maven         -> https://demo.container-registry.com/maven/todomvc-maven
    CI auth       -> GitHub OIDC token, audience demo.container-registry.com, repository container-registry/harbor-multi-artifact-support-examples
```

On a fresh instance this took 17 s. For your own fork, set
`GITHUB_REPO=<owner>/<repo>`. A rerun reconciles the robots' permissions and
claim rules; the output above was captured before `todomvc-ci` gained the
`ref` rule, which the rerun added.

## What it does, as API calls

The script is the reference; these are the calls it makes, for reading.

**Endpoints and proxy-cache projects.** `registry_id` and
`proxy_cache_allow_push` can only be set when the project is created.

```bash
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/registries" \
  -d '{"name":"npmjs","type":"npm","url":"https://registry.npmjs.org"}'
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/projects" \
  -d '{"project_name":"todomvc-npm","registry_id":1,
       "metadata":{"public":"true","proxy_cache_allow_push":"true"}}'
```

The endpoint type list in the portal (**Administration → Registries → New
Endpoint**) does not offer npm or Maven on the demo, because it comes from
`GET /replication/adapters`, which is filtered for replication. `POST
/registries` accepts `npm`, `maven` and the other package types regardless.

**The multi-project.** `multi_project` is create-only and cannot be combined
with `registry_id`. Sub-projects are added by name or id, with a rank:

```bash
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/projects" \
  -d '{"project_name":"todomvc","metadata":{"public":"false","multi_project":"true"}}'
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/projects/todomvc/subprojects" \
  -d '{"sub_project_name":"dockerhub","rank":1}'
```

```console
$ curl -s -u "admin:$HARBOR_PASS" "$API/projects/todomvc/subprojects" | jq -c '.[]'
{"sub_project_name":"dockerhub","rank":1,"is_proxy":true,...}
```

**Trusted issuer.** `audience` is required and immutable; the issuer plus
audience identifies the trusted issuer. Online validation fetches GitHub's
discovery document and follows its key rotation.

```bash
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/trusted-issuers" \
  -d '{"name":"github-actions","audience":"demo.container-registry.com","offline_validation":false,
       "openid_config_url":"https://token.actions.githubusercontent.com/.well-known/openid-configuration"}'
```

**Secretless robots and claim rules.** A robot created with
`trusted_issuer_id` has no secret. A token becomes the robot whose claim rules
it satisfies; when several match, the robot with the most matching rules wins.
Here the two CI robots never overlap:

| Robot | Claim rules | Token from a pull request | Token from `main` | Token from any other branch |
|---|---|---|---|---|
| `todomvc-ci` (push) | `repository`, `ref = refs/heads/main` | no match (`ref` is `refs/pull/<n>/merge`) | match | no match |
| `todomvc-ci-pr` (pull) | `repository`, `event_name = pull_request` | match | no match | no match |

A token that matches no robot authenticates as nobody, so a workflow on a
side branch cannot push even if it mints a token.

```bash
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/trusted-issuers/1/claims" \
  -d '{"rules":[{"robot_id":2,"claim_path":"repository","value":"container-registry/harbor-multi-artifact-support-examples"},
                {"robot_id":2,"claim_path":"event_name","value":"pull_request"}]}'
```

Two robots on one trusted issuer cannot have identical claim sets, and `aud`
and `iss` are rejected as claim rules because they belong to the issuer.

## Check it

```console
$ curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://demo.container-registry.com/npm/todomvc-npm/vue
200 application/json
$ curl -s -o /dev/null -w '%{http_code} %{content_type}\n' \
    https://demo.container-registry.com/maven/todomvc-maven/junit/junit/4.13.2/junit-4.13.2.pom
200 text/xml; charset=utf-8
$ crane manifest demo.container-registry.com/todomvc/library/nginx:alpine
Error: fetching manifest ...: UNAUTHORIZED: unauthorized to access repository: todomvc/library/nginx, action: pull
```

The last one is correct: `todomvc` is private. [04](04-ci-keyless.md) and
[05](05-flux-on-kind.md) pull through it with a token.

A JSON or XML answer is the success signal for the package URLs. An HTML
answer means the path did not reach the package handler.

## Next

[03: Maven and npm](03-maven-and-npm.md)
