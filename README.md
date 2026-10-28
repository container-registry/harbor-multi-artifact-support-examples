# 8gcr Harbor registry for npm, Maven and container images

A working example of using a single [8gcr](https://container-registry.com/8gcr) / Harbor
instance as the only artifact store a project needs:

- **proxy** npm packages from npmjs.org and Maven artifacts from Maven Central through it,
- **publish** your own npm package and Maven jar back into Harbor,
- **push and pull container images**,
- From one GitHub Actions pipeline, with **no registry secret stored anywhere**.

The two TodoMVC apps in `apps/` exist only to give the pipeline something real to build.
The artifact flow, the pipeline and the guide are the point.

![The TodoMVC app the pipeline builds](docs/images/todomvc-app.png)

## What you will actually see

One project per ecosystem, each acting as a pull-through cache for its upstream and as a
home for your own packages at the same time:

![Projects in the registry portal](docs/images/portal-projects.png)

After a build, the npm project holds both the dependencies your build pulled from
npmjs.org and the package your pipeline published:

![npm packages cached and published](docs/images/portal-npm-repositories.png)

## Read it front to back

| | |
|---|---|
| [01: Concepts](docs/01-concepts.md) | Native hosting vs proxy cache, precedence, `proxy_cache_allow_push` |
| [02: Registry setup](docs/02-harbor-setup.md) | Endpoints, projects, federated identity, secretless robot |
| [03: npm](docs/03-npm.md) | Package it, publish it, proxy through it, pull it back |
| [04: Maven](docs/04-maven.md) | The same four steps for Maven |
| [05: Images and keyless auth](docs/05-images-wif.md) | Push and pull with no stored credential |
| [06: The pipeline](docs/06-pipeline.md) | The whole thing wired together in CI |
| [07: Local dev](docs/07-local-dev.md) | The same flows against a local `task dev:up` Harbor |
| [08: Homebrew](docs/08-homebrew.md) | `brew install` on intranet machines that cannot reach Homebrew, plus your own tools |
| [Recorded demos](docs/demos/README.md) | Every flow above, recorded end to end against a fresh instance |

## The five-minute path

Provision the registry side. This is idempotent, so re-running it is safe:

```bash
export HARBOR_URL=https://8gcr.container-registry.dev
export HARBOR_USER=admin HARBOR_PASS=...
export GITHUB_REPO=your-org/your-repo
./scripts/setup-8gcr.sh
```

It creates two proxy-cache registry endpoints, three projects, a federated identity
provider trusting GitHub's OIDC issuer, and a robot account that has **no secret** and can
only be assumed by a token carrying the right claims.

Then point your clients at it. npm (`apps/todo-ui/.npmrc`):

```ini
registry=https://8gcr.container-registry.dev/npm/todomvc-npm/
always-auth=true
```

Maven (`apps/todo-api/.mvn/settings.xml`) uses a wildcard mirror so plugin downloads are
covered too, not just dependencies:

```xml
<mirror>
  <id>8gcr</id>
  <mirrorOf>*</mirrorOf>
  <url>https://8gcr.container-registry.dev/maven/todomvc-maven</url>
</mirror>
```

Install, publish, read back. `npm run build` is not optional: `package.json` ships
`files: ["dist"]`, `dist` is not in git, and publishing without it succeeds with an
empty package at a version you can never reuse.

```bash
cd apps/todo-ui  && npm ci && npm run build && npm publish
cd apps/todo-api && mvn -B -s .mvn/settings.xml deploy
```

Needs JDK 21, Maven 3.9, Node 20 and Docker. `docker build` needs none of them, since
`apps/todo-api/Dockerfile` builds inside `maven:3.9-eclipse-temurin-21`.

The setup script takes the registry URL as an argument; the clients do not. Pointing
this repository at your own instance means editing the URL, scheme included, in five
committed files — [06-pipeline.md](docs/06-pipeline.md#running-it-against-your-own-registry)
step 3 lists them.

## How the keyless part works

There is no token exchange and no secret to rotate. The pipeline asks GitHub for an OIDC
token and hands it straight to the registry as the HTTP Basic **password**. Harbor
validates the signature against the identity provider's JWKS and matches the token's
claims to a robot account.

```yaml
- id: auth
  uses: ./.github/actions/8gcr-token
  with:
    audience: 8gcr.container-registry.dev

- run: |
    printf '%s' '${{ steps.auth.outputs.password }}' \
      | docker login 8gcr.container-registry.dev -u jwt --password-stdin
```

The username is ignored. The token expires in minutes. Nothing is stored in
`secrets.*`.

## Homebrew for intranet machines

Laptops and CI runners that cannot reach `formulae.brew.sh`, `ghcr.io` or
`github.com` still run `brew install`. Harbor is the only host that goes out:
public packages come through a Homebrew proxy-cache project, your own tools
from an ordinary OCI project, both with one pull-only robot.

![Only Harbor leaves the network](docs/images/homebrew-architecture.svg)

**Registry side.** `scripts/setup-homebrew.py` creates the Homebrew endpoint
(`https://formulae.brew.sh/api`), the private proxy project `brew-priv` and a
pull-only robot, and writes the client settings.

**Client side.** Five settings, rolled out as `/etc/homebrew/brew.env` so
users change nothing in their shell:

| Setting | Why |
|---|---|
| `HOMEBREW_API_DOMAIN=https://<robot>:<secret>@<harbor>/homebrew/brew-priv/api` | Formula metadata. brew sends no credentials on these requests, so they sit in the URL. |
| `HOMEBREW_ARTIFACT_DOMAIN=https://<harbor>/homebrew/brew-priv` | Manifests and bottles. |
| `HOMEBREW_ARTIFACT_DOMAIN_NO_FALLBACK=1` | A proxy problem fails loudly instead of quietly going to ghcr.io. |
| `HOMEBREW_DOCKER_REGISTRY_BASIC_AUTH_TOKEN=<base64 robot:secret>` | Bottle auth. Basic only, a Bearer token gets `401`. |
| `HOMEBREW_NO_AUTO_UPDATE=1` | `brew update` fetches brew itself from github.com, which is blocked. |

**Your own tools.** The proxy accepts no uploads. CI pushes the tool to a
private OCI project, a formula in your git tap points at the Harbor blob, and
clients install it with the same `brew.env`
([example tap](homebrew-tap/)):

![Internal tools: publish, describe, install](docs/images/homebrew-internal-tools.svg)

**Verified** on 2026-10-27 and 2026-10-28 with Homebrew 4.6.20 in
`homebrew/ubuntu24.04`, with all seven Homebrew and GitHub hosts blocked inside
the container: `brew install jq` and `brew install acme/tools/acme-hello`
both downloaded only from `8gcr.container-registry.dev`, and every proxied
bottle shows up as a `HOMEBREW` artifact with its pulls in the audit log under
the robot's name.

| Covered | Not covered |
|---|---|
| Bottles and dependencies from `homebrew/core` | Uploads to the proxy project (the `/homebrew/` route is pull-only) |
| Formula and cask metadata, so `brew search` works | brew itself: `brew update` needs github.com |
| Your own tools, as OCI artifacts installed through a git tap | Cask installers and third-party taps (vendor download URLs) |
| Pull-only robots, scoped per project or team | A fully offline registry: metadata is cached 15 minutes, so Harbor needs egress |
| Quota, retention and audit log like any Harbor project | Per-download audit of internal tools: pushes are logged, downloads are not |
| Cached bottles keep serving if GHCR is down | macOS clients: same URLs, not yet run |

Details, every command and its output: [08-homebrew.md](docs/08-homebrew.md).

## Repository layout

```
apps/todo-api/      Spring Boot + H2 backend. The Maven artifact.
apps/todo-ui/       Vue 3 TodoMVC frontend. The npm artifact.
.github/workflows/  The pipeline that publishes all three artifact kinds.
homebrew-tap/       Example Homebrew tap for an internal tool served by Harbor.
scripts/            Idempotent registry provisioning.
docs/               The guide.
```

## Every command here was run

Each page documents what was executed against
`https://8gcr.container-registry.dev`, with the output it produced. Where a
behaviour is still rough, the page says so at the point where you would hit it,
with the measurement that shows it, rather than in a separate caveats section.
