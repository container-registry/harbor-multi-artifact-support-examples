# 3. npm

[← 2. Maven](03-maven.md) · [4. Images →](05-images.md)

`apps/todo-ui` installs every package through the read-only `npmjs` proxy and
publishes itself as `@todomvc/todo-ui` to the hosted `todomvc-npm` project.

## The client configuration

[`apps/todo-ui/.npmrc`](../apps/todo-ui/.npmrc):

```ini
registry=https://demo.container-registry.com/npm/npmjs/
@todomvc:registry=https://demo.container-registry.com/npm/todomvc-npm/
```

The package is scoped so that one file covers both directions: unscoped names
resolve from the proxy, and the `@todomvc` scope, including `npm publish`, goes
to the hosted project. A consumer of the package uses the same two lines.

The lockfile keeps `resolved` URLs on `registry.npmjs.org`; npm rewrites those
to the configured registry. From a clean cache:

```console
$ rm -rf node_modules && npm cache clean --force
$ npm ci --no-audit --no-fund
added 36 packages in 5s
$ grep -oE 'http fetch GET [0-9]+ https://[^/]+/npm/[^/]+/' ~/.npm/_logs/<latest>-debug-0.log | sort | uniq -c
  36 http fetch GET 200 https://demo.container-registry.com/npm/npmjs/
```

All 36 packages came through the proxy.

## Publish, keyless

Harbor reads HTTP Basic from `_auth`; `_authToken` (Bearer) is not accepted.
The credential is appended for the hosted project only:

```bash
echo "//demo.container-registry.com/npm/todomvc-npm/:_auth=$(printf 'jwt:%s' "$TOKEN" | base64 | tr -d '\n')" >> .npmrc
```

In CI `$TOKEN` is the GitHub OIDC token ([6. Pipeline](07-pipeline.md)). This
run used a ServiceAccount token from the kind cluster of
[7. Flux deploy](08-flux-deploy.md), mapped to a temporary robot with push on
`todomvc-npm`:

```console
$ npm run build
✓ built in 379ms
$ npm version 0.0.1-local --no-git-tag-version
$ npm publish --loglevel http
npm notice Publishing to https://demo.container-registry.com/npm/todomvc-npm/ with tag latest and default access
npm http fetch PUT 201 https://demo.container-registry.com/npm/todomvc-npm/@todomvc%2ftodo-ui 7146ms
+ @todomvc/todo-ui@0.0.1-local
```

Run `npm run build` first: `files` in `package.json` is `["dist", "README.md"]`
and `dist` is not in git, so a publish without it ships an empty package at a
version you cannot reuse. Published versions are immutable:

```console
$ npm publish        # 0.0.1-local again, different package.json
npm error code E409
npm error 409 Conflict - PUT https://demo.container-registry.com/npm/todomvc-npm/@todomvc%2ftodo-ui - immutable: version 0.0.1-local already exists with different payload
```

## Resolve it back

A new project with only the committed `.npmrc` and no credential (both projects
are public):

```console
$ npm init -y && npm install @todomvc/todo-ui@0.0.1-local vue@3 --loglevel http
npm http fetch GET 200 https://demo.container-registry.com/npm/todomvc-npm/@todomvc%2ftodo-ui 76ms (cache miss)
npm http fetch GET 200 https://demo.container-registry.com/npm/npmjs/vue 565ms (cache miss)
npm http fetch GET 200 https://demo.container-registry.com/npm/npmjs/vue/-/vue-3.5.45.tgz 1232ms (cache miss)
npm http fetch GET 200 https://demo.container-registry.com/npm/todomvc-npm/@todomvc%2ftodo-ui/-/todo-ui-0.0.1-local.tgz 1468ms (cache miss)
added 26 packages in 8s
$ ls node_modules/@todomvc/todo-ui/dist
assets
index.html
```

The scoped package came from the hosted project, `vue` from the proxy.

## Next

[4. Images](05-images.md)
