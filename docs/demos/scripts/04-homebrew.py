#!/usr/bin/env python3
"""Demo: a machine that cannot reach Homebrew installs jq through Harbor.

Needs the client env file written by scripts/setup-homebrew.py (BREW_ENV,
default brew.env) and HARBOR_PASS for the Harbor-side view.
"""
import os
import subprocess
import sys
import time

C_PROMPT, C_CMD, C_DIM, C_OFF = "\033[1;32m", "\033[1;37m", "\033[2m", "\033[0m"
HOMEBREW_HOSTS = ["formulae.brew.sh", "ghcr.io", "pkg-containers.githubusercontent.com",
                  "github.com", "api.github.com", "raw.githubusercontent.com",
                  "objects.githubusercontent.com"]


def say(text):
    print(f"\n{C_DIM}# {text}{C_OFF}", flush=True)
    time.sleep(1)


def run(cmd):
    print(f"{C_PROMPT}${C_OFF} {C_CMD}{cmd}{C_OFF}", flush=True)
    time.sleep(0.6)
    subprocess.run(cmd, shell=True, executable="/bin/bash", check=False)


def main():
    env = os.environ
    env.setdefault("H", env.get("HARBOR_URL", "https://8gcr.container-registry.dev").rstrip("/"))
    env.setdefault("BREW_ENV", "brew.env")
    env.setdefault("IMG", "homebrew/ubuntu24.04:latest")
    env["BLOCKED"] = " ".join(f"--add-host {h}:127.0.0.1" for h in HOMEBREW_HOSTS)
    if not os.path.exists(env["BREW_ENV"]) or not env.get("HARBOR_PASS"):
        sys.exit("run scripts/setup-homebrew.py first and set HARBOR_PASS")

    say("An intranet machine: Homebrew's hosts resolve to nowhere, only Harbor is reachable.")
    run('for h in $BLOCKED; do [ "$h" = --add-host ] || echo "blocked: ${h%:*}"; done')
    run('docker run --rm --platform linux/amd64 $BLOCKED $IMG bash -c "for u in https://formulae.brew.sh https://ghcr.io $H; do curl -s -m5 -o /dev/null \\$u && echo reachable: \\$u || echo unreachable: \\$u; done"')

    say("The client gets five settings, all pointing at one Harbor project (robot secret masked here).")
    run('sed -E "s#//[^@]*@#//<robot>@#; s/(TOKEN=).*/\\1<robot>/" $BREW_ENV')

    say("brew install jq: formula metadata, manifests and bottles all come from Harbor.")
    run('docker run --rm --platform linux/amd64 $BLOCKED --env-file $BREW_ENV $IMG bash -c "brew install jq 2>&1 | grep -E \'Downloading|Pouring|🍺\'; jq --version"')

    say("Harbor side: cached bottles are artifacts, every pull is audited under the robot's name.")
    run('curl -su admin:$HARBOR_PASS "$H/api/v2.0/projects/brew-priv/repositories" | jq -r ".[] | [.name, .artifact_count, .pull_count] | @tsv"')
    run('curl -su admin:$HARBOR_PASS "$H/api/v2.0/auditlog-exts?page_size=4&q=resource%3D~brew-priv" | jq -r ".[] | [.op_time, .username, .operation, .resource] | @tsv"')


if __name__ == "__main__":
    main()
