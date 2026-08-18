# The registry this demo runs against

Everything below was established by probing the running instance and reading the
binary it is running, not from documentation. Commands are included so you can
repeat every check yourself.

Target: **`https://8gcr.container-registry.dev`**

```console
$ curl -su admin:$PASS https://8gcr.container-registry.dev/api/v2.0/systeminfo
{"harbor_version":"2.16.0-e4715866","enable_project_federated_idp":true,
 "external_url":"https://8gcr.container-registry.dev","registry_url":"8gcr.container-registry.dev", ...}
```

## What the instance supports

| Capability | Status | How this was established |
|---|---|---|
| OCI container images | **working** | standard `/v2/` API, reachable |
| Workload Identity Federation | **working** | `/api/v2.0/federated-idps` accepts providers, claim rules and secretless robots, all created by `scripts/setup-8gcr.sh` against the live instance |
| npm + Maven code | **present in the running build** | see below |
| npm + Maven proxy-cache endpoints | **created successfully** | `POST /api/v2.0/registries` with `"type":"npm"` / `"maven"` → `201`, both report `status: healthy` |
| npm + Maven **usable end to end** | **blocked by two deployment-config gaps** | see [Known gaps](#known-gaps) |

## The multi-format feature is in the running build

The first, obvious conclusion from the outside is that the feature is missing:
`/npm/...` and `/maven/...` return HTML, and the provider dropdown in
**Administration → Registries** offers no npm or Maven. Both of those are
misleading. The feature is there.

The deployment is GitOps-managed from
[`container-registry/harbor-next`](https://github.com/container-registry/harbor-next)
branch `8gcr-rolling`, directory `deploy/flux/8gcr-dev/`. `helmrelease.yaml`
pins each component by digest, e.g.

```yaml
core:
  annotations:
    deploy.8gears.io/image-revision: "sha256:f4f965e450aeb696257c8b660d807e2b51c3e66bb073ac26905caba0eac34a75"
  image:
    repository: 8gears.container-registry.com/8gcr/harbor-core
    tag: latest
```

Pulling that exact digest and inspecting the `/core` binary inside it:

```console
$ strings core | grep -c e4715866          # matches the live harbor_version
1
$ strings core | grep -oE 'src/server/registry/(npm|maven|pypi|cargo|gomod|gosum|homebrew)/[a-z]+\.go' | sort -u
src/server/registry/cargo/handler.go
src/server/registry/gomod/handler.go
src/server/registry/gosum/mirror.go
src/server/registry/homebrew/handler.go
src/server/registry/maven/handler.go
src/server/registry/npm/handler.go
...
$ strings core | grep -oE 'reg/adapter/package\.init\.0'
reg/adapter/package.init.0                 # registers npm/pypi/maven/cargo/go/go-sumdb/homebrew
$ strings core | grep -cE 'federatedidp|robotjwt|jwkscache'
139                                        # WIF is in the same binary
```

The portal ships the UI too. It is in a lazily-loaded chunk, which is why
grepping `main.*.js` finds nothing:

```console
$ curl -s https://8gcr.container-registry.dev/492.a8343c8f6fdf610a.js \
    | grep -oE '_authToken|/npm/|/maven/|dist-tag' | sort | uniq -c
   1 _authToken
   1 /maven/
   2 /npm/
   7 dist-tag
```

So the code, the API and the UI are all deployed. What is missing is
configuration.

## Known gaps

Two independent deployment-config issues stand between this instance and a
working npm/Maven demo. Neither is a code defect; both are one-line changes in
the GitOps repo. Neither is fixable from this repository; they need cluster or
GitOps access.

### Gap 1: proxy-cache projects reject npm and Maven

```console
$ curl -su admin:$PASS -X POST https://8gcr.container-registry.dev/api/v2.0/projects \
    -H 'Content-Type: application/json' \
    -d '{"project_name":"todomvc-npm","registry_id":1,"metadata":{"public":"true","proxy_cache_allow_push":"true"}}'
{"errors":[{"code":"BAD_REQUEST","message":"bad request: unsupported registry type npm"}]}
```

The endpoint exists and is healthy; the *project* refuses to bind to it.
`src/server/v2.0/handler/project.go` gates this on
`config.GetPermittedRegistryTypesForProxyCache()`, which reads the
`PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE` environment variable
(`src/lib/config/systemconfig.go:143`).

The Helm chart hardcodes that variable **without** the package formats
(`harbor-next-helm`, `templates/core.configmap.yaml:36`):

```yaml
PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE: "docker-hub,harbor,azure-acr,ali-acr,aws-ecr,google-gcr,docker-registry,github-ghcr,jfrog-artifactory"
```

The Compose deployment that ships with the feature sets the full list
(`deploy/compose/docker-compose.yaml:62`):

```yaml
PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE: docker-hub,harbor,azure-acr,ali-acr,aws-ecr,google-gcr,docker-registry,github-ghcr,jfrog-artifactory,npm,pypi,maven,cargo,go,go-sumdb,homebrew
```

**Fix.** `templates/core.deployment.yaml:71` renders `.Values.core.extraEnv`
into `env:`, and `env` wins over `envFrom`, so this needs no chart change. In
`harbor-next` `deploy/flux/8gcr-dev/helmrelease.yaml`, under the existing
`values.core:` key:

```yaml
    core:
      extraEnv:
        - name: PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE
          value: "docker-hub,harbor,azure-acr,ali-acr,aws-ecr,google-gcr,docker-registry,github-ghcr,jfrog-artifactory,npm,pypi,maven,cargo,go,go-sumdb,homebrew"
```

The chart default should arguably be widened as well, so every deployment of a
build that has the feature can actually use it.

### Gap 2: `/npm/` and `/maven/` are not routed to core

```console
$ curl -su admin:$PASS -D- -o/dev/null https://8gcr.container-registry.dev/npm/library/-/whoami
HTTP/2 200
content-type: text/html
content-length: 785
```

785 bytes of `text/html` is the portal's static `index.html`. The request never
reached core. `harbor-next-helm`, `templates/ingress.yaml` hardcodes the path
list and has no values hook:

| Path | Backend |
|---|---|
| `/api/`, `/service/`, `/v2/`, `/chartrepo/`, `/c/` | core |
| `/` (everything else) | **portal** |

So `/npm/`, `/maven/`, `/pypi/`, `/cargo/`, `/go/`, `/go-sumdb/`, `/homebrew/`
all land on the Angular app. For comparison, the Compose deployment that ships
with the feature adds them explicitly (`config/nginx/proxy.conf`):

```nginx
location /npm/   { proxy_pass http://core:8080; proxy_send_timeout 900; proxy_read_timeout 900; }
location /maven/ { proxy_pass http://core:8080; proxy_send_timeout 900; proxy_read_timeout 900; }
```

Note that even the Compose config only covers npm and Maven. `/pypi/`,
`/cargo/`, `/go/` and `/homebrew/` are unreachable through the bundled proxy in
every shipped deployment, although core implements them.

**Fix (proper).** Add the package prefixes to the chart's ingress template
alongside `/api/` and `/v2/`.

**Fix (deployable now, no chart release).** Add a second Ingress to the Flux
bundle in `harbor-next` `deploy/flux/8gcr-dev/`, and reference it from
`kustomization.yaml`. More specific prefixes win over the chart's `/`, so the
two Ingresses coexist:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: harbor-packages
  namespace: 8gcr-dev-main
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "0"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
    - secretName: harbor-tls
      hosts: ["8gcr.container-registry.dev"]
  rules:
    - host: 8gcr.container-registry.dev
      http:
        paths:
          # keep in sync with src/server/server.go route registration
          - {path: /npm/,      pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
          - {path: /maven/,    pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
          - {path: /pypi/,     pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
          - {path: /cargo/,    pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
          - {path: /go/,       pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
          - {path: /go-sumdb/, pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
          - {path: /homebrew/, pathType: Prefix, backend: {service: {name: harbor-core, port: {number: 80}}}}
```

Confirm the core Service name for the release before applying
(`kubectl -n 8gcr-dev-main get svc`); it is `<release>-core`, i.e. `harbor-core`
for this HelmRelease.

### Verifying the fixes landed

```bash
# Gap 1
./scripts/setup-8gcr.sh          # todomvc-npm and todomvc-maven should now be created

# Gap 2: JSON, not HTML, is the success signal
curl -su admin:$PASS https://8gcr.container-registry.dev/npm/todomvc-npm/-/whoami
```

## A note on two things that look like evidence but are not

**The provider dropdown is curated.** `GET /api/v2.0/replication/adapters`
returns 14 entries with no npm or Maven, but it also omits `quay`, `gitlab`,
`dtr` and `native`, whose `init` symbols are equally present in the binary. The
list is not a reflection of what is registered, and creating the endpoints via
the API works regardless. Expect to create npm/Maven endpoints with `curl`, not
through the UI, until the list is widened.

**`npm login` does not work, and `_authToken` is not honoured.** Harbor accepts
HTTP Basic (`_auth` in `.npmrc`) only. `GET /-/v1/login` returns 404 and npm's
legacy fallback `PUT /-/user/org.couchdb.user:<name>` is treated as a push and
returns 401, so no token is ever issued. A `Bearer` header on an endpoint that
requires credentials returns 401 where the same value sent as `Basic` returns
200. The portal's **Usage** tab nevertheless emits an `_authToken` line
(`src/portal/.../usage/usage.component.ts`). Use `_auth`, as every example in
this repository does.

Note that on a public project anonymous reads succeed, so an `_authToken`
configuration can look correct until the first publish fails.
