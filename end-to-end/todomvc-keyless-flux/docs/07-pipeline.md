# 6. Pipeline

[← 5. Helm chart](06-helm-chart.md) · [7. Flux deploy →](08-flux-deploy.md)

One reusable workflow, [`_e2e-todomvc-pipeline.yml`](../../../.github/workflows/_e2e-todomvc-pipeline.yml),
runs steps 2 to 5 from two entry points:

| Entry point | Trigger | `publish` | Token becomes |
|---|---|---|---|
| [`e2e-todomvc-build.yml`](../../../.github/workflows/e2e-todomvc-build.yml) | `pull_request` | false | `todomvc-ci-pr`, pull only |
| [`e2e-todomvc-publish.yml`](../../../.github/workflows/e2e-todomvc-publish.yml) | push to `main` that changes the example, `lib/` or `.github/`, and `workflow_dispatch` of `main` | true | `todomvc-ci`, push and pull |

```
maven   resolve via maven-central, verify, deploy jar to todomvc-maven
npm     resolve via npmjs, build, publish @todomvc/todo-ui to todomvc-npm
images  (todo-api, todo-ui) base images via todomvc, build, push to todomvc
  └─ chart   helm package, push to todomvc/charts
verify  after all four: pull images and chart, npm view, mvn dependency:get (publish only)
```

## Who may push

Both entry points grant `id-token: write`. The boundary that matters is in
Harbor's claim rules ([1. Setup](02-setup.md#secretless-robots-and-claim-rules)):
only a token whose `ref` is `refs/heads/main` maps to the robot that can push,
and a `pull_request` token maps to the one that can only pull, whatever the
pull request's build code does with it. `e2e-todomvc-publish.yml` also skips its job on any
ref but `main`. Pull requests from forks get no OIDC token from GitHub, so
their runs fail at the auth step.

## The token

[`.github/actions/8gcr-token`](../../../.github/actions/8gcr-token/action.yml) asks
GitHub for an OIDC token with the registry host as audience, masks it, and
returns it as the password. There is no exchange step: Harbor validates the
token itself. The action logs the claims that matter:

```console
token for aud=demo.container-registry.com event_name=pull_request ref=refs/pull/12/merge, valid 300s
```

**The token is valid for 300 seconds.** The first run of this pipeline minted
one token at the start of the Maven job and used it for `mvn deploy` seven
minutes later:

```console
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-deploy-plugin:3.1.4:deploy (default-deploy) on project todo-api: Failed to deploy artifacts: Could not transfer artifact com.containerregistry.todo:todo-api:pom:0.1.12 from/to 8gcr (https://demo.container-registry.com/maven/todomvc-maven): status code: 401, reason phrase: Unauthorized (401)
```

So every job mints a second token right before it pushes. How each client
takes the token:

```bash
printf '%s' "$TOKEN" | docker login demo.container-registry.com -u jwt --password-stdin
printf '%s' "$TOKEN" | helm registry login demo.container-registry.com -u jwt --password-stdin
export NPM_CONFIG_USERCONFIG="$(mktemp)"
echo "//demo.container-registry.com/npm/todomvc-npm/:_auth=$(printf 'jwt:%s' "$TOKEN" | base64 | tr -d '\n')" > "$NPM_CONFIG_USERCONFIG"
HARBOR_USERNAME=jwt HARBOR_PASSWORD="$TOKEN" mvn -s .mvn/settings.xml deploy
```

## Versions

Each publishing job computes its version, `0.1.<run_number>` with
`-rc<attempt>` on a rerun, with
[`.github/actions/version`](../../../.github/actions/version/action.yml). Release
versions are immutable, and "Re-run failed jobs" does not rerun jobs that
succeeded, so a shared version job would hand a rerun the old value. `verify`
reads each job's version from its outputs.

## Pull requests can read, not push

On a pull request the same jobs run with `publish: false`. The token resolves
to `todomvc-ci-pr`, which is enough to pull base images through the private
`todomvc` project, so the image builds succeed. Each image job then tries to
push with a fresh token and expects to be refused. From a run on
[PR #12](https://github.com/container-registry/harbor-multi-artifact-support-examples/pull/12):

```console
token for aud=demo.container-registry.com event_name=pull_request ref=refs/pull/12/merge, valid 300s
error from registry: unauthorized to access repository: todomvc/todo-api, action: push: unauthorized to access repository: todomvc/todo-api, action: push
```

## Read back

After a publish, `verify` reads everything back on a clean runner. From the
publish run 44645789533:

```console
Status: Downloaded newer image for demo.container-registry.com/todomvc/todo-api:bfa6cd622e89eddf64c7845059ce0d64f7ac1f6f
Status: Downloaded newer image for demo.container-registry.com/todomvc/todo-ui:bfa6cd622e89eddf64c7845059ce0d64f7ac1f6f
Pulled: demo.container-registry.com/todomvc/charts/todomvc:0.1.13
name = 'todomvc-todo-ui'
version = '0.1.13'
[INFO] Resolving com.containerregistry.todo:todo-api:jar:0.1.13
[INFO] BUILD SUCCESS
```

That run predates the split into hosted and proxy projects and the package
rename to `@todomvc/todo-ui`. The publish and read-back of the current layout
are shown in [2. Maven](03-maven.md#resolve-it-back) and
[3. npm](04-npm.md#resolve-it-back).

## Timings

Publish run 44645789533 on 2026-11-20, the second run against the freshly set
up demo:

| Job | Duration | Of which |
|---|---|---|
| npm | 22 s | `npm ci` + build + publish |
| images (todo-ui) | 51 s | |
| maven | 5 min 56 s | `versions:set` 2:08, `verify` 3:03, `deploy` 31 s (54 MB jar at 3.9 MB/s) |
| images (todo-api) | 5 min 56 s | Maven inside `docker build` 4:43 |
| chart | 13 s | |
| verify | 2 min 58 s | `dependency:get` 2:24 |
| whole run | 9 min 20 s | |

The Maven numbers are dominated by the proxy cache going upstream for files it
dropped instead of storing ([2. Maven](03-maven.md#the-proxy-cache-fills-less-than-it-serves)).

Maven job on pull requests, with and without the hosted project as a
resolution source ([2. Maven](03-maven.md#the-client-configuration)):

| Run | Hosted project in resolution | Lookups against `8gcr-hosted` | `versions:set` | `verify` | Maven job |
|---|---|---|---|---|---|
| 44653689841 | yes | 273 | 3:49 | 4:49 | 9 min 2 s |
| 44691004859 | no | 0 | 2:24 | 3:07 | 5 min 42 s |

## Running it against your own fork

1. Run `./setup.py` against your own instance, with
   `HARBOR_URL=https://harbor.example.com` and `GITHUB_REPO=<owner>/<repo>`.
   On a shared instance it would rewrite the claim rules of `todomvc-ci` and
   `todomvc-ci-pr` to your fork, and the original repository's CI would stop
   matching.
2. Change `demo.container-registry.com` in the files listed in the
   [README](../README.md#repository-layout).
3. Push a change under `end-to-end/todomvc-keyless-flux/` to `main`, or run
   `gh workflow run e2e-todomvc-publish.yml --ref main`. The publish workflow
   is path-filtered and does not run for unrelated pushes.

## Next

[7. Flux deploy](08-flux-deploy.md)
