# Helm: push and pull charts as OCI artifacts

**Level:** artifact type · **Artifact types:** Helm chart · **Keyless:** no (robot secret)

[← Example catalogue](../../README.md)

A Helm chart is an OCI artifact, so it goes into an ordinary hosted project:
`example-helm`, private. Helm 3.8+ talks to it with `helm registry login`,
`helm push` and `oci://` references.

## Prerequisites

- 8gcr / Harbor Next 2.16, admin credentials
- Helm 3.8+ (ran with v4.3.1), Python 3.10+

## Setup

```console
$ export HARBOR_URL=https://harbor.example.com HARBOR_PASS=...
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
$ helm package sample -d "$(mktemp -d)"
Successfully packaged chart and saved it to: /tmp/.../hello-0.1.0.tgz
$ printf '%s' "$HARBOR_ROBOT_SECRET" | helm registry login demo.container-registry.com -u "$HARBOR_ROBOT_USER" --password-stdin
Login Succeeded
$ helm push /tmp/.../hello-0.1.0.tgz oci://demo.container-registry.com/example-helm
Pushed: demo.container-registry.com/example-helm/hello:0.1.0
Digest: sha256:d13bb6a9a6b3f2ab1d75fdef1ca50563c0b41d34e721db0dde4e7f4f937c849f
$ helm template t oci://demo.container-registry.com/example-helm/hello --version 0.1.0
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
$ helm show chart oci://demo.container-registry.com/example-helm/hello --version 0.1.0
Error: failed to perform "FetchReference" on source: GET "https://demo.container-registry.com/v2/example-helm/hello/manifests/0.1.0": response status code 401: unauthorized: unauthorized to access repository: example-helm/hello, action: pull
```

The chart version is the tag. Pushing the same version again with a different
chart replaces the tag; bump `version` in `Chart.yaml` for every release.

For keyless chart delivery to a cluster, see the
[end-to-end example](../../end-to-end/todomvc-keyless-flux/docs/06-helm-chart.md).

## Cleanup

Delete the project `example-helm` and the robot `example-helm` in the portal,
and `.robot.env` locally.
