# todomvc-todo-ui

Vue 3 TodoMVC frontend, adapted from the [official TodoMVC Vue example](https://github.com/tastejs/todomvc/tree/master/examples/vue).
`localStorage` persistence is replaced by a REST backend, and `vue-router` by a
plain `hashchange` listener.

It exists as demo scaffolding for the Harbor multi-artifact examples: it consumes
npm packages through a Harbor proxy-cache project and is itself published as an
npm package to a Harbor hosted npm registry.

## API contract

Base URL comes from `VITE_API_BASE` (build time), default `http://localhost:8080`.

| Method   | Path                          | Body                            | Response      |
| -------- | ----------------------------- | ------------------------------- | ------------- |
| `GET`    | `/api/todos`                  |                                 | `Todo[]`      |
| `POST`   | `/api/todos`                  | `{"title": "..."}`              | `Todo`        |
| `PATCH`  | `/api/todos/{id}`             | `{"title"?, "completed"?}`      | `Todo`        |
| `DELETE` | `/api/todos/{id}`             |                                 | `204`         |
| `DELETE` | `/api/todos?completed=true`   |                                 | `204`         |

`Todo` is `{"id": 1, "title": "buy milk", "completed": false}`.
All calls live in `src/api.js`.

## Develop

```sh
npm install
npm run dev      # http://localhost:5173
npm run build    # -> dist/
npm run preview
```

## Registry

The committed `.npmrc` resolves dependencies through Harbor:

```
registry=https://8gcr.container-registry.dev/npm/todomvc-npm/
always-auth=true
```

CI injects credentials as `//8gcr.container-registry.dev/npm/todomvc-npm/:_auth=<base64 user:pass>`.
Harbor accepts Basic `_auth` only, **not** `_authToken`.

`package-lock.json` was generated against npmjs.org, so its `resolved` fields name
`registry.npmjs.org`. That is fine: npm rewrites the host of a default-registry
`resolved` URL to whatever registry is configured, so `npm ci` under this `.npmrc`
still fetches every tarball through Harbor (verified by pointing `npm ci` at an
unreachable registry: it requested every tarball from that host, not from npmjs.org).

While the Harbor npm endpoint is unavailable, install straight from upstream:

```sh
npm install --registry=https://registry.npmjs.org
```

`.npmrc.example` holds the same Harbor configuration for reference.

## Container

```sh
docker build --build-arg VITE_API_BASE=http://localhost:8080 -t todomvc-todo-ui .
docker run --rm -p 8081:80 todomvc-todo-ui
```

nginx serves `dist/` and falls back to `index.html` for unknown paths.
