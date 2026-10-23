#!/usr/bin/env bash
# Usage:
#   run.sh [command...]                  Pi (or a command) on the current folder
#   run.sh --clone OWNER/REPO [command...]  same, on a clone kept in a container volume
#   run.sh check [OWNER/REPO]            verify both keys; spends no OpenRouter credits
set -euo pipefail

env_file="${PI_ENV_FILE:-$HOME/.config/pi-container/env}"
[ -f "$env_file" ] || { echo "run.sh: missing $env_file (see README)" >&2; exit 1; }

args=(run --rm -i --init --env-file "$env_file"
  --cpus "${PI_CPUS:-4}" --memory "${PI_MEMORY:-4G}"
  -e TERM=xterm-256color -v pi-agent-home:/root/.pi/agent)
if [ -t 0 ] && [ -t 1 ]; then args+=(-t); fi

clone=""
if [ "${1:-}" = --clone ]; then
  clone="${2:?--clone needs OWNER/REPO}"; shift 2
  [[ "$clone" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "run.sh: bad repo '$clone'" >&2; exit 2; }
fi
[ $# -gt 0 ] || set -- pi

if [ "$1" = check ]; then
  read -r -d '' script <<'EOF' || true
s=0
echo "== OpenRouter"
if r=$(curl -fsS -m 20 -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/key); then
  printf '%s\n' "$r" | jq '.data | {label: .label, limit: .limit, remaining: .limit_remaining, usage: .usage}'
else
  echo "FAIL: key rejected"; s=1
fi
echo "== GitHub"
gh auth status || s=1
[ -z "$1" ] || git ls-remote "https://github.com/$1.git" HEAD || s=1
exit $s
EOF
  set -- bash -c "$script" check "${2:-$clone}"
  args+=(-w /tmp)
elif [ -n "$clone" ]; then
  read -r -d '' boot <<'EOF' || true
d="/work/${PI_CLONE#*/}"
[ -d "$d/.git" ] || git clone "https://github.com/$PI_CLONE.git" "$d" || exit 1
cd "$d" && exec "$@"
EOF
  vol="pi-clone-$(printf '%s' "$clone" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-')"
  args+=(-v "$vol:/work" -w /work -e "PI_CLONE=$clone")
  set -- bash -c "$boot" boot "$@"
else
  if [ "$PWD" = "$HOME" ] || [ "$PWD" = / ]; then
    echo "run.sh: refusing to mount $PWD; cd into a project first" >&2; exit 1
  fi
  args+=(-v "$PWD:$PWD" -w "$PWD")
fi

exec "${CONTAINER_CLI:-container}" "${args[@]}" "${PI_IMAGE:-pi-agent:local}" "$@"
