# 5. Helm chart

[← 4. Images](05-images.md) · [6. Pipeline →](07-pipeline.md)

[`chart/todomvc`](../chart/todomvc) deploys both images: the API
and the UI, whose nginx forwards `/api` to the API service, so the browser
needs only the UI. Pods run as the ServiceAccount `todomvc`, whose token is
what pulls the images in [7. Flux deploy](08-flux-deploy.md).

## Version and appVersion

CI packages the chart with the run's version and the commit as `appVersion`.
The image tag defaults to `appVersion`, so a chart always deploys the images
built from the same commit:

```bash
VERSION=0.1.13      # CI: 0.1.<run_number>, see 6. Pipeline
helm package chart/todomvc --version "$VERSION" --app-version "$GITHUB_SHA"
```

The committed `appVersion` is `unset`, and rendering without a tag fails
instead of producing an image reference that does not exist:

```console
$ helm template t chart/todomvc
Error: execution error at (todomvc/templates/ui.yaml:18:20): no image tag: set image.tag, or package the chart with --app-version <commit>
```

## Push as OCI

The chart goes into the same multi-project as the images:

```bash
printf '%s' "$TOKEN" | helm registry login $HOST -u jwt --password-stdin
helm push "todomvc-$VERSION.tgz" "oci://$HOST/todomvc/charts"
```

```console
Pushed: demo.container-registry.com/todomvc/charts/todomvc:0.1.13
```

Because the chart is the multi-project's own content, `tags/list` returns its
versions and Flux can follow a `semver` range. Content that only a sub-project
holds is not listed ([Concepts](01-concepts.md#oci-one-multi-project)).

## Next

[6. Pipeline](07-pipeline.md)
