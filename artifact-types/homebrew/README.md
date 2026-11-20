# Homebrew: `brew install` through a proxy, for machines that cannot reach Homebrew

**Level:** artifact type · **Artifact types:** Homebrew bottles and formula metadata · **Keyless:** no (robot secret)

[← Example catalogue](../../README.md)

Developer laptops and build hosts in an intranet reach the registry but not
`formulae.brew.sh`, `ghcr.io` or `github.com`. A Homebrew proxy-cache project
makes Harbor the only machine that talks to Homebrew; clients authenticate as
a pull-only robot, and every bottle they install is cached in the project and
written to the audit log.

```
brew client ──► Harbor /homebrew/brew-proxy/api/...  ──► formulae.brew.sh   (formula metadata)
                       /homebrew/brew-proxy/v2/...   ──► ghcr.io            (bottles)
```

This is pull only: the `/homebrew/` route has no publishing side. Harbor itself
still needs outbound HTTPS to those hosts. `brew update` fetches brew itself
from `github.com`, which is not proxied, so clients turn auto-update off.

## Prerequisites

- 8gcr / Harbor Next 2.16 with *Multi-Format Artifacts* enabled, admin credentials
- Homebrew 4.x on the client (ran with 4.6.20 in `homebrew/ubuntu24.04`), Python 3.10+
- On 8gcr builds newer than v2.16.0, the path is `/pkg/homebrew/` instead of `/homebrew/`: run `setup.py` with `PKG_ROOT=/pkg`.

## Setup

The transcripts on this page ran against the [shared demo](../../docs/shared-demo.md),
`https://demo.container-registry.com`; against your own instance the host in
the output is yours. Every command takes the host from `HARBOR_URL`.

```console
$ export HARBOR_URL=https://harbor.example.com HARBOR_PASS=...   # your instance
$ HOST=${HARBOR_URL#https://}
$ ./setup.py
==> Target: https://demo.container-registry.com
  ok authenticated

==> Homebrew proxy
  ok endpoint homebrew id=7 homebrew -> https://formulae.brew.sh/api
  ok project brew-proxy (proxy cache of homebrew, public=false)

==> Pull-only robot and brew client settings
  ok robot robot$example-brew id=11, secret rotated and written to .robot.env (mode 600)
  ok brew client settings written to brew.env (mode 600)
  ok robot reads formula metadata through the proxy (jq 1.8.2)

==> Done
```

`brew.env` holds five settings:

| Setting | Why |
|---|---|
| `HOMEBREW_API_DOMAIN=https://<robot>:<secret>@<host>/homebrew/brew-proxy/api` | brew sends no credentials to the metadata API, so they ride in the URL |
| `HOMEBREW_ARTIFACT_DOMAIN=https://<host>/homebrew/brew-proxy` | bottle downloads go to Harbor |
| `HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1` | a proxy problem fails visibly instead of silently falling back to `ghcr.io` |
| `HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN=<base64 robot:secret>` | authenticates bottle downloads; the Bearer variant is not accepted |
| `HOMEBREW_NO_AUTO_UPDATE=1` | stops `brew` from fetching itself from `github.com` |

brew reads `brew.env` itself, and skips an unreadable one silently. brew runs
as the user, so the file must be readable by that user:

```bash
install -d ~/.homebrew && install -m 0600 brew.env ~/.homebrew/brew.env      # per user
sudo install -d /etc/homebrew                                                # system-wide:
sudo install -m 0640 -o root -g <brew-users> brew.env /etc/homebrew/brew.env # group-readable
```

A root-owned `/etc/homebrew/brew.env` with mode 0600 does not work.

## Run

A Linux client with every Homebrew host resolved to `127.0.0.1` and no
`HOMEBREW_*` variable in its environment:

```console
$ docker run --rm --platform linux/amd64 \
    --add-host formulae.brew.sh:127.0.0.1 --add-host ghcr.io:127.0.0.1 \
    --add-host pkg-containers.githubusercontent.com:127.0.0.1 --add-host github.com:127.0.0.1 \
    --add-host api.github.com:127.0.0.1 --add-host raw.githubusercontent.com:127.0.0.1 \
    -v "$PWD/brew.env:/etc/homebrew/brew.env:ro" homebrew/ubuntu24.04 \
    bash -c 'brew --version | head -1; env | grep -c ^HOMEBREW_; brew install jq; jq --version'
Homebrew 4.6.20
0
==> Downloading https://demo.container-registry.com/homebrew/brew-proxy/v2/homebrew/core/jq/manifests/1.8.2-1
==> Downloading https://demo.container-registry.com/homebrew/brew-proxy/v2/homebrew/core/oniguruma/manifests/6.9.10
==> Downloading https://demo.container-registry.com/homebrew/brew-proxy/v2/homebrew/core/oniguruma/blobs/sha256:49eb885ab9a80ce30edc0aaa5f531fc0079a17e5cf41c2b6c34be0e53e763993
==> Downloading https://demo.container-registry.com/homebrew/brew-proxy/v2/homebrew/core/jq/blobs/sha256:631787d9b19df5e5557cc83f972080e541f543f8df2d1f212ca4290ff23e9764
==> Pouring oniguruma--6.9.10.x86_64_linux.bottle.tar.gz
🍺  /home/linuxbrew/.linuxbrew/Cellar/oniguruma/6.9.10: 16 files, 1.7MB
==> Pouring jq--1.8.2.x86_64_linux.bottle.1.tar.gz
🍺  /home/linuxbrew/.linuxbrew/Cellar/jq/1.8.2: 21 files, 1.5MB
jq-1.8.2
```

Metadata, the dependency `oniguruma` and both bottles came through Harbor; the
run took 20 s. The installed bottles are now artifacts in `brew-proxy`.

## Cleanup

Delete the project `brew-proxy`, the endpoint `homebrew` and the robot
`example-brew` in the portal, and `brew.env` and `.robot.env` locally.
