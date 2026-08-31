# Homebrew

[← The pipeline](06-pipeline.md) · [Concepts →](01-concepts.md)

Harbor can act as the network path for `brew`: formula metadata and bottle
downloads both route through one project, get cached, and show up in the
project's repositories and audit log. Unlike npm and Maven there is no
hosting side — Homebrew support is a pull-through proxy only, and this repo
publishes nothing to it. It is documented here because it completes the
"every package manager, one registry" story the other pages tell.

> **Where this was verified.** The hosted instance does not expose the
> Homebrew endpoints yet (`/homebrew/...` answered 404 on 2026-08-31);
> everything below was run against a local dev build of the same feature
> branch the next release cuts from. The commands and outputs are real,
> the hostname is `localhost:8080`. Re-probe the hosted instance before
> relying on it there.

## How brew talks to a registry

Homebrew keeps its two data families on two origins:

- **Formula metadata** (what `brew update` fetches): JSON from
  `https://formulae.brew.sh/api`.
- **Bottles** (the pre-built binaries `brew install` downloads): OCI images
  on `ghcr.io` under `homebrew/core`.

Harbor mirrors that split under one project:

```
/homebrew/<project>/api/...   → metadata endpoint  (cached 15 min)
/homebrew/<project>/v2/...    → bottle manifests and blobs (blobs cached as artifacts)
```

## Set it up

1. **Administration → Registries → New Endpoint** — provider **Homebrew**,
   URL `https://formulae.brew.sh/api`. This preset also fetches bottles from
   GHCR, and never forwards your endpoint credentials there. (The generic
   **Homebrew Registry** provider instead treats one custom URL as a unified
   mirror serving both path families.)
2. **New Project** → enable **Proxy Cache** → select that endpoint. The
   examples below use a project named `brew-priv`, access level private.

## Point brew at it

```bash
export HOMEBREW_API_DOMAIN="https://<harbor-host>/homebrew/brew-priv/api"
export HOMEBREW_ARTIFACT_DOMAIN="https://<harbor-host>/homebrew/brew-priv"
export HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1
```

The third line matters more than it looks: without it brew silently falls
back to ghcr.io whenever the artifact domain misbehaves, and `brew install`
reports success while your proxy saw nothing. With it, a proxy problem is a
visible failure instead of a quiet bypass.

## Authentication (private projects)

The endpoints accept **HTTP Basic** — a Harbor user or robot account with
pull permission on the project. The same rule as the
[npm endpoint](03-npm.md#authenticate) applies: Bearer tokens are rejected.

```console
$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/homebrew/brew-priv/api/formula/jq.json
401
$ curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $B64" http://localhost:8080/homebrew/brew-priv/api/formula/jq.json
401
$ curl -su admin:*** -o /dev/null -w '%{http_code}\n' http://localhost:8080/homebrew/brew-priv/api/formula/jq.json
200
```

brew has two env vars for registry auth, and only the Basic one works here:

```bash
# yes — sends Authorization: Basic on bottle downloads
export HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN="$(printf '%s:%s' "$USER" "$PASS" | base64 | tr -d '\n')"

# no — sends Authorization: Bearer, Harbor answers 401
# export HOMEBREW_DOCKER_REGISTRY_TOKEN=...
```

**The metadata gap:** brew attaches *no* credentials to `HOMEBREW_API_DOMAIN`
requests, so `brew update` against a private project gets 401. Either make
the proxy project public (the content is a mirror of public metadata and
public bottles — private-ness usually isn't the point, egress control is),
or embed credentials in the URL, which curl — and brew fetches with curl —
honors:

```bash
# robot names need URL-encoding: $ → %24, + → %2B
export HOMEBREW_API_DOMAIN="https://robot%24brew-priv%2Bpuller:SECRET@<harbor-host>/homebrew/brew-priv/api"
```

Verified: `curl 'http://admin:***@localhost:8080/homebrew/brew-priv/api/formula/jq.json'` → 200.

## What a bottle pull looks like

`brew install jq` asks for the version manifest, then the platform bottle
blob the manifest names. By hand:

```console
$ curl -su admin:*** -H 'Accept: application/vnd.oci.image.index.v1+json' \
    http://localhost:8080/homebrew/brew-priv/v2/homebrew/core/jq/manifests/1.8.1 \
  | jq -r '.manifests[].annotations
           | select(.["org.opencontainers.image.ref.name"] == "1.8.1.x86_64_linux")
           | .["sh.brew.bottle.digest"]'
82883e1f3b674759d0e3d0c37e6805c0f91e3886f3e40c7ebc57f1e0174dfbe7

$ curl -su admin:*** -o jq.bottle.tar.gz -w '%{http_code} %{size_download}b %{time_total}s\n' \
    http://localhost:8080/homebrew/brew-priv/v2/homebrew/core/jq/blobs/sha256:82883e1f…
200 494577b 1.107989s
```

That first pull round-tripped to GHCR. Pull it again:

```console
$ curl -su admin:*** -o jq.bottle2.tar.gz -w '%{http_code} %{size_download}b %{time_total}s\n' \
    http://localhost:8080/homebrew/brew-priv/v2/homebrew/core/jq/blobs/sha256:82883e1f…
200 494577b 0.088914s

$ cmp jq.bottle.tar.gz jq.bottle2.tar.gz && sha256sum jq.bottle2.tar.gz
82883e1f3b674759d0e3d0c37e6805c0f91e3886f3e40c7ebc57f1e0174dfbe7  jq.bottle2.tar.gz
```

Twelve times faster, byte-identical, and the checksum is the digest that was
requested — the cache serves the exact content-addressed payload, so brew's
own integrity check passes either way.

## Where it shows up

The cached bottle is a real project artifact, not an invisible blob:

- **Repositories:** `brew-priv/homebrew/core/jq`, one PACKAGE artifact
  tagged `1.8.1`, one layer per platform bottle that has been pulled.
- **Audit log:** one `pull artifact brew-priv/homebrew/core/jq:1.8.1` entry
  per download — cache misses and cache hits both.
- **Quota:** cached bottles count toward the project's storage quota and are
  deletable like any artifact.

```console
$ curl -su admin:*** http://localhost:8080/api/v2.0/projects/brew-priv/repositories | jq '.[0] | {name, artifact_count, pull_count}'
{
  "name": "brew-priv/homebrew/core/jq",
  "artifact_count": 1,
  "pull_count": 3
}
```

## What is not proxied

- **Formula version manifests and `api/` metadata** are cached briefly but
  not persisted — a fully offline `brew install` still needs the upstream
  reachable for those. The bottle payloads (the megabytes) are what survive
  an outage.
- **Casks and vendor-hosted taps** (`hashicorp/tap`, `heroku/brew`, …)
  download from arbitrary vendor URLs. brew *prefixes* the artifact domain
  to those URLs instead of replacing the host, producing a path no registry
  can serve. That is brew's behavior, not the proxy's; no
  `HOMEBREW_ARTIFACT_DOMAIN` value fixes it.
- A full `brew install` driven end-to-end through a proxy in CI is not yet
  exercised by this repo — the commands above verify each request brew makes,
  not the client itself.

## Next

- [01-concepts.md](01-concepts.md): back to the native-vs-proxy model
- [03-npm.md](03-npm.md) / [04-maven.md](04-maven.md): the ecosystems this repo publishes to
