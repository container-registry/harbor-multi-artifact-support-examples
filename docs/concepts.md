# Concepts

[← Example catalogue](../README.md)

The ideas every example builds on. Measurements and the full reasoning for one
concrete layout are in the end-to-end example's
[concepts page](../end-to-end/todomvc-keyless-flux/docs/01-concepts.md).

## Hosted, proxy cache, multi-project

| Kind | Created with | Holds | Publishing |
|---|---|---|---|
| Hosted | a plain project | what you push | yes |
| Proxy cache | `registry_id` of a registry endpoint (npmjs.org, Maven Central, Docker Hub, Homebrew, ...) | what clients pulled from upstream | no |
| Multi-project | `metadata.multi_project: "true"` | what you push, plus ranked sub-projects for pulls | yes, into the multi-project itself |

### Hosted

A plain project. On 8gcr 2.16 the same project serves OCI images, Helm charts,
npm and Maven; no package-type setting is needed.

### Proxy cache

Bound at creation to a registry endpoint. A miss is fetched from upstream,
streamed to the client and stored. The binding cannot be changed later.

Keep proxy caches read-only. v2.16.0 still accepts
`proxy_cache_allow_push: "true"` to publish into a proxy project, but 8gcr
change #658 removes it in the next release. Publish to a hosted project and
point clients at both:

| Client | Resolve from the proxy | Publish to the hosted project |
|---|---|---|
| npm | `registry=` | a scope, `@scope:registry=` |
| Maven | `<mirror>` with `mirrorOf *,!<hosted id>` | `distributionManagement` |

### Multi-project

New in 2.16, beta, part of the *Multi-Format Artifacts* feature. A pull
resolves in this order:

1. the multi-project's own content,
2. its sub-projects by rank, and for a proxy-cache sub-project also its upstream.

Pushes land in the multi-project itself. Authorization is checked against the
multi-project only, so one pull grant covers all its sub-projects.

Limits in 2.16.0:

- **OCI only.** Resolution is wired into the `/v2/` manifest and blob routes.
  npm and Maven requests to a multi-project do not consult sub-projects, even
  though the API accepts a package proxy as a sub-project.
- **`tags/list` is not aggregated.** It lists only the multi-project's own
  tags, so a version range (Flux `semver`, `crane ls`) sees nothing that only a
  sub-project holds. Pulling such content by tag still works.
- **Misses go upstream.** A miss asks every proxy sub-project's upstream,
  including the existence check `docker push` makes before uploading a new tag.

## Keyless: trusted issuers and secretless robots

A *trusted issuer* tells Harbor to accept JWTs from an OIDC issuer for one
audience. Use the registry host as the audience, so a token minted for anything
else is useless here.

- **Online:** Harbor fetches the discovery document and follows key rotation.
  For issuers it can reach, such as GitHub Actions.
- **Offline:** the issuer URL and the JWKS are stored in Harbor. For issuers
  it cannot reach, such as a Kubernetes API server.

A *federated robot* is linked to a trusted issuer and has no secret. *Claim
rules* map a token to it: every rule must match a claim in the token, and the
robot with the most matching rules wins. A token that matches none is
anonymous.

Clients send the token as the HTTP Basic password; the username is ignored
(`jwt` by convention). That works unchanged for docker, helm, npm (`_auth`),
Maven (`<server>`), Flux (ServiceAccount token auth) and the kubelet (a KEP-4412
credential provider).

The [end-to-end example](../end-to-end/todomvc-keyless-flux/README.md) uses this
for GitHub Actions and for a Kubernetes cluster. The artifact-type examples use
robot secrets to stay self-contained.

## Package paths

v2.16.0 serves packages under `/npm/<project>/`, `/maven/<project>/` and
`/homebrew/<project>/`. Later builds move them to `/pkg/<format>/<project>/`
and answer 404 on the old prefixes.
