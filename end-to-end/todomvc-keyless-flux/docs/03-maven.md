# 2. Maven

[← 1. Setup](02-setup.md) · [3. npm →](04-npm.md)

`apps/todo-api` resolves every dependency and plugin through the read-only
`maven-central` proxy and deploys its jar to the hosted `todomvc-maven` project.

## The client configuration

[`apps/todo-api/.mvn/settings.xml`](../apps/todo-api/.mvn/settings.xml):

```xml
<mirror>
  <id>8gcr-proxy</id>
  <mirrorOf>*,!8gcr-hosted</mirrorOf>
  <url>https://demo.container-registry.com/maven/maven-central</url>
</mirror>
...
<server>
  <id>8gcr-hosted</id>
  <username>${env.HARBOR_USERNAME}</username>
  <password>${env.HARBOR_PASSWORD}</password>
</server>
```

and in [`pom.xml`](../apps/todo-api/pom.xml):

```xml
<distributionManagement>
  <repository>
    <id>8gcr-hosted</id>
    <url>${harbor.url}/maven/${harbor.maven.project}</url>
  </repository>
</distributionManagement>
```

- `mirrorOf *` rather than `central`: `central` covers the built-in
  repository for dependencies and plugins, but not repositories that
  third-party POMs declare themselves. The wildcard sends those through the
  proxy too.
- The hosted project is not a resolution source. No build in this flow
  consumes the published jar (the image builds from source), and listing it as
  a repository made Maven ask it first for every dependency: 218 extra 404
  lookups locally, 273 in CI, and a Maven job of 9:02 instead of 5:56.
  `!8gcr-hosted` only keeps an explicit `-DremoteRepositories=8gcr-hosted::...`
  from being sent to the proxy, which the read-back below relies on.
- One id, `8gcr-hosted`, ties `distributionManagement` to the `<server>`
  credentials.
- Neither project needs a credential to read: both are public, and Maven only
  sends `<server>` credentials when challenged.

A cold build with this configuration, inside `maven:3.9-eclipse-temurin-21`:

```console
$ mvn -B -s .mvn/settings.xml verify -DskipTests | tee build.log
...
[INFO] BUILD SUCCESS
[INFO] Total time:  03:30 min
$ grep -c 'from 8gcr-hosted' build.log
0
$ grep -rhoE '>[a-z0-9-]+=' ~/.m2/repository --include=_remote.repositories | sort | uniq -c
 473 >8gcr-proxy=
```

Every resolved file came through the `maven-central` proxy, none from Central
directly and none from the hosted project.

## Build and deploy, keyless

The token is the password, user `jwt`. In CI that is the GitHub OIDC token
([6. Pipeline](07-pipeline.md)). To show the same mechanism from a workstation,
this run used a token of a ServiceAccount `publisher` in the kind cluster of
[7. Flux deploy](08-flux-deploy.md), which the setup script does not create.
It was set up for this run and removed afterwards:

```bash
kubectl -n todomvc create sa publisher
ISSUER_ID=$(curl -su "admin:$HARBOR_PASS" "$API/trusted-issuers?q=name%3Dkind-todomvc" | jq '.[0].id')
PUSH='[{"resource":"repository","action":"push"},{"resource":"repository","action":"pull"},
       {"resource":"artifact","action":"read"},{"resource":"tag","action":"create"}]'
ROBOT_ID=$(curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/robots" -d "{
  \"name\":\"probe-publisher\",\"level\":\"system\",\"duration\":-1,\"trusted_issuer_id\":$ISSUER_ID,
  \"permissions\":[{\"kind\":\"project\",\"namespace\":\"todomvc-maven\",\"access\":$PUSH},
                   {\"kind\":\"project\",\"namespace\":\"todomvc-npm\",\"access\":$PUSH}]}" | jq .id)
curl -su "admin:$HARBOR_PASS" -H 'Content-Type: application/json' -X POST "$API/trusted-issuers/$ISSUER_ID/claims" \
  -d "{\"rules\":[{\"robot_id\":$ROBOT_ID,\"claim_path\":\"sub\",\"value\":\"system:serviceaccount:todomvc:publisher\"}]}"
```

The robot create response carries no secret:
`{"id":5,"name":"robot$probe-publisher","secret":null}`. This block was rerun
as written afterwards and created the same claim for robot 6. Remove the
temporary identity when done; deleting the robot also deletes its claim rule:

```bash
curl -su "admin:$HARBOR_PASS" -X DELETE "$API/robots/$ROBOT_ID"
kubectl -n todomvc delete sa publisher
```

Both robots (5 and 6) were deleted this way; afterwards `kind-todomvc` held
only the claim of `todomvc-k8s`.

The deploy (run while the hosted project was still configured as a
repository, which only affects resolution):

```console
$ export HARBOR_USERNAME=jwt HARBOR_PASSWORD="$(kubectl -n todomvc create token publisher --audience $HOST --duration 1h)"
$ mvn -B -q -s .mvn/settings.xml versions:set -DnewVersion=0.0.1-local -DgenerateBackupPoms=false
$ mvn -B -s .mvn/settings.xml deploy -DskipTests
...
[INFO] Uploaded to 8gcr-hosted: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.0.1-local/todo-api-0.0.1-local.pom (2.0 kB at 285 B/s)
[INFO] Uploaded to 8gcr-hosted: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.0.1-local/todo-api-0.0.1-local.jar (54 MB at 2.6 MB/s)
[INFO] Uploaded to 8gcr-hosted: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/maven-metadata.xml (359 B at 3.7 kB/s)
[INFO] BUILD SUCCESS
```

Release versions are immutable, so CI sets one per run
(`0.1.<run_number>`, see [6. Pipeline](07-pipeline.md#versions)).

## What Harbor serves back

Harbor generates `maven-metadata.xml` from what it holds and serves checksums
it computes itself:

```console
$ curl -s $HARBOR_URL/maven/todomvc-maven/com/containerregistry/todo/todo-api/maven-metadata.xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.containerregistry.todo</groupId>
  <artifactId>todo-api</artifactId>
  <versioning>
    <latest>0.1.13</latest>
    <release>0.1.13</release>
    <versions>
      <version>0.1.13</version>
    </versions>
    <lastUpdated>20261120003127</lastUpdated>
  </versioning>
</metadata>
$ U=$HARBOR_URL/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.1.13/todo-api-0.1.13.pom
$ curl -s $U.sha1; echo; curl -s $U | shasum -a 1
97a15e43e50f56af712ddc3e9178fd30d7c32af8
97a15e43e50f56af712ddc3e9178fd30d7c32af8  -
```

(Captured from the CI-published 0.1.13 before the layout split, when the jar
still went into the proxy project; the hosted project behaves the same.)

## Resolve it back

A separate read-back names the hosted project explicitly, with an empty local
repository:

```console
$ mvn -B -s .mvn/settings.xml dependency:get -Dtransitive=false \
    -DremoteRepositories=8gcr-hosted::default::$HARBOR_URL/maven/todomvc-maven \
    -Dartifact=com.containerregistry.todo:todo-api:0.0.1-local
[INFO] Downloaded from 8gcr-hosted: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.0.1-local/todo-api-0.0.1-local.pom (2.0 kB at 2.2 kB/s)
[INFO] Downloaded from 8gcr-hosted: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.0.1-local/todo-api-0.0.1-local.jar (54 MB at 13 MB/s)
[INFO] BUILD SUCCESS
[INFO] Total time:  02:41 min
```

The pipeline's `verify` job runs the same command after every publish. A
project that does consume the jar adds `todomvc-maven` as a `<repository>`
with id `8gcr-hosted`.

## The proxy cache fills less than it serves

Under load, Harbor 2.16.0 drops many proxy-cache writes. Fills run on a fixed
pool of 4 workers with a queue of 16, and a full queue drops the fill with a
warning. During one cold `npm ci` and one Maven build the core logged:

```console
$ kubectl -n <harbor> logs deploy/harbor-core --since=20m | grep -c 'queue is full'
964
$ kubectl -n <harbor> logs deploy/harbor-core | grep 'queue is full' | head -1
[WARNING] [/server/registry/pkgfill/pkgfill.go:70]: pkgfill: queue is full, dropping cache fill npm:todomvc-npm/vue@3.5.41
```

The client still gets its file, streamed from upstream, so builds succeed. A
dropped fill only means the next request goes upstream again, which is why
repeat Maven builds stay slow ([timings](07-pipeline.md#timings)).

## Next

[3. npm](04-npm.md)
