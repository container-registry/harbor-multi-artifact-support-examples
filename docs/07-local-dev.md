# 07: Running the examples against a local Harbor dev instance

Everything in this repo also works against a Harbor Next dev environment
(`task dev:up` in the harbor repo) on plain HTTP at `localhost:8080` —
verified end to end with the npm, Maven, and image flows. This page collects
the local-only differences; the concepts are unchanged from the other docs.

## 1. Start Harbor and enable the feature

```bash
# in the harbor repo
task dev:up            # core on http://localhost:8080, admin / Harbor12345
```

The multi-format endpoints sit behind a commercial feature gate. Enable it
once per instance:

```bash
curl -u admin:Harbor12345 -X PUT -H 'Content-Type: application/json' \
  http://localhost:8080/api/v2.0/configurations \
  -d '{"enable_commercial_multi_format_artifacts": true}'
```

Without it, creating npm/maven registry endpoints fails with
`commercial feature multi_format_artifacts is not enabled`.

## 2. Provision registries and projects

The same setup script works; point it at the dev instance and skip the
GitHub-OIDC parts (no CI tokens locally):

```bash
HARBOR_URL=http://localhost:8080 HARBOR_PASS=Harbor12345 SKIP_WIF=1 \
  ./scripts/setup-8gcr.sh
```

That creates the `npmjs` and `maven-central` endpoints plus the
`todomvc-npm`, `todomvc-maven`, and `todomvc` projects.

## 3. npm

`apps/todo-ui` publishes wherever `.npmrc` points (there is no
`publishConfig` in `package.json`, on purpose), so retargeting is one file:

```bash
cd apps/todo-ui
auth=$(printf 'admin:Harbor12345' | base64)
cat > .npmrc <<EOF
registry=http://localhost:8080/npm/todomvc-npm/
//localhost:8080/npm/todomvc-npm/:_auth=$auth
always-auth=true
EOF

npm install         # cold pull-through from npmjs.org via Harbor
npm publish         # lands in todomvc-npm
```

Don't commit that `.npmrc` — the committed one targets the real registry.

## 4. Maven

`apps/todo-api` ships an example settings file for local dev
(`settings-local.xml` itself is gitignored — it's yours), and the pom's
deploy URL is overridable as one property:

```bash
cd apps/todo-api
cp .mvn/settings-local.xml.example .mvn/settings-local.xml
export HARBOR_USERNAME=admin HARBOR_PASSWORD=Harbor12345

mvn -B -s .mvn/settings-local.xml verify     # cold build through the proxy
mvn -B -s .mvn/settings-local.xml deploy -DskipTests \
    -Dharbor.url=http://localhost:8080       # publish to todomvc-maven
```

Cold pull-back proof, mirror-less on purpose:

```bash
mvn -B -s .mvn/settings-upstream.xml -Dmaven.repo.local="$(mktemp -d)" \
  dependency:get \
  -DremoteRepositories="8gcr::::http://localhost:8080/maven/todomvc-maven" \
  -Dartifact=com.containerregistry.todo:todo-api:<version>
```

## 5. Images

```bash
podman login -u admin -p Harbor12345 --tls-verify=false localhost:8080
podman push --tls-verify=false localhost:8080/todomvc/app:1.0.0
podman pull --tls-verify=false localhost:8080/todomvc/app:1.0.0
```

(`docker` works the same; `--tls-verify=false` / an insecure-registry entry is
needed because dev serves plain HTTP.)

## Known local quirks

- Under **rootless podman**, start the dev backend with
  `DEV_CONTAINER_USER=root`, otherwise the hot-reload build dies silently.
- `settings-local.xml` and the `.npmrc` above carry the default dev admin
  credentials pattern — never reuse them against a real registry.
