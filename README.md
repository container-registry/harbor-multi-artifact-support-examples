# 8gcr examples: one registry for every artifact type

Runnable examples for [8gears Container Registry (8gcr)](https://container-registry.com/8gcr)
2.16 as the registry for containers, Helm charts and language packages. Each
example lives in its own directory with a README, a setup script and the
material it pushes and pulls. Every transcript was run against
`https://demo.container-registry.com`, a [shared public demo](docs/shared-demo.md).

## Examples

| Example | Level | Artifact types | Keyless | Status |
|---|---|---|---|---|
| [TodoMVC, keyless, from source to Flux](end-to-end/todomvc-keyless-flux/README.md) | end to end | Maven, npm, OCI images, Helm | yes: GitHub OIDC, Kubernetes ServiceAccount tokens | available |
| [npm](artifact-types/npm/README.md) | artifact type | npm | no | available |
| [Maven](artifact-types/maven/README.md) | artifact type | Maven | no | available |
| [OCI images](artifact-types/oci-images/README.md) | artifact type | OCI images, Docker Hub proxy via multi-project | no | available |
| [Helm](artifact-types/helm/README.md) | artifact type | Helm charts (OCI) | no | available |
| [Homebrew](artifact-types/homebrew/README.md) | artifact type | Homebrew bottles and metadata (proxy) | no | available |
| PyPI | artifact type | PyPI | n/a | planned |
| Cargo | artifact type | Cargo | n/a | planned |
| Go modules | artifact type | Go modules, checksum database | n/a | planned |

**Levels.** An *artifact type* example shows one format on its own: provision,
push or proxy, pull, clean up. An *end to end* example wires several formats
into a delivery flow. New levels get their own top-level directory, see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Concepts

[docs/concepts.md](docs/concepts.md): hosted, proxy-cache and multi-projects,
their limits in 2.16, and the keyless trust chain of trusted issuers and
secretless robots.

## Layout

```
README.md               this catalogue
docs/                   concepts shared by all examples
artifact-types/<type>/  one format each: README, sample, setup.py
end-to-end/<name>/      complete flows: apps, chart, deploy, docs, setup.py
lib/harborlib.py        provisioning helpers every setup.py imports
.github/workflows/      per example: entry workflows filtered to its directory, plus
                        an optional reusable _<prefix>-pipeline.yml they call
.github/actions/        shared: the GitHub OIDC token action, the version action
```

## Requirements

8gcr 2.16 with *Multi-Format Artifacts* enabled, and *Federated
Robot Accounts* for the keyless examples. Both are opt-in commercial features of
8gcr. Setup scripts need Python 3.10+ with
the standard library only, and read `HARBOR_URL`, `HARBOR_USER` (default
`admin`) and `HARBOR_PASS`. Each example lists its other tools; for instance
the end-to-end example's `setup.py kind` also calls `kubectl`.
