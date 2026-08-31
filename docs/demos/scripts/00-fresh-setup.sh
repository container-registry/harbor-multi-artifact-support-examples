#!/bin/bash
source "$(dirname "$0")/runner.sh"
cd "${HARBOR_SRC:?path to your harbor checkout}"

say "A fresh Harbor Next dev instance: backend containers with hot reload."
run 'export DEV_CONTAINER_USER=root COMPOSE_PROJECT_NAME=harbor-0 HOST_GOMODCACHE=$(go env GOMODCACHE) HOST_GOCACHE=$(go env GOCACHE)'
run 'docker compose -f devenv/docker-compose.yml --env-file versions.env --profile core --profile jobservice --profile registryctl up -d --build 2>&1 | tail -8'

say "Wait for core to answer (first boot compiles Harbor inside the container)."
run 'until curl -sf -o /dev/null http://localhost:8080/api/v2.0/ping; do sleep 5; printf .; done; echo " core is up"'

say "Multi-format endpoints sit behind a commercial feature gate - enable once."
run 'curl -su admin:Harbor12345 -X PUT -H "Content-Type: application/json" http://localhost:8080/api/v2.0/configurations -d "{\"enable_commercial_multi_format_artifacts\": true}" -w "%{http_code}\n"'

say "Provision registry endpoints and projects with the repo script."
cd "$(git rev-parse --show-toplevel)"
run 'HARBOR_URL=http://localhost:8080 HARBOR_PASS=Harbor12345 SKIP_WIF=1 ./scripts/setup-8gcr.sh 2>&1 | tail -15'

say "What we have now:"
run 'curl -su admin:Harbor12345 "http://localhost:8080/api/v2.0/projects?page_size=20" | jq -r ".[] | [.name, (.registry_id // 0 | tostring)] | @tsv"'
