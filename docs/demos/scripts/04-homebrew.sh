#!/bin/bash
source "$(dirname "$0")/runner.sh"
H=http://localhost:8080; A="-su admin:Harbor12345"

say "Homebrew: formula metadata AND bottles through one proxy project."
run 'curl '"$A"' -X POST -H "Content-Type: application/json" '"$H"'/api/v2.0/registries -d "{\"name\":\"brew-sh\",\"type\":\"homebrew\",\"url\":\"https://formulae.brew.sh/api\"}" -w "endpoint: %{http_code}\n"'
run 'RID=$(curl '"$A"' "'"$H"'/api/v2.0/registries?q=name%3Dbrew-sh" | jq ".[0].id"); curl '"$A"' -X POST -H "Content-Type: application/json" '"$H"'/api/v2.0/projects -d "{\"project_name\":\"brew-demo\",\"registry_id\":$RID,\"metadata\":{\"public\":\"true\"}}" -w "project: %{http_code}\n"'

say "Formula metadata comes from formulae.brew.sh via the /api path."
run 'curl '"$A"' '"$H"'/homebrew/brew-demo/api/formula/jq.json | jq "{name: .name, version: .versions.stable}"'

say "brew asks for the version manifest, then the platform bottle it names."
run 'curl '"$A"' -H "Accept: application/vnd.oci.image.index.v1+json" '"$H"'/homebrew/brew-demo/v2/homebrew/core/jq/manifests/1.8.1 -o /tmp/jq-idx.json -w "manifest: %{http_code}\n"'
run 'DG=$(jq -r ".manifests[].annotations | select(.\"org.opencontainers.image.ref.name\" | endswith(\"x86_64_linux\")) | .\"sh.brew.bottle.digest\"" /tmp/jq-idx.json); echo "bottle digest: $DG"'

say "Cold pull round-trips to ghcr.io; the warm pull serves from Harbor."
run 'curl '"$A"' -o /tmp/jq1.tgz -w "cold: %{http_code} %{size_download} bytes %{time_total}s\n" '"$H"'/homebrew/brew-demo/v2/homebrew/core/jq/blobs/sha256:$DG'
run 'curl '"$A"' -o /tmp/jq2.tgz -w "warm: %{http_code} %{size_download} bytes %{time_total}s\n" '"$H"'/homebrew/brew-demo/v2/homebrew/core/jq/blobs/sha256:$DG'
run 'cmp /tmp/jq1.tgz /tmp/jq2.tgz && sha256sum /tmp/jq2.tgz | cut -c1-20'

say "The cached bottle is a real artifact: repository, quota, audit log."
run 'sleep 3; curl '"$A"' "'"$H"'/api/v2.0/projects/brew-demo/repositories" | jq -r ".[] | [.name, (.pull_count|tostring)] | @tsv"'
run 'curl '"$A"' "'"$H"'/api/v2.0/auditlog-exts?page_size=3" | jq -r ".[] | [.op_time, .operation, .resource] | @tsv"'
