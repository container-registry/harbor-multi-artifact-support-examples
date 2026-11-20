# Helm: push and pull charts as OCI artifacts

**Level:** artifact type · **Artifact types:** Helm chart · **Keyless:** no (robot secret)

[← Example catalogue](../../README.md)

A Helm chart is an OCI artifact, so it goes into an ordinary hosted project:
`example-helm`, private. Helm 3.8+ talks to it with `helm registry login`,
`helm push` and `oci://` references.

## Prerequisites

- 8gcr 2.16, admin credentials
- Helm 3.8+ (ran with v4.3.1), Python 3.10+

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

==> Hosted project
  ok project example-helm (hosted, private)

==> Robot that may push and pull
  ok robot robot$example-helm id=10, secret rotated and written to .robot.env (mode 600)
    charts -> oci://demo.container-registry.com/example-helm

==> Done
```

## Run

```console
$ set -a; . ./.robot.env; set +a
$ OUT="$(mktemp -d)"
$ helm package sample -d "$OUT"
Successfully packaged chart and saved it to: /tmp/.../hello-0.1.0.tgz
$ printf '%s' "$HARBOR_ROBOT_SECRET" | helm registry login "$HOST" -u "$HARBOR_ROBOT_USER" --password-stdin
Login Succeeded
$ helm push "$OUT/hello-0.1.0.tgz" "oci://$HOST/example-helm"
Pushed: demo.container-registry.com/example-helm/hello:0.1.0
Digest: sha256:9d3c9810c520fab0e76c6f752d9cbfcd98cb343214bfc6e2020721d704097863
$ helm template t "oci://$HOST/example-helm/hello" --version 0.1.0
apiVersion: v1
kind: ConfigMap
metadata:
  name: t-hello
data:
  greeting: "hello from example-helm"
```

`helm install` and Flux's `OCIRepository` use the same `oci://` reference. After
`helm registry logout`, the private project refuses the pull:

```console
$ helm show chart "oci://$HOST/example-helm/hello" --version 0.1.0
Error: failed to perform "FetchReference" on source: GET "https://demo.container-registry.com/v2/example-helm/hello/manifests/0.1.0": response status code 401: unauthorized: unauthorized to access repository: example-helm/hello, action: pull
```

The chart version is the tag. Pushing a changed chart as `0.1.0` again
replaced the tag (no immutability rule on the project); bump `version` in
`Chart.yaml` for every release.

For keyless chart delivery to a cluster, see the
[end-to-end example](../../end-to-end/todomvc-keyless-flux/docs/06-helm-chart.md).

## Cleanup

Delete the project `example-helm` and the robot `example-helm` in the portal,
and `.robot.env` locally.
