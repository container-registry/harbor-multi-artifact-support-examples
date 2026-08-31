#!/bin/bash
source "$(dirname "$0")/runner.sh"
cd "$(git rev-parse --show-toplevel)/apps/todo-ui"
H=http://localhost:8080; REG=$H/npm/todomvc-npm/

say "One npm registry URL: resolves upstream packages through the proxy AND hosts our own."
run 'auth=$(printf "admin:Harbor12345" | base64 | tr -d "\n"); printf "//localhost:8080/npm/todomvc-npm/:_auth=%s\n" "$auth" > /tmp/harbor-npmrc'

say "The packument comes from upstream - full version list, even on a cold cache."
run 'curl -su admin:Harbor12345 $H/npm/todomvc-npm/lodash | jq "{versions: (.versions|length), latest: .\"dist-tags\".latest}"'

say "Exact pins of never-cached versions pull through."
run 'npm install lodash@4.17.21 --userconfig /tmp/harbor-npmrc --registry=$REG --cache $(mktemp -d) --prefix $(mktemp -d) 2>&1 | tail -1'

say "Install the app dependencies through the proxy, then build."
run 'rm -rf node_modules && npm ci --userconfig /tmp/harbor-npmrc --registry=$REG --cache $(mktemp -d) 2>&1 | tail -1'
run 'npm run build 2>&1 | tail -3'

say "Publish our own package into the same project."
run 'V=0.1.$(date +%Y%m%d%H%M%S); npm version $V --no-git-tag-version'
run 'npm publish --userconfig /tmp/harbor-npmrc --registry=$REG 2>&1 | tail -1'

say "Prove it: cold pull-back of the version we just published."
run 'npm pack todomvc-todo-ui@$V --userconfig /tmp/harbor-npmrc --registry=$REG --cache $(mktemp -d) --pack-destination $(mktemp -d) 2>&1 | tail -1'
run 'git restore package.json package-lock.json'
