#!/bin/bash
source "$(dirname "$0")/runner.sh"
cd "$(git rev-parse --show-toplevel)"/apps/todo-api
export HARBOR_USERNAME=admin HARBOR_PASSWORD=Harbor12345

say "The Maven project mirrors everything: one URL for reads and writes."
run 'cp .mvn/settings-local.xml.example .mvn/settings-local.xml'

say "A GAV nobody asked for yet - pulled through from Maven Central, cached, checksummed."
run 'curl -su admin:Harbor12345 -o /dev/null -w "junit-4.13.2.jar: %{http_code} %{size_download} bytes %{time_total}s\n" http://localhost:8080/maven/todomvc-maven/junit/junit/4.13.2/junit-4.13.2.jar'
run 'curl -su admin:Harbor12345 http://localhost:8080/maven/todomvc-maven/junit/junit/4.13.2/junit-4.13.2.jar.sha1; echo " <- sha1"'

say "Full build + tests with an EMPTY local repository: every dependency and plugin resolves through Harbor."
run 'mvn -B -q -s .mvn/settings-local.xml -Dmaven.repo.local=$(mktemp -d) verify && echo BUILD SUCCESS'

say "Deploy a release version into the same project."
run 'V=0.1.$(date +%Y%m%d%H%M%S); mvn -B -q -s .mvn/settings-local.xml versions:set -DnewVersion=$V -DgenerateBackupPoms=false'
run 'mvn -B -q -s .mvn/settings-local.xml deploy -DskipTests -Dharbor.url=http://localhost:8080 && echo DEPLOYED $V'
run 'git restore pom.xml'

say "Cold pull-back, mirror-less on purpose."
run 'mvn -B -q -s .mvn/settings-upstream.xml -Dmaven.repo.local=$(mktemp -d) dependency:get -DremoteRepositories="8gcr::::http://admin:Harbor12345@localhost:8080/maven/todomvc-maven" -Dartifact=com.containerregistry.todo:todo-api:$V && echo PULLED BACK $V'
