# demo runner: pretty-print each command, then run it.
C_PROMPT=$'\033[1;32m'; C_CMD=$'\033[1;37m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
say() { printf '\n%s# %s%s\n' "$C_DIM" "$*" "$C_OFF"; sleep 1; }
run() { printf '%s$%s %s%s%s\n' "$C_PROMPT" "$C_OFF" "$C_CMD" "$*" "$C_OFF"; sleep 0.6; eval "$*"; }
