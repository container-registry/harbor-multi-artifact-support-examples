# OCI images: push and pull, base images through a multi-project

**Level:** artifact type · **Artifact types:** OCI images · **Keyless:** no (robot secret)

[← Example catalogue](../../README.md)

`example-images` is a private multi-project with the `dockerhub` proxy cache as
its rank-1 sub-project. One URL serves the images you push and, for anything it
does not hold itself, Docker Hub. See
[docs/concepts.md](../../docs/concepts.md#multi-project).

## Prerequisites

- 8gcr 2.16 with *Multi-Format Artifacts* enabled (multi-projects are part of it), admin credentials
- Docker, Python 3.10+

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

==> Docker Hub proxy and the multi-project in front of it
  ok endpoint dockerhub id=3 docker-hub -> https://hub.docker.com
  ok project dockerhub (proxy cache of dockerhub, public=false)
  ok example-images -> sub-project dockerhub rank 1

==> Robot that may push and pull
  ok robot robot$example-images id=9, secret rotated and written to .robot.env (mode 600)
    push and pull -> demo.container-registry.com/example-images/<image>
    Docker Hub    -> demo.container-registry.com/example-images/library/<image>

==> Done
```

## Run

The robot has a grant on `example-images` only. That is enough to pull Docker
Hub content through it: authorization is checked against the multi-project.

```console
$ set -a; . ./.robot.env; set +a
$ printf '%s' "$HARBOR_ROBOT_SECRET" | docker login "$HOST" -u "$HARBOR_ROBOT_USER" --password-stdin
Login Succeeded
$ docker build -q --build-arg BASE="$HOST/example-images/library" -t "$HOST/example-images/hello:1.0" sample
sha256:6a051d57fcd739883eea95493b571009d212cd5961e4f154652f41b976bc8fcd
$ docker push "$HOST/example-images/hello:1.0"
...
1.0: digest: sha256:6a051d57fcd739883eea95493b571009d212cd5961e4f154652f41b976bc8fcd size: 855
$ docker rmi "$HOST/example-images/hello:1.0"
$ docker pull "$HOST/example-images/hello:1.0"
Status: Downloaded newer image for demo.container-registry.com/example-images/hello:1.0
$ docker run --rm "$HOST/example-images/hello:1.0"
hello from example-images
```

Without the login the project is closed:

```console
$ docker logout "$HOST"
$ docker pull "$HOST/example-images/hello:1.0"
Error response from daemon: failed to resolve reference "demo.container-registry.com/example-images/hello:1.0": pull access denied, repository does not exist or may require authorization: authorization failed: no basic auth credentials
```

Two things to know about multi-projects in 2.16: `tags/list` shows only the
multi-project's own tags, not those of its sub-projects, and a miss asks every
proxy sub-project's upstream, so names you push are looked up on Docker Hub
once.

## Cleanup

Delete the project `example-images` and the robot `example-images` in the
portal, and `.robot.env` locally. `dockerhub` is shared with other examples.
