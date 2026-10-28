# Homebrew for machines that cannot reach Homebrew

[← README](../README.md) · [Concepts](../docs/01-concepts.md)

The situation: developer laptops and build hosts sit in an intranet. They can
reach the internal registry, but not `formulae.brew.sh`, `ghcr.io` or
`github.com`. People still want `brew install`.

Harbor solves this with a Homebrew **proxy-cache project**. Harbor is the only
machine that talks to Homebrew. Clients talk to Harbor, authenticate as a
pull-only robot, and every bottle they install is cached in the project,
counted against its quota and written to the audit log.

![Only Harbor leaves the network](images/homebrew-architecture.svg)

```
intranet client ──► Harbor  /homebrew/brew-priv/api/...  ──► formulae.brew.sh   (formula metadata)
  (brew)                    /homebrew/brew-priv/v2/...   ──► ghcr.io            (bottles)
                                                         ──► pkg-containers.githubusercontent.com
                                                             (ghcr.io redirects blob downloads here)
```

Everything on this page was run on 2026-10-27 and 2026-10-28 against
`https://8gcr.container-registry.dev` with the real `brew` client (Homebrew
4.6.20) in the official `homebrew/ubuntu24.04` image, with all Homebrew hosts
blocked inside the container.

## What it is and what it is not

- **It is a pull-through proxy.** Homebrew support has no hosting side: the
  `/homebrew/` route accepts `GET` and `HEAD` only, and `PUT`, `POST` and
  `PATCH` are refused. Your own tools go to an ordinary OCI project instead,
  see [5. Publish your own tools](#5-publish-your-own-tools).
- **Harbor still needs the internet.** Formula metadata is cached for minutes,
  not stored, so the proxy needs outbound HTTPS to the three hosts above. The
  clients need none.
- **Homebrew's own code is not proxied.** `brew update` git-fetches brew and
  `homebrew-core` from `github.com`. Clients turn auto-update off (below) and
  get brew upgrades the way your org ships any other tool.

## At a glance

| Covered | Not covered |
|---|---|
| Bottles and dependencies from `homebrew/core` | Uploads to the proxy project (the `/homebrew/` route is pull-only) |
| Formula and cask metadata, so `brew search` works | brew itself: `brew update` needs github.com |
| Your own tools, as OCI artifacts installed through a git tap ([section 5](#5-publish-your-own-tools)) | Cask installers and third-party taps (vendor download URLs) |
| Pull-only robots, scoped per project or team | A fully offline registry: metadata is cached 15 minutes, so Harbor needs egress |
| Quota, retention and audit log like any Harbor project | Per-download audit of internal tools: pushes are logged, downloads are not |
| Cached bottles keep serving if GHCR is down | macOS clients: same URLs, not yet run |

## 1. Provision the registry side

One script does it, idempotently:

```bash
export HARBOR_URL=https://8gcr.container-registry.dev
export HARBOR_PASS=...                          # admin password
export API="$HARBOR_URL/api/v2.0" PASS="$HARBOR_PASS"   # used by the curl examples below
./homebrew/setup-homebrew.py --out brew.env
```

```
==> https://8gcr.container-registry.dev
  ok endpoint homebrew id=10 -> https://formulae.brew.sh/api
  ok project brew-priv id=137 (private, proxy cache)
  ok robot bot_brew-priv+brew-puller exists, secret rotated
  ok client settings written to brew.env (contains the robot secret)
  ok robot reads formula metadata through the proxy (jq 1.8.2)
```

It creates:

| Object | Value | Why |
|---|---|---|
| Registry endpoint | `homebrew`, provider **Homebrew**, URL `https://formulae.brew.sh/api` | This preset fetches metadata from that URL and bottles from `ghcr.io`. |
| Project | `brew-priv`, private, proxy cache of that endpoint | The upstream binding is fixed at creation. |
| Robot | `bot_brew-priv+brew-puller`, `repository:pull` on `brew-priv` only | What the clients authenticate as. It cannot push, delete or see other projects. |

Harbor never returns an existing robot secret, so each run rotates it and
writes the new one to `brew.env` (mode 600). Re-running invalidates
previously distributed settings.

The multi-format endpoints sit behind the commercial feature gate
`enable_commercial_multi_format_artifacts`, and `homebrew` must be listed in
`PERMITTED_REGISTRY_TYPES_FOR_PROXY_CACHE` on the core container. Both are
already set on 8gcr.

The same steps by hand, through the portal:

1. **Administration → Registries → New Endpoint**: provider **Homebrew**, URL
   `https://formulae.brew.sh/api`. (The **Homebrew Registry** provider instead
   treats one custom URL as a unified mirror serving both metadata and bottles.)
2. **Projects → New Project**: enable **Proxy Cache**, select that endpoint,
   leave it private.
3. **Project → Robot Accounts → New Robot Account**: permission
   *Repository: Pull*, nothing else.

## 2. Configure the clients

`brew.env` holds five settings:

```bash
HOMEBREW_API_DOMAIN=https://<robot>:<secret>@8gcr.container-registry.dev/homebrew/brew-priv/api
HOMEBREW_ARTIFACT_DOMAIN=https://8gcr.container-registry.dev/homebrew/brew-priv
HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1
HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN=<base64 of robot:secret>
HOMEBREW_NO_AUTO_UPDATE=1
```

Why each one is there:

- **`HOMEBREW_API_DOMAIN`** carries the credentials in the URL because brew
  attaches none to metadata requests. Without them a private project answers
  `401`. The robot name contains `$` and `+`, so both parts are URL-encoded;
  the script does that.
- **`HOMEBREW_ARTIFACT_DOMAIN`** redirects manifest and bottle downloads.
- **`HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1`** makes a proxy problem a visible
  failure. Without it brew silently falls back to `ghcr.io`, which in an
  intranet just means a slower, more confusing failure, and on a machine that
  *can* reach `ghcr.io` means your proxy is bypassed without anyone noticing.
- **`HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN`** authenticates bottle
  downloads. Use this one, not `HOMEBREW_DOCKER_REGISTRY_TOKEN`: that sends a
  `Bearer` header, and the endpoint accepts only Basic.
- **`HOMEBREW_NO_AUTO_UPDATE=1`** stops brew from trying to `git fetch` itself
  from `github.com` before every install.

Distribute it system-wide by placing the file at `/etc/homebrew/brew.env`.
brew reads that file itself, so users need no shell profile changes. Verified
on Linux with no `HOMEBREW_*` variable set in the environment:

```console
$ docker run --rm ... -v ./brew.env:/etc/homebrew/brew.env:ro homebrew/ubuntu24.04 \
    bash -c 'env | grep -c ^HOMEBREW_; brew install jq | grep Downloading; jq --version'
0
==> Downloading https://8gcr.container-registry.dev/homebrew/brew-priv/v2/homebrew/core/jq/manifests/1.8.2-1
...
jq-1.8.2
```

## 3. Install from the intranet

The client container resolves every Homebrew host to `127.0.0.1`:
`formulae.brew.sh`, `ghcr.io`, `pkg-containers.githubusercontent.com`,
`github.com`, `api.github.com`, `raw.githubusercontent.com`,
`objects.githubusercontent.com`.

```console
unreachable: https://formulae.brew.sh
unreachable: https://ghcr.io
reachable: https://8gcr.container-registry.dev

$ brew install jq
==> Downloading https://8gcr.container-registry.dev/homebrew/brew-priv/v2/homebrew/core/jq/manifests/1.8.2-1
==> Downloading https://8gcr.container-registry.dev/homebrew/brew-priv/v2/homebrew/core/oniguruma/manifests/6.9.10
==> Downloading https://8gcr.container-registry.dev/homebrew/brew-priv/v2/homebrew/core/oniguruma/blobs/sha256:49eb885a…
==> Downloading https://8gcr.container-registry.dev/homebrew/brew-priv/v2/homebrew/core/jq/blobs/sha256:631787d9…
==> Pouring oniguruma--6.9.10.x86_64_linux.bottle.tar.gz
🍺  /home/linuxbrew/.linuxbrew/Cellar/oniguruma/6.9.10: 16 files, 1.7MB
==> Pouring jq--1.8.2.x86_64_linux.bottle.1.tar.gz
🍺  /home/linuxbrew/.linuxbrew/Cellar/jq/1.8.2: 21 files, 1.5MB

$ jq --version
jq-1.8.2
```

Dependencies resolve through the proxy too: `oniguruma` above, and
`ripgrep` pulled `zlib-ng-compat` and `bzip2` the same way. `brew search`
works, because it reads the formula list from the proxied API.

To prove the metadata really comes from Harbor rather than a cache in the
image: drop `HOMEBREW_API_DOMAIN` and the same install fails with
`curl: (7) Failed to connect to formulae.brew.sh`.

## 4. What the registry admin sees

Each installed bottle is a Harbor artifact of type `HOMEBREW`, tagged with the
formula version, one layer per platform pulled:

```console
$ curl -su admin:$PASS "$API/projects/brew-priv/repositories" \
    | jq -r '.[] | [.name, .artifact_count, .pull_count] | @tsv'
brew-priv/homebrew/core/oniguruma   1   8
brew-priv/homebrew/core/jq          2   20
```

Every download is in the audit log under the robot that made it:

```console
$ curl -su admin:$PASS "$API/auditlog-exts?page_size=4&q=resource%3D~brew-priv" \
    | jq -r '.[] | [.op_time, .username, .operation, .resource] | @tsv'
2026-10-27T13:46:05Z  bot_brew-priv+brew-puller  pull  brew-priv/homebrew/core/jq:1.8.2-1
2026-10-27T13:46:04Z  bot_brew-priv+brew-puller  pull  brew-priv/homebrew/core/oniguruma:6.9.10
```

Cached bottles count toward the project quota and are deleted like any other
artifact. After installing `jq` and `ripgrep` the project
held 6 repositories (`jq`, `oniguruma`, `ripgrep`, `pcre2`, `bzip2`,
`zlib-ng-compat`) using 13.1 MB. Give each team its
own robot if you want the audit log to say which team pulled what.

## 5. Publish your own tools

The `/homebrew/` route only proxies, so a tool your organisation builds
itself takes a different path through the same registry:

![Internal tools: publish, describe, install](images/homebrew-internal-tools.svg)

| | Public packages | Internal tools |
|---|---|---|
| Harbor project | `brew-priv`, Homebrew proxy cache | `internal-tools`, standard OCI project |
| Package definitions | formulae.brew.sh, through the proxy | your own git tap |
| How content arrives | fetched from upstream on first install | pushed by CI |
| Artifact type | `HOMEBREW` | generic OCI artifact |
| Audit log | every pull, per robot | pushes only |
| Egress | 3 hosts | none |

### Registry side

A private project, a push robot for CI, and one system robot the clients use
for both projects, so a single `brew.env` covers proxy and internal tools:

```bash
curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/projects" \
  -d '{"project_name":"internal-tools","metadata":{"public":"false"}}'

curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/robots" -d '{
  "name":"publisher","duration":-1,"level":"project","permissions":[
    {"kind":"project","namespace":"internal-tools","access":[
      {"resource":"repository","action":"push"},{"resource":"repository","action":"pull"}]}]}'

curl -su "admin:$PASS" -H 'Content-Type: application/json' -X POST "$API/robots" -d '{
  "name":"brew-client","duration":-1,"level":"system","permissions":[
    {"kind":"project","namespace":"brew-priv","access":[{"resource":"repository","action":"pull"}]},
    {"kind":"project","namespace":"internal-tools","access":[{"resource":"repository","action":"pull"}]}]}'
```

Put `bot_brew-client` and its secret into `brew.env` in place of the
`brew-puller` robot that `setup-homebrew.py` writes.

### Publish from CI

```console
$ COPYFILE_DISABLE=1 tar --no-xattrs -C pkg -czf acme-hello-1.0.0-linux-amd64.tar.gz acme-hello
$ shasum -a 256 acme-hello-1.0.0-linux-amd64.tar.gz
230b49fcbb8f7ffb703c315e84665b4a0a4403201e3a8ca906fbf6ef01889845  acme-hello-1.0.0-linux-amd64.tar.gz
$ oras push -u 'bot_internal-tools+publisher' -p "$SECRET" \
    8gcr.container-registry.dev/internal-tools/acme-hello:1.0.0 \
    acme-hello-1.0.0-linux-amd64.tar.gz:application/vnd.acme.tool.tar+gzip
```

`COPYFILE_DISABLE=1 tar --no-xattrs` matters on macOS: without it the tarball
carries Apple extended attributes and `brew install` prints tar warnings.

### Describe it in a tap

[`tap/Formula/acme-hello.rb`](tap/Formula/acme-hello.rb):

```ruby
class AcmeHello < Formula
  desc "Internal tool published to Harbor"
  homepage "https://git.internal/acme/acme-hello"
  url "https://8gcr.container-registry.dev/v2/internal-tools/acme-hello/blobs/sha256:230b49fcbb8f7ffb703c315e84665b4a0a4403201e3a8ca906fbf6ef01889845",
      using: CurlGitHubPackagesDownloadStrategy
  version "1.0.0"
  sha256 "230b49fcbb8f7ffb703c315e84665b4a0a4403201e3a8ca906fbf6ef01889845"

  def install
    bin.install "acme-hello"
  end
end
```

- The `url` is the registry blob endpoint, addressed by the tarball's digest,
  so `sha256` is that same digest.
- `using: CurlGitHubPackagesDownloadStrategy` is what makes brew send
  `HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN` on the download. With the
  default strategy the private project answers `401`.
- `HOMEBREW_ARTIFACT_DOMAIN` does not interfere: brew rewrites only `ghcr.io`
  URLs to it, so this Harbor URL is used as written.

### Install

Same blocked-hosts client as above, same `brew.env`:

```console
$ brew tap acme/tools /tap
$ brew install acme/tools/acme-hello
==> Downloading https://8gcr.container-registry.dev/v2/internal-tools/acme-hello/blobs/sha256:230b49fc…
==> Installing acme-hello from acme/tools
🍺  /home/linuxbrew/.linuxbrew/Cellar/acme-hello/1.0.0: 4 files, 1.5MB
$ acme-hello
acme-hello 1.0.0: built in-house, served by Harbor
$ brew install jq
==> Downloading https://8gcr.container-registry.dev/homebrew/brew-priv/v2/homebrew/core/jq/manifests/1.8.2-1
```

| Request for the blob | Result |
|---|---|
| `bot_brew-client`, HTTP Basic | `200`, sha256 matches |
| `bot_brew-client`, upload attempt | `401` |
| anonymous | `401` |

A client that uses only internal tools, without the proxy settings, also
needs `HOMEBREW_NO_INSTALL_FROM_API=1`. Otherwise brew first fetches
`formulae.brew.sh/api/formula_tap_migrations.jws.json` and fails.

### Releasing a new version

Push the new tarball, then commit the new `url`, `version` and `sha256` to
the tap. Clients pick it up with `brew update`: it still fails to fetch brew
itself from `github.com` and exits `1`, but reports `Updated 1 tap
(acme/tools)` and the new version is installable.

## Authentication, checked

| Request to `/homebrew/brew-priv/api/formula/jq.json` | Result |
|---|---|
| no credentials | `401` |
| `Authorization: Bearer ...` | `401` |
| HTTP Basic, robot or user | `200` |
| credentials embedded in the URL (`https://user:pass@host/...`) | `200` |

## Speed

Cache is not the point here, availability is. For the record, measured from
a laptop against 8gcr's host in Finland (Hetzner), `jq` x86_64 bottle
(494,577 bytes):

| | Total time |
|---|---|
| cold pull through Harbor (fetches from GHCR) | 1.34 s |
| warm pull through Harbor (served from the cache) | 0.66 to 1.12 s |
| same blob directly from `ghcr.io` | 0.34 s |

Cached and upstream payloads are byte-identical, and their sha256 is the
digest brew asked for, so brew's own integrity check passes.

## Limits

- **Homebrew namespaces only.** The bottle path serves `homebrew/core/*` and
  `homebrew/cask/*`; anything else (`/v2/library/alpine/...`) is refused, so the
  project cannot be abused as a generic GHCR proxy.
- **No uploads to the proxy project.** Internal tools use a separate OCI
  project and a git tap, see [section 5](#5-publish-your-own-tools).
- **No per-download audit for internal tools.** Their pushes are logged,
  plain blob downloads are not, and `pull_count` stays at 0.
- **Casks and third-party taps.** Cask metadata is served
  (`/api/cask/firefox.json` returns `200`), but cask installers and
  third-party tap bottles download from vendor URLs the proxy does not serve.
  Not tested here.
- **macOS clients.** Only Linux clients were tested. macOS uses the same URLs
  and the bottle tags exist (`arm64_sequoia`, `arm64_tahoe`, ...).
- **Old Linux bases.** In `homebrew/brew:latest` (Ubuntu 22.04, glibc 2.35)
  the install succeeds through the proxy but the current `jq` bottle will not
  run: it needs glibc 2.38. That is a Homebrew bottle requirement, not a proxy
  one; Ubuntu 24.04 works.
- **Upstream outage.** Bottles already cached keep serving, but metadata is
  only cached for minutes, so new installs need Harbor's upstream reachable.

## Demo

[`docs/demos/scripts/04-homebrew.py`](../docs/demos/scripts/04-homebrew.py) runs the
blocked-hosts install above end to end:

```bash
HARBOR_PASS=... ./homebrew/setup-homebrew.py --out brew.env
HARBOR_PASS=... BREW_ENV=brew.env ./docs/demos/scripts/04-homebrew.py
```

## Next

- [01-concepts.md](../docs/01-concepts.md): native hosting vs proxy cache
- [03-npm.md](../docs/03-npm.md) / [04-maven.md](../docs/04-maven.md): ecosystems where you can also publish
