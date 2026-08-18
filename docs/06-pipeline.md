# The pipeline

[← Images and WIF](05-images-wif.md) · [Concepts](01-concepts.md)

Three files build both apps and publish three kinds of artifact into one
registry, with no stored secret:

| File | Trigger | Grants `id-token: write` |
|---|---|---|
| [`_pipeline.yml`](../.github/workflows/_pipeline.yml) | `workflow_call` | no, it inherits |
| [`build.yml`](../.github/workflows/build.yml) | `pull_request` | **no** |
| [`publish.yml`](../.github/workflows/publish.yml) | push to `main`, manual | yes |

The work lives once, in the reusable `_pipeline.yml`. The two entry points differ
in one thing that matters, and it is the reason for the split: what they are
allowed to do. See [below](#why-the-split). This page walks the pipeline job by
job.

```mermaid
flowchart LR
    P[preflight] --> M[maven]
    P --> N[npm]
    P --> I[images]
    M --> V[verify]
    N --> V
    I --> V
    P --> V
```

`images` needs `preflight` as well. The push itself does not depend on the
package endpoints, but the two Dockerfiles resolve dependencies during the build,
so they take the same routing decision as the `maven` and `npm` jobs.

## Why the split

A pull request runs code from the branch under review: Maven plugins, npm
lifecycle scripts, `RUN` layers in a Dockerfile. If the job holding that code can
mint a registry credential, then so can the code.

The first version of this pipeline tried to solve that with a step condition:

```yaml
# NOT sufficient
permissions:
  id-token: write
steps:
  - if: github.event_name != 'pull_request'
    uses: ./.github/actions/8gcr-token
```

That does not work. Granting `id-token: write` puts `ACTIONS_ID_TOKEN_REQUEST_URL`
and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` into the job environment for **every** step,
so any build script in the job can request a token itself with two lines of curl.
Skipping the step that mints one changes nothing. A step condition is not a
permission boundary; the job's permission set is.

The boundary has to be the grant, and permissions cannot be set from an
expression. Hence two callers:

```yaml
# build.yml, on: pull_request
jobs:
  pipeline:
    uses: ./.github/workflows/_pipeline.yml
    permissions:
      contents: read          # no id-token, at all
    with:
      publish: false
```

```yaml
# publish.yml, on: push to main
jobs:
  pipeline:
    uses: ./.github/workflows/_pipeline.yml
    permissions:
      contents: read
      id-token: write         # the only grant in the repository
    with:
      publish: true
```

A called workflow can never hold more than its caller granted, so on a pull
request the token endpoint is not reachable from any step, whatever the branch's
build scripts try. `_pipeline.yml` deliberately declares no `permissions` block
of its own; declaring one would fail the run rather than elevate it.

Everything inside the pipeline keys off the `publish` input rather than the event
name, so the two paths cannot drift apart.

## Environment

```yaml
env:
  REGISTRY: 8gcr.container-registry.dev
  NPM_PROJECT: todomvc-npm
  MAVEN_PROJECT: todomvc-maven
  IMAGE_PROJECT: todomvc
```

One place to repoint the whole repository at a different registry.

## Artifact versions

`preflight` computes the version every job publishes under:

```bash
v="0.1.${{ github.run_number }}"
[ "${{ github.run_attempt }}" = "1" ] || v="$v-rc${{ github.run_attempt }}"
```

Release versions are immutable in the registry. `run_number` does not change when
you press "re-run", so a rerun would try to publish a coordinate that already
exists and fail with a 409. Folding the attempt in as a semver prerelease keeps
reruns publishable, and both npm and Maven accept the form.

## `preflight`

This job exists because of a specific failure mode, and it is worth understanding
rather than copying.

Harbor core serves `/npm/` and `/maven/`, but the ingress in front of core decides
whether those paths ever reach it. A deployment can have the feature compiled in
and still route those paths to the web UI, which answers with 785 bytes of
`index.html` and HTTP 200. npm then tries to parse that HTML as a packument and
reports a JSON parse error partway through an install; Maven reports something
equally unhelpful. The cause and the symptom look nothing alike, and this is the
current state of `8gcr.container-registry.dev`
([00-environment.md](00-environment.md)).

The probe checks the status and the content type, and bounds itself in time:

```bash
probe() {  # "true" only if a package API really answered
  read -r code ct <<<"$(curl -sS --connect-timeout 10 --max-time 30 \
    -o /dev/null -w '%{http_code} %{content_type}' "$1" || echo '000 -')"
  case "$ct" in *text/html*) echo "false"; return ;; esac
  case "$code" in
    200) echo "true"  ;;
    *)   echo "false" ;;
  esac
}
```

Three things it deliberately rejects:

- **200 with `text/html`** is the routing failure above.
- **A JSON error.** Checking only the content type would read a `404` or `500`
  JSON body as a healthy endpoint and send the build at it.
- **A 401.** That proves the endpoint is there, but the image builds resolve
  dependencies inside `docker build`, which receives no credentials, so pointing
  them at a project that demands authentication only moves the failure. This demo
  keeps its package projects public.

The timeouts matter because an endpoint can accept a connection and then never
respond, which would hang `preflight` and with it every job waiting on it.

The two outputs, `npm_ready` and `maven_ready`, gate the later jobs. When an
endpoint is unreachable the workflow does not fail; it builds against the upstream
registry instead, emits a `::warning::` naming the cause, and writes a small table
to the job summary. That keeps the repository buildable while the deployment gaps
are open, and makes the reason visible in one line instead of buried in an npm
stack trace.

## `maven`

```yaml
- id: auth
  if: needs.preflight.outputs.maven_ready == 'true' && inputs.publish
  uses: ./.github/actions/8gcr-token
  with:
    audience: ${{ env.REGISTRY }}
```

`inputs.publish` is false on a pull request, so nothing is minted there. That
condition is a convenience, not the safeguard; the safeguard is that the calling
workflow never granted the permission (see [Why the split](#why-the-split)).

The composite action mints the OIDC token and returns it as
`steps.auth.outputs.password`, with `steps.auth.outputs.username` fixed to `jwt`.
It calls `core.setSecret()` on the token first, so the value is masked in logs
before it can be printed anywhere.

The build step branches on the probe:

```bash
if [ "${{ needs.preflight.outputs.maven_ready }}" = "true" ]; then
  if mvn -B -s .mvn/settings.xml verify; then   # everything through the proxy cache
    exit 0
  fi
  echo "::warning::Build through the registry failed; retrying against Maven Central."
fi
mvn -B verify                                    # straight to Maven Central
```

Note the retry. A reachable endpoint is not proof it can serve a whole dependency
tree, and Maven proxy cold fetches could not be reproduced at all
([04-maven.md](04-maven.md#known-issue-cold-proxy-fetches-return-404)). Falling
back keeps the build honest about where the packages came from instead of failing
opaquely. The npm job does the same, for the packument defect in
[03-npm.md](03-npm.md).

The settings file is what redirects resolution, via `mirrorOf=*`, and it is also
what supplies credentials, via the `<server>` entry whose id matches. Dropping the
`-s` flag drops both at once, which is why there is no partial mode.

Publishing sets the version first:

```bash
mvn -B -s .mvn/settings.xml versions:set -DnewVersion="${{ needs.preflight.outputs.version }}" -DgenerateBackupPoms=false
mvn -B -s .mvn/settings.xml deploy -DskipTests
```

The version comes from `preflight` so every job publishes the same coordinate.
See [Artifact versions](#artifact-versions) for why the run attempt is part of it.
Details on Maven immutability in [04-maven.md](04-maven.md).

Publishing is gated on `inputs.publish`: pull requests build and resolve, but do
not write to the registry.

## `npm`

Same shape. The authentication step is the one worth reading:

```bash
# base64 -w0 is GNU-only; macOS needs -b0. Piping through tr works on both.
auth="$(printf 'jwt:%s' "$HARBOR_PASSWORD" | base64 | tr -d '\n')"
echo "::add-mask::$auth"
echo "//$REGISTRY/npm/$NPM_PROJECT/:_auth=$auth" >> .npmrc
```

Three deliberate details:

- `_auth`, not `_authToken`. Harbor's npm endpoint takes HTTP Basic. `_authToken`
  sends a Bearer header and gets a 401, despite what the portal's Usage tab
  suggests ([03-npm.md](03-npm.md)).
- `add-mask` on the base64 string. The token itself is already masked, but its
  base64 encoding is a different string and is an equally usable credential.
- The line is appended to the committed
  [`.npmrc`](../apps/todo-ui/.npmrc), which already carries the `registry=` line.
  Nothing secret is committed; the credential is added at runtime and lives only
  on the runner.

Install and publish then need no registry flags at all, because `.npmrc` decides
where both go.

## `images`

A matrix over the two apps. It takes `needs: preflight` so the in-image
dependency resolution can be pointed at the registry only when the endpoints
answer; the push to `/v2/` itself works regardless.

The Dockerfiles default to upstream registries and the job passes a build-arg to
override that:

```yaml
build-args: |
  ${{ matrix.app == 'todo-api' && needs.preflight.outputs.maven_ready == 'true' && 'MAVEN_SETTINGS=.mvn/settings.xml' || '' }}
```

Note that the build stage receives no registry credentials. `docker build` does
not inherit the job's environment, so dependency resolution inside the image
relies on the package projects being **public**. Keep them public, or pass
credentials in explicitly with build secrets.

```bash
printf '%s' "$HARBOR_PASSWORD" | docker login "$REGISTRY" -u "$HARBOR_USERNAME" --password-stdin
```

The token is passed through the environment and piped on stdin, not placed on the
command line. A command line is visible in a process listing and in `set -x`
output; stdin is not.

```yaml
push: ${{ inputs.publish }}
provenance: false
tags: |
  ${{ env.REGISTRY }}/${{ env.IMAGE_PROJECT }}/${{ matrix.app }}:${{ github.sha }}
  ${{ env.REGISTRY }}/${{ env.IMAGE_PROJECT }}/${{ matrix.app }}:latest
```

`provenance: false` keeps buildx from attaching an attestation manifest, which
turns a plain image into an index with an extra artifact. It is off here to keep
the demo's registry contents simple to read; turn it on when you want the
attestations.

Both tags point at the same image. `latest` is for humans, the commit sha is what
`verify` pulls.

Note that the `todo-api` image builds Maven inside the Dockerfile, using the same
`.mvn/settings.xml`. That stage therefore also resolves through the registry, and
it has no fallback: see the comment at the top of
[`apps/todo-api/Dockerfile`](../apps/todo-api/Dockerfile).

## `verify`

Publishing that is never read back proves nothing. This job runs on a clean
runner, mints a **new** token, and pulls all three artifact kinds.

```yaml
needs: [preflight, maven, npm, images]
if: inputs.publish
```

- **Images**: `docker login` with the fresh token, then `docker pull` by commit
  sha. A different token from the one that pushed, which shows the identity is
  reconstructed from claims on each request.
- **npm**: writes a throwaway `.npmrc` in a temp directory, then `npm view` and
  `npm pack` the version just published. The temp directory means a cold npm
  cache.
- **Maven**: `dependency:get` with `-Dmaven.repo.local="$(mktemp -d)"`. Without
  that flag the request could be satisfied from `~/.m2` and prove nothing.

The npm and Maven checks are skipped when the corresponding preflight output is
false, so the job stays green while those endpoints are unroutable, and starts
proving something the moment they are fixed.

## Running it against your own registry

1. Change `REGISTRY` and the three project names in the `env:` block.
2. Run [`scripts/setup-8gcr.sh`](../scripts/setup-8gcr.sh) against your instance
   with `GITHUB_REPO` set to your fork, so the claim rule matches.
3. Update the hard-coded hostname in
   [`apps/todo-ui/.npmrc`](../apps/todo-ui/.npmrc),
   [`apps/todo-ui/package.json`](../apps/todo-ui/package.json) (`publishConfig`),
   [`apps/todo-api/.mvn/settings.xml`](../apps/todo-api/.mvn/settings.xml) and the
   `harbor.registry` property in [`apps/todo-api/pom.xml`](../apps/todo-api/pom.xml).

No secret needs to be added to the repository. That is the entire point.

## Related

- [01-concepts.md](01-concepts.md)
- [02-harbor-setup.md](02-harbor-setup.md)
- [03-npm.md](03-npm.md)
- [04-maven.md](04-maven.md)
- [05-images-wif.md](05-images-wif.md)
