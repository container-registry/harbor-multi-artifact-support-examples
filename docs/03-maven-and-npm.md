# 03: Maven and npm

[← 02: Registry setup](02-registry-setup.md) · [04: CI, images and chart →](04-ci-keyless.md)

Both builds resolve every dependency through Harbor and publish their artifact
back into the same project, at the same URL.

## Maven

[`apps/todo-api/.mvn/settings.xml`](../apps/todo-api/.mvn/settings.xml):

```xml
<mirror>
  <id>8gcr</id>
  <mirrorOf>*</mirrorOf>
  <url>https://demo.container-registry.com/maven/todomvc-maven</url>
</mirror>
...
<server>
  <id>8gcr</id>
  <username>${env.HARBOR_USERNAME}</username>
  <password>${env.HARBOR_PASSWORD}</password>
</server>
```

`mirrorOf=*` rather than `central`: a `<repositories>` block in the pom only
redirects dependencies, while plugins keep coming from the built-in plugin
repository. The wildcard mirror catches both. The `<server>` id equals the
mirror id and the `distributionManagement` id in
[`pom.xml`](../apps/todo-api/pom.xml), so one entry authenticates resolution
and deploy. Resolution needs no credential because `todomvc-maven` is public;
Maven only sends the `<server>` credentials when challenged.

A cold build in `maven:3.9-eclipse-temurin-21` with an empty local repository:

```console
$ docker run --rm -v "$PWD:/src" -v "$PWD/.m2-empty:/root/.m2" -w /src maven:3.9-eclipse-temurin-21 \
    mvn -B -q -s .mvn/settings.xml verify -DskipTests
$ ls target/*.jar
target/todo-api-0.1.0.jar
$ grep -rhoE '>[a-z0-9-]+=' .m2-empty/repository --include=_remote.repositories | sort | uniq -c
 473 >8gcr=
```

Every one of the 473 resolved files is recorded as coming from the `8gcr` mirror. The run took 2:56 including the image pull.

**Publish.** Release versions are immutable, so CI sets one per run:

```bash
mvn -B -s .mvn/settings.xml versions:set -DnewVersion=0.1.$RUN -DgenerateBackupPoms=false
mvn -B -s .mvn/settings.xml deploy -DskipTests
```

From the CI run that published 0.1.13:

```console
[INFO] Uploaded to 8gcr: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.1.13/todo-api-0.1.13.pom (2.1 kB at 247 B/s)
[INFO] Uploaded to 8gcr: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.1.13/todo-api-0.1.13.jar (54 MB at 3.9 MB/s)
[INFO] Uploaded to 8gcr: https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/maven-metadata.xml (344 B at 597 B/s)
[INFO] BUILD SUCCESS
```

Harbor generates `maven-metadata.xml` from what it holds, and serves checksums
it computes itself:

```console
$ curl -s https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/maven-metadata.xml
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
$ U=https://demo.container-registry.com/maven/todomvc-maven/com/containerregistry/todo/todo-api/0.1.13/todo-api-0.1.13.pom
$ curl -s $U.sha1; echo; curl -s $U | shasum -a 1
97a15e43e50f56af712ddc3e9178fd30d7c32af8
97a15e43e50f56af712ddc3e9178fd30d7c32af8  -
```

The pipeline's `verify` job reads the jar back with a cold local repository
(`mvn dependency:get -Dmaven.repo.local=$(mktemp -d)`), see [04](04-ci-keyless.md).

## npm

[`apps/todo-ui/.npmrc`](../apps/todo-ui/.npmrc):

```ini
registry=https://demo.container-registry.com/npm/todomvc-npm/
```

The lockfile keeps `resolved` URLs on `registry.npmjs.org`; npm rewrites those
to the configured registry. From a clean cache:

```console
$ rm -rf node_modules && npm cache clean --force
$ npm ci --no-audit --no-fund
added 36 packages in 4s
$ grep -c 'http fetch GET 200 https://demo.container-registry.com/npm/todomvc-npm' ~/.npm/_logs/<latest>-debug-0.log
36
$ grep -c 'registry.npmjs.org' ~/.npm/_logs/<latest>-debug-0.log
0
```

**Authenticate for publishing.** Harbor reads HTTP Basic from `_auth`;
`_authToken` (Bearer) is not accepted. CI appends:

```bash
auth="$(printf 'jwt:%s' "$TOKEN" | base64 | tr -d '\n')"
echo "//demo.container-registry.com/npm/todomvc-npm/:_auth=$auth" >> .npmrc
```

**Publish.** Run `npm run build` first: `files` in `package.json` is `["dist",
"README.md"]` and `dist` is not in git, so a publish without it ships an empty
package at a version you cannot reuse.

```bash
npm run build
npm version 0.1.$RUN --no-git-tag-version
npm publish
```

Read back with a fresh cache:

```console
$ npm view todomvc-todo-ui versions --json --cache "$(mktemp -d)"
[
  "0.1.12",
  "0.1.13"
]
$ npm view todomvc-todo-ui@0.1.13 dist.tarball
https://demo.container-registry.com/npm/todomvc-npm/todomvc-todo-ui/-/todomvc-todo-ui-0.1.13.tgz
```

The tarball URL names the registry, not npmjs.org. A republish of an existing
version with different content is refused:

```console
$ npm publish        # version 0.1.13 again, changed package.json
npm error code E409
npm error 409 Conflict - PUT https://demo.container-registry.com/npm/todomvc-npm/todomvc-todo-ui - immutable: version 0.1.13 already exists with different payload
```

## The cache fills less than it serves

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
dropped fill only means the next request goes upstream again. Timings in
[04](04-ci-keyless.md#timings) reflect this.

## Next

[04: CI, images and chart, keyless](04-ci-keyless.md)
