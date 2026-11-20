# End to end: TodoMVC, keyless, from source to Flux

**Level:** end to end · **Artifact types:** Maven, npm, OCI images, Helm chart · **Keyless:** yes

[← Example catalogue](../../README.md)

The complete, runnable example of [8gcr](https://container-registry.com/8gcr)
(Harbor Next 2.16) as the only artifact store of a project, run against
`https://demo.container-registry.com`. A Java/Maven backend and
an npm frontend are built in GitHub Actions, packaged as container images and a
Helm chart, and deployed by Flux to a Kubernetes cluster. Every dependency comes
through Harbor, every artifact goes into Harbor, and no registry secret is
stored anywhere.

The TodoMVC apps in `apps/` only exist to give the flow something real to build.

## The flow

```mermaid
flowchart LR
    subgraph GH["GitHub Actions"]
      MVN["mvn verify / deploy"]
      NPM["npm ci / publish"]
      IMG["docker build / push"]
      CH["helm package / push"]
    end
    subgraph H["demo.container-registry.com"]
      MP["maven-central<br/>proxy, read-only"]
      MH["todomvc-maven<br/>hosted"]
      NP["npmjs<br/>proxy, read-only"]
      NH["todomvc-npm<br/>hosted"]
      T["todomvc<br/>multi-project:<br/>images + chart"]
      D["dockerhub<br/>proxy, read-only"]
    end
    subgraph K["Kubernetes (kind)"]
      F["Flux<br/>OCIRepository + HelmRelease"]
      KL["kubelet"]
    end
    MP -- dependencies --> MVN
    MVN -- jar --> MH
    NP -- dependencies --> NPM
    NPM -- "@todomvc/todo-ui" --> NH
    T -. "base images via sub-project" .-> D
    T -- base images --> IMG
    IMG -- todo-api, todo-ui --> T
    CH -- charts/todomvc --> T
    T -- chart --> F
    T -- images --> KL
```

## The project layout

| Project | Kind | Clients use it for |
|---|---|---|
| `maven-central` | proxy cache of Maven Central, read-only, public | Maven mirror (`mirrorOf *,!8gcr-hosted`) |
| `todomvc-maven` | hosted, public | Maven `distributionManagement` (id `8gcr-hosted`) |
| `npmjs` | proxy cache of npmjs.org, read-only, public | `.npmrc` `registry=` |
| `todomvc-npm` | hosted, public | `.npmrc` `@todomvc:registry=` |
| `todomvc` | multi-project, private | push and pull of images and the Helm chart; base images through it |
| `dockerhub` | proxy cache of Docker Hub, read-only, private | only as sub-project of `todomvc` |

Multi-project resolution in 2.16 works for OCI artifacts only, so npm and Maven
use a proxy and a hosted project each. [01: Concepts](docs/01-concepts.md#the-layout-and-why)
has the reasons and the evidence.

## Prerequisites

- 8gcr / Harbor Next 2.16 with *Multi-Format Artifacts* and *Federated Robot Accounts* enabled, and admin credentials
- a fork of this repository with GitHub Actions enabled
- Docker, kind 0.33+, kubectl, Python 3.10+
- for local builds: JDK 21 and Maven 3.9, Node 22

## The keyless trust chain

```mermaid
flowchart LR
    GHA["GitHub Actions job"] -- "OIDC token<br/>aud = demo.container-registry.com" --> TI1["trusted issuer github-actions<br/>online JWKS"]
    SA["Kubernetes ServiceAccount<br/>todomvc/todomvc"] -- "SA token<br/>aud = demo.container-registry.com" --> TI2["trusted issuer kind-todomvc<br/>offline, pinned JWKS"]
    TI1 -- "repository + ref = refs/heads/main" --> R1["robot todomvc-ci<br/>push"]
    TI1 -- "repository + event_name = pull_request" --> R2["robot todomvc-ci-pr<br/>pull"]
    TI2 -- "sub = system:serviceaccount:todomvc:todomvc" --> R3["robot todomvc-k8s<br/>pull todomvc"]
```

Every client sends the token as the HTTP Basic password with user `jwt`.
Harbor checks signature, issuer and audience, then maps the claims to a robot
that has no secret of its own. Flux's source-controller and the kubelet (through
a KEP-4412 credential provider) both mint the ServiceAccount token themselves.

## Read it in order

The sections follow the flow. Paths and headings are stable for linking.

| Step | Page |
|---|---|
| Concepts | [docs/01-concepts.md](docs/01-concepts.md): layout, multi-project, trust chain |
| 1. Setup | [docs/02-setup.md](docs/02-setup.md): `setup.py`, the API calls behind it |
| 2. Maven | [docs/03-maven.md](docs/03-maven.md): resolve through the proxy, deploy to hosted, resolve it back |
| 3. npm | [docs/04-npm.md](docs/04-npm.md): the same for npm, with a scoped package |
| 4. Images | [docs/05-images.md](docs/05-images.md): base images through the multi-project, push the app images |
| 5. Helm chart | [docs/06-helm-chart.md](docs/06-helm-chart.md): package and push the chart as OCI |
| 6. Pipeline | [docs/07-pipeline.md](docs/07-pipeline.md): the GitHub Actions workflows, tokens, robots, timings |
| 7. Flux deploy | [docs/08-flux-deploy.md](docs/08-flux-deploy.md): kind, offline trusted issuer, Flux and kubelet without secrets |

## Setup and run

From this directory:

```bash
export HARBOR_URL=https://harbor.example.com HARBOR_PASS=...   # your own instance
export GITHUB_REPO=<owner>/<repo>  # your fork; the CI robots trust only this repository
./setup.py                         # projects, trusted issuer, robots
# push a change under this directory to main, or: gh workflow run e2e-todomvc-publish.yml --ref main
# build the credential provider first, see docs/08-flux-deploy.md
kind create cluster --config deploy/kind/kind-config.yaml
kubectl apply -f deploy/kind/node-audience-rbac.yaml
./setup.py kind                    # trust this cluster
kubectl apply -f https://github.com/fluxcd/flux2/releases/download/v2.10.0/install.yaml
kubectl apply -f deploy/flux/
```

`demo.container-registry.com` is a shared public demo, see
[the note](../../docs/shared-demo.md). Run the flow against your own instance.

## Cleanup

```bash
kind delete cluster --name todomvc
```

Then delete the projects `todomvc`, `todomvc-npm`, `todomvc-maven`, the
trusted issuers `github-actions` and `kind-todomvc` and the robots
`todomvc-ci`, `todomvc-ci-pr` and `todomvc-k8s` in the portal. The proxy
projects `npmjs`, `maven-central` and `dockerhub` are shared with the
artifact-type examples.

## Repository layout

```
apps/todo-api/   Spring Boot backend: the Maven artifact and one image
apps/todo-ui/    Vue 3 frontend: the npm package @todomvc/todo-ui and one image
chart/todomvc/   Helm chart for both, pushed as OCI
deploy/flux/     Namespace, ServiceAccount, OCIRepository, HelmRelease
deploy/kind/     kind config and the kubelet credential provider
setup.py         The only provisioning step, idempotent (helpers in ../../lib)
docs/            The walkthrough, 01 to 08

../../.github/workflows/e2e-todomvc-*.yml, _e2e-todomvc-pipeline.yml   the pipeline
../../.github/actions/8gcr-token                                      the OIDC token action
```

To point this at your own instance, change `demo.container-registry.com` in
`apps/todo-api/pom.xml`, `apps/todo-api/.mvn/settings.xml`, `apps/todo-ui/.npmrc`,
`../../.github/workflows/_e2e-todomvc-pipeline.yml`, `chart/todomvc/values.yaml`,
`deploy/flux/` and `deploy/kind/`. On 8gcr builds newer than v2.16.0 the package
paths move from `/npm/` and `/maven/` to `/pkg/npm/` and `/pkg/maven/`; the same
files carry them.

Every command in the docs was run against the demo (v2.16.0) on 2026-11-20 and
the output shown is what it printed, trimmed.
