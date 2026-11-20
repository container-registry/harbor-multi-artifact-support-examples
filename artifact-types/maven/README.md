# Maven: deploy to a hosted project, resolve through a proxy

**Level:** artifact type · **Artifact types:** Maven · **Keyless:** no (robot secret)

[← Example catalogue](../../README.md)

Two projects with one job each: `maven-central`, a read-only proxy cache of
Maven Central, and `example-maven`, a hosted project for your own artifacts.
See [docs/concepts.md](../../docs/concepts.md) for why the two are separate.

## Prerequisites

- 8gcr / Harbor Next 2.16 with *Multi-Format Artifacts* enabled, admin credentials
- Maven 3.9 with a JDK 17+, or Docker (the commands below ran in `maven:3.9-eclipse-temurin-21`), Python 3.10+
- On 8gcr builds newer than v2.16.0, package paths are `/pkg/maven/` instead of `/maven/`.

## Setup

```console
$ export HARBOR_URL=https://harbor.example.com HARBOR_PASS=...
$ ./setup.py
==> Target: https://demo.container-registry.com
  ok authenticated

==> Proxy and hosted project
  ok endpoint maven-central id=2 maven -> https://repo1.maven.org/maven2
  ok project maven-central (proxy cache of maven-central, public=true)
  ok project example-maven (hosted, public)

==> Robot that may publish to the hosted project
  ok robot robot$example-maven id=8, secret rotated and written to .robot.env (mode 600)
    resolve -> https://demo.container-registry.com/maven/maven-central
    publish -> https://demo.container-registry.com/maven/example-maven

==> Done
```

The sample's [`.mvn/settings.xml`](sample/.mvn/settings.xml) mirrors everything
to the proxy (`mirrorOf *,!example-hosted`) and reads the deploy credentials
from `HARBOR_ROBOT_USER` and `HARBOR_ROBOT_SECRET`;
[`pom.xml`](sample/pom.xml) deploys to `example-maven` under the id
`example-hosted`. `mirrorOf *` rather than `central` also catches repositories
that third-party POMs declare. The hosted project is deliberately not a
resolution source: a build that does not consume your own artifacts would ask
it first for every dependency and get a 404 each time.

## Run

Deploy, from `sample/`, with a cold local repository. Release versions are
immutable, so each run sets a new one:

```console
$ set -a; . ../.robot.env; set +a
$ mvn -B -q -s .mvn/settings.xml versions:set -DnewVersion="0.1.$(date +%Y%m%d%H%M%S)" -DgenerateBackupPoms=false
$ mvn -B -s .mvn/settings.xml deploy
...
[INFO] Uploaded to example-hosted: https://demo.container-registry.com/maven/example-maven/com/example/hello/0.1.20261120152606/hello-0.1.20261120152606.pom (880 B at 99 B/s)
[INFO] Uploaded to example-hosted: https://demo.container-registry.com/maven/example-maven/com/example/hello/0.1.20261120152606/hello-0.1.20261120152606.jar (2.4 kB at 244 B/s)
[INFO] Uploaded to example-hosted: https://demo.container-registry.com/maven/example-maven/com/example/hello/maven-metadata.xml (362 B at 3.9 kB/s)
[INFO] BUILD SUCCESS
[INFO] Total time:  43.567 s
$ grep -rhoE '>[a-z0-9-]+=' ~/.m2/repository --include=_remote.repositories | sort | uniq -c
 321 >example-proxy=
```

All 321 files the build needed, plugins included, came through the proxy.

Read it back with an empty local repository, naming the hosted project
explicitly (both projects are public, no credential needed):

```console
$ mvn -B -s .mvn/settings.xml dependency:get -Dtransitive=false \
    -DremoteRepositories=example-hosted::default::https://demo.container-registry.com/maven/example-maven \
    -Dartifact=com.example:hello:0.1.20261120152606
[INFO] Downloaded from example-hosted: https://demo.container-registry.com/maven/example-maven/com/example/hello/0.1.20261120152606/hello-0.1.20261120152606.pom (880 B at 1.6 kB/s)
[INFO] Downloaded from example-hosted: https://demo.container-registry.com/maven/example-maven/com/example/hello/0.1.20261120152606/hello-0.1.20261120152606.jar (2.4 kB at 4.6 kB/s)
[INFO] BUILD SUCCESS
```

A project that depends on your artifacts adds the hosted project as a
`<repository>` with the same id instead.

## Cleanup

Delete the project `example-maven` and the robot `example-maven` in the portal,
and `.robot.env` locally. `maven-central` is shared with other examples.
