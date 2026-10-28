#!/usr/bin/env python3
"""Demo: bring up a fresh Harbor Next dev instance and provision it.

Needs HARBOR_SRC, a harbor checkout that holds devenv/docker-compose.yml.
"""
import os
import subprocess
import sys
import time

C_PROMPT, C_CMD, C_DIM, C_OFF = "\033[1;32m", "\033[1;37m", "\033[2m", "\033[0m"
REPO = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                      cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()


def say(text):
    print(f"\n{C_DIM}# {text}{C_OFF}", flush=True)
    time.sleep(1)


def run(cmd, cwd):
    print(f"{C_PROMPT}${C_OFF} {C_CMD}{cmd}{C_OFF}", flush=True)
    time.sleep(0.6)
    rc = subprocess.run("set -o pipefail; " + cmd, shell=True, executable="/bin/bash", cwd=cwd).returncode
    if rc:
        sys.exit(f"demo step failed with exit code {rc}")


def main():
    src = os.environ.get("HARBOR_SRC") or sys.exit("set HARBOR_SRC to your harbor checkout")
    env = os.environ
    env.update(DEV_CONTAINER_USER="root", COMPOSE_PROJECT_NAME="harbor-0")
    for key, arg in (("HOST_GOMODCACHE", "GOMODCACHE"), ("HOST_GOCACHE", "GOCACHE")):
        env[key] = subprocess.run(["go", "env", arg], capture_output=True, text=True).stdout.strip()

    say("A fresh Harbor Next dev instance: backend containers with hot reload.")
    run("docker compose -f devenv/docker-compose.yml --env-file versions.env --profile core "
        "--profile jobservice --profile registryctl up -d --build 2>&1 | tail -8", src)

    say("Wait for core to answer (first boot compiles Harbor inside the container).")
    run('until curl -sf -o /dev/null http://localhost:8080/api/v2.0/ping; do sleep 5; printf .; done; '
        'echo " core is up"', src)

    say("Multi-format endpoints sit behind a commercial feature gate - enable once.")
    run('curl -su admin:Harbor12345 -X PUT -H "Content-Type: application/json" '
        'http://localhost:8080/api/v2.0/configurations '
        '-d "{\\"enable_commercial_multi_format_artifacts\\": true}" -w "%{http_code}\\n"', src)

    say("Provision registry endpoints and projects with the repo script.")
    run("HARBOR_URL=http://localhost:8080 HARBOR_PASS=Harbor12345 ./scripts/setup-8gcr.py --skip-wif "
        "2>&1 | tail -15", REPO)

    say("What we have now:")
    run('curl -su admin:Harbor12345 "http://localhost:8080/api/v2.0/projects?page_size=20" '
        '| jq -r ".[] | [.name, (.registry_id // 0 | tostring)] | @tsv"', REPO)


if __name__ == "__main__":
    main()
