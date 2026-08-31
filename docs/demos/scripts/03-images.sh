#!/bin/bash
source "$(dirname "$0")/runner.sh"
cd "$(git rev-parse --show-toplevel)"

say "Container images land in the todomvc project - plain OCI, same registry."
run 'podman build -q -t localhost:8080/todomvc/todo-ui:demo apps/todo-ui'
run 'podman login -u admin -p Harbor12345 --tls-verify=false localhost:8080'
run 'podman push --tls-verify=false localhost:8080/todomvc/todo-ui:demo 2>&1 | tail -2'

say "Round-trip: forget the local copy, pull it back from Harbor."
run 'podman rmi localhost:8080/todomvc/todo-ui:demo >/dev/null && podman pull --tls-verify=false localhost:8080/todomvc/todo-ui:demo 2>&1 | tail -1'
