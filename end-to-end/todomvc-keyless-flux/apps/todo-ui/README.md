# @todomvc/todo-ui

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

The committed `.npmrc` resolves packages through the `npmjs` proxy project and
the `@todomvc` scope through the hosted `todomvc-npm` project on the demo; see
[docs/04-npm.md](../../docs/04-npm.md). The
lockfile's `resolved` URLs name `registry.npmjs.org`, and npm rewrites them to
the configured registry.

The API base URL comes from `VITE_API_BASE` at build time. Unset (`npm run dev`)
it is `http://localhost:8080`; the image sets it empty, so the bundle calls
`/api` on its own origin and nginx forwards that to `API_UPSTREAM`.
