# npm: publish to a hosted project, resolve through a proxy

**Level:** artifact type · **Artifact types:** npm · **Keyless:** no (robot secret)

[← Example catalogue](../../README.md)

Two projects with one job each: `npmjs`, a read-only proxy cache of npmjs.org,
and `example-npm`, a hosted project for your own packages. The sample package
is scoped (`@example/hello`), so one `.npmrc` routes the scope to the hosted
project and everything else to the proxy. See
[docs/concepts.md](../../docs/concepts.md) for why the two are separate.

## Prerequisites

- 8gcr / Harbor Next 2.16 with *Multi-Format Artifacts* enabled, admin credentials
- Node 18+ with npm, Python 3.10+
- On 8gcr builds newer than v2.16.0, package paths are `/pkg/npm/` instead of `/npm/`.

## Setup

```console
$ export HARBOR_URL=https://harbor.example.com HARBOR_PASS=...
$ ./setup.py
==> Target: https://demo.container-registry.com
  ok authenticated

==> Proxy and hosted project
  ok endpoint npmjs id=1 npm -> https://registry.npmjs.org
  ok project npmjs (proxy cache of npmjs, public=true)
  ok project example-npm (hosted, public)

==> Robot that may publish to the hosted project
  ok robot robot$example-npm id=7, secret rotated and written to .robot.env (mode 600)
    resolve -> https://demo.container-registry.com/npm/npmjs/
    publish -> https://demo.container-registry.com/npm/example-npm/

==> Done
```

Point [`sample/.npmrc`](sample/.npmrc) at your host if it is not the demo:

```ini
registry=https://demo.container-registry.com/npm/npmjs/
@example:registry=https://demo.container-registry.com/npm/example-npm/
```

## Run

Publish. Harbor reads HTTP Basic from `_auth`; `_authToken` (Bearer) is not
accepted. The credential goes into a user config, not the tracked `.npmrc`:

```console
$ set -a; . ./.robot.env; set +a
$ export NPM_CONFIG_USERCONFIG="$(mktemp)"
$ printf '//demo.container-registry.com/npm/example-npm/:_auth=%s\n' \
    "$(printf '%s:%s' "$HARBOR_ROBOT_USER" "$HARBOR_ROBOT_SECRET" | base64 | tr -d '\n')" > "$NPM_CONFIG_USERCONFIG"
$ cd sample
$ npm version "0.1.$(date +%Y%m%d%H%M%S)" --no-git-tag-version   # versions are immutable
v0.1.20261120152522
$ npm publish --loglevel http
npm notice Publishing to https://demo.container-registry.com/npm/example-npm/ with tag latest and default access
npm http fetch PUT 201 https://demo.container-registry.com/npm/example-npm/@example%2fhello 7405ms
+ @example/hello@0.1.20261120152522
```

Install it from a new project with the same `.npmrc` and no credential (both
projects are public). `left-pad` stands in for any public dependency:

```console
$ cd "$(mktemp -d)" && cp <repo>/artifact-types/npm/sample/.npmrc . && npm init -y
$ npm install @example/hello@0.1.20261120152522 left-pad --loglevel http
npm http fetch GET 200 https://demo.container-registry.com/npm/example-npm/@example%2fhello 99ms (cache miss)
npm http fetch GET 200 https://demo.container-registry.com/npm/npmjs/left-pad 166ms (cache miss)
npm http fetch GET 200 https://demo.container-registry.com/npm/npmjs/left-pad/-/left-pad-1.3.0.tgz 187ms (cache miss)
added 2 packages in 620ms
$ node -e "console.log(require('@example/hello')('8gcr'))"
hello, 8gcr
```

Republishing an existing version with different content is refused with
`409 Conflict ... immutable: version X already exists with different payload`.

## Cleanup

Delete the project `example-npm` and the robot `example-npm` in the portal, and
`.robot.env` locally. `npmjs` is shared with other examples.
