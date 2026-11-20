# Contributing an example

## Where it goes

The top-level directory is the level:

| Directory | Level | Scope |
|---|---|---|
| `artifact-types/<type>/` | artifact type | one format, push or proxy and pull, nothing else |
| `end-to-end/<name>/` | end to end | several formats wired into a delivery flow |

A new level, for example `scenarios/` for air-gapped installs or replication,
is a new top-level directory that follows the contract below. Add it to the
level list in [README.md](README.md).

## The contract every example directory follows

1. **`README.md`** with, in this order:
   - a title, then one line: `**Level:** ... · **Artifact types:** ... · **Keyless:** yes|no`
   - a link back to the catalogue
   - **Prerequisites**: 8gcr version and features, tools with versions
   - **Setup**: the setup command and its real output
   - **Run**: the commands and their real, trimmed output
   - **Cleanup**: what to delete in Harbor and locally
2. **`setup.py`**: Python 3, standard library only, idempotent, configured
   through `HARBOR_URL`, `HARBOR_USER`, `HARBOR_PASS`. It imports its
   provisioning from [`lib/harborlib.py`](lib/harborlib.py); add a helper there
   instead of copying code. Secrets it creates go to a mode-600 file that
   `.gitignore` covers, never to stdout.
3. **Self-contained**: the example runs with only its own directory, `lib/`
   and `.github/actions/`. No imports from or links into other examples for
   anything needed to run it.
4. **Workflows** named `<level token>-<name>[-<entry>].yml`, with the level
   tokens `artifact` for `artifact-types/` and `e2e` for `end-to-end/`. One
   workflow per example is the default (`artifact-npm.yml`). An example that
   needs several entry points, such as build on pull requests and publish on
   `main`, gets one file per entry point plus a reusable
   `_<level token>-<name>-pipeline.yml` they call (`e2e-todomvc-build.yml`,
   `e2e-todomvc-publish.yml`, `_e2e-todomvc-pipeline.yml`). Every entry
   workflow has `paths:` filters on the example directory, `lib/**`, its own
   workflow files and, if it uses them, `.github/actions/**`, so it runs only
   when those change. A workflow without registry credentials checks what it
   can offline or anonymously; examples that publish from CI use the keyless
   token action in `.github/actions/8gcr-token`.
5. **Project names** start with `example-` (artifact types) or the example's
   own prefix, so examples do not collide on a shared instance. Proxy-cache
   projects for common upstreams are shared through `harborlib.SHARED_PROXIES`.

## Writing rules

- Every command in a README was run; paste the real output, trimmed.
- Use `harbor.example.com` as the placeholder host for your own instance.
- Proxy caches stay read-only; publish to hosted projects.
- No em dashes, no marketing tone. Comments explain why, not what.
