# Recorded demos

Every flow in this repository, recorded end to end with
[asciinema](https://asciinema.org/) against a **freshly wiped** local Harbor
Next dev instance (`localhost:8080`, state volumes deleted first — nothing
was cached, nothing pre-created except what each recording shows). The
scripts that produced them are in [`scripts/`](scripts/) and print every
command before running it, so each recording doubles as a copy-pasteable
walkthrough.

Formats per demo: an animated GIF (inline below), an `.mp4`, and the
original `.cast` (replay locally with `asciinema play <file>.cast`;
long pauses are capped at 2 s).

## 00 — Fresh setup

Backend containers up, wait for core, enable the multi-format feature gate,
provision endpoints and projects with `scripts/setup-8gcr.sh`.
[mp4](00-fresh-setup.mp4) · [cast](00-fresh-setup.cast) · [script](scripts/00-fresh-setup.sh)

![Fresh setup](00-fresh-setup.gif)

## 01 — npm

Upstream-complete packument on a cold cache, exact-pin install of a
never-cached version, `npm ci` + build through the proxy, publish our own
package, cold pull-back. See [03-npm.md](../03-npm.md).
[mp4](01-npm.mp4) · [cast](01-npm.cast) · [script](scripts/01-npm.sh)

![npm](01-npm.gif)

## 02 — Maven

Cold GAV pull-through with checksums, then the real test: `mvn verify` with
an **empty local repository** — every dependency and plugin resolves through
Harbor — followed by a release deploy and a mirror-less cold pull-back.
See [04-maven.md](../04-maven.md).
[mp4](02-maven.mp4) · [cast](02-maven.cast) · [script](scripts/02-maven.sh)

![Maven](02-maven.gif)

## 03 — Images

Build the todo-ui image, push it to the `todomvc` project, forget the local
copy, pull it back. See [05-images-wif.md](../05-images-wif.md).
[mp4](03-images.mp4) · [cast](03-images.cast) · [script](scripts/03-images.sh)

![Images](03-images.gif)

## 04 — Homebrew

An intranet client: every Homebrew host is blocked inside the container, only
Harbor is reachable. The real `brew install jq` pulls formula metadata,
manifests and bottles through the `brew-priv` proxy project as a pull-only
robot, then the Harbor side shows the cached repositories and the robot's
pulls in the audit log. Recorded against `https://8gcr.container-registry.dev`
on 2026-10-27, after `homebrew/setup-homebrew.py`. See [homebrew/README.md](../../homebrew/README.md).
[mp4](04-homebrew.mp4) · [cast](04-homebrew.cast) · [script](scripts/04-homebrew.py)

![Homebrew](04-homebrew.gif)

## Reproducing

```bash
# 00 needs a harbor checkout for the compose file:
HARBOR_SRC=~/code/harbor ./scripts/00-fresh-setup.sh
# the rest run from anywhere inside this repo:
./scripts/01-npm.sh
./scripts/02-maven.sh
./scripts/03-images.sh
HARBOR_PASS=... ../../homebrew/setup-homebrew.py --out brew.env
HARBOR_PASS=... BREW_ENV=brew.env ./scripts/04-homebrew.py
```

Recorded 2026-08-31 with `asciinema rec --headless --window-size 100x30 -i 2`,
rendered with `agg`, converted with `ffmpeg`.
