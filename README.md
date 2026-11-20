# 8gcr examples: one registry for every artifact type

Runnable examples for [8gcr](https://container-registry.com/8gcr) (Harbor Next
2.16) as the registry for containers, Helm charts and language packages. Each
example lives in its own directory with a README, a setup script and the
material it pushes and pulls. Every transcript was run against
`https://demo.container-registry.com`, a [shared public demo](docs/shared-demo.md).

## Examples

| Example | Level | Artifact types | Keyless | |
|---|---|---|---|---|
| [TodoMVC, keyless, from source to Flux](end-to-end/todomvc-keyless-flux/README.md) | end to end | Maven, npm, OCI images, Helm | yes: GitHub OIDC, Kubernetes ServiceAccount tokens | |
| [npm](artifact-types/npm/README.md) | artifact type | npm | no | |
| [Maven](artifact-types/maven/README.md) | artifact type | Maven | no | |
| [OCI images](artifact-types/oci-images/README.md) | artifact type | OCI images, Docker Hub proxy via multi-project | no | |
| [Helm](artifact-types/helm/README.md) | artifact type | Helm charts (OCI) | no | |
| [Homebrew](artifact-types/homebrew/README.md) | artifact type | Homebrew bottles and metadata (proxy) | no | |
| PyPI | artifact type | PyPI | | planned |
| Cargo | artifact type | Cargo | | planned |
| Go modules | artifact type | Go modules, checksum database | | planned |

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
.github/workflows/      one workflow per example, filtered to its directory
.github/actions/        shared: the GitHub OIDC token action, the version action
```

## Requirements

8gcr / Harbor Next 2.16 with *Multi-Format Artifacts* enabled, and *Federated
Robot Accounts* for the keyless examples. Setup scripts need Python 3.10+ and
nothing else, and read `HARBOR_URL`, `HARBOR_USER` (default `admin`) and
`HARBOR_PASS`.
