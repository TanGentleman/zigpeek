#!/usr/bin/env bash
# Run Pi inside Apple's container, on a host-only network.
#   run.sh                         Pi on the current folder
#   run.sh --clone OWNER/REPO      Pi on a clone kept in a volume
#   run.sh check [OWNER/REPO]      keys, GitHub, and the network lock
#   run.sh proxy                   follow the proxy container's logs
#   run.sh proxy-stop              stop the proxy container
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
env_file="${PI_ENV_FILE:-$HOME/.config/pi-container/env}"
cfg="${PI_CONFIG_DIR:-$HOME/.config/pi-container}"
port="${PI_PROXY_PORT:-8888}"
placeholder="sk-or-v1-placeholder"
cli="${CONTAINER_CLI:-container}"
proxy_name="pi-proxy"
proxy_image="${PI_PROXY_IMAGE:-pi-proxy:local}"

file_mode() {
  if stat -c %a "$1" >/dev/null 2>&1; then stat -c %a "$1"; else stat -f %Lp "$1"; fi
}

require_env() {
  [ -f "$env_file" ] || { echo "run.sh: missing $env_file (see README)" >&2; exit 1; }
  case $(file_mode "$env_file") in
    600|400) ;;
    *) echo "run.sh: $env_file must be mode 600 (chmod 600)" >&2; exit 1 ;;
  esac
  if ! grep -q '^OPENROUTER_API_KEY=.' "$env_file" || ! grep -q '^GITHUB_TOKEN=.' "$env_file"; then
    echo "run.sh: set OPENROUTER_API_KEY and GITHUB_TOKEN in $env_file" >&2
    exit 1
  fi
}

ensure_network() {
  names=$("$cli" network list -q) || { echo "run.sh: container network list failed" >&2; exit 1; }
  printf '%s\n' "$names" | grep -qx pi-locked && return
  "$cli" network create --internal pi-locked --subnet 172.30.240.0/24
}

# The proxy container gets the OpenRouter key and nothing else from the env file.
write_proxy_env() {
  mkdir -p "$cfg"
  old_umask=$(umask)
  umask 077
  tmp=$(mktemp "${cfg}/proxy.env.XXXXXX")
  umask "$old_umask"
  grep '^OPENROUTER_API_KEY=' "$env_file" | tail -n 1 > "$tmp" || true
  if ! grep -q '^OPENROUTER_API_KEY=.' "$tmp"; then
    rm -f "$tmp"
    echo "run.sh: OPENROUTER_API_KEY is empty" >&2
    exit 1
  fi
  if [ -f "$cfg/proxy.env" ] && cmp -s "$tmp" "$cfg/proxy.env"; then
    rm -f "$tmp"
  else
    mv "$tmp" "$cfg/proxy.env"
    chmod 600 "$cfg/proxy.env"
  fi
}

# Prints the proxy's state and its address on pi-locked, one per line.
# `container inspect` prints pretty JSON. An attachment object holds both
# "ipv4Address" and "network", in whichever order, so split on "}".
proxy_facts() {
  json=$("$cli" inspect "$proxy_name" 2>/dev/null) || { printf '\n\n'; return; }
  printf '%s\n' "$json" | awk '
    BEGIN { RS = "}" }
    /"state"[[:space:]]*:/ {
      s = $0
      sub(/.*"state"[[:space:]]*:[[:space:]]*"/, "", s)
      sub(/".*/, "", s)
      if (s ~ /^(running|stopped|stopping|unknown)$/) state = s
    }
    /"ipv4Address"/ && /"network"[[:space:]]*:[[:space:]]*"pi-locked"/ {
      ip = $0
      sub(/.*"ipv4Address"[[:space:]]*:[[:space:]]*"/, "", ip)
      sub(/".*/, "", ip)
      sub(/\/.*/, "", ip)
      if (ip ~ /^[0-9.]+$/) locked = ip
    }
    END { print state; print locked }
  '
}

ensure_proxy() {
  mkdir -p "$cfg/certs" "$cfg/private"
  chmod 700 "$cfg/private"
  write_proxy_env
  stamp="$cfg/proxy.stamp"
  image_stale=0
  env_stale=0
  if [ ! -f "$stamp" ] || [ "$here/proxy.py" -nt "$stamp" ] || [ "$here/Dockerfile.proxy" -nt "$stamp" ]; then
    image_stale=1
  fi
  if [ ! -f "$stamp" ] || [ "$cfg/proxy.env" -nt "$stamp" ]; then
    env_stale=1
  fi
  if ! "$cli" image inspect "$proxy_image" >/dev/null 2>&1; then
    image_stale=1
  fi
  if [ "$image_stale" = 1 ] || [ "$env_stale" = 1 ]; then
    "$cli" delete --force "$proxy_name" >/dev/null 2>&1 || true
    if [ "$image_stale" = 1 ]; then
      "$cli" build -t "$proxy_image" -f "$here/Dockerfile.proxy" "$here"
    fi
    touch "$stamp"
  fi
  facts=$(proxy_facts || true)
  state=$(printf '%s\n' "$facts" | sed -n '1p')
  if [ "$state" = running ]; then
    return
  fi
  if [ "$state" = stopped ] || [ "$state" = stopping ]; then
    "$cli" start "$proxy_name"
    return
  fi
  "$cli" run -d --name "$proxy_name" \
    --cpus 1 --memory 1G \
    --network default --network pi-locked \
    --env-file "$cfg/proxy.env" \
    -v "$cfg/private:/private" -v "$cfg/certs:/certs" \
    "$proxy_image" >/dev/null
}

proxy_ip() {
  i=0
  while [ "$i" -lt 90 ]; do
    facts=$(proxy_facts || true)
    ip=$(printf '%s\n' "$facts" | sed -n '2p')
    if [ -n "$ip" ] && curl -fsS -m 2 "http://${ip}:${port}/health" 2>/dev/null | grep -qx pi-container-proxy; then
      printf '%s\n' "$ip"
      return
    fi
    i=$((i + 1))
    sleep 0.5
  done
  echo "run.sh: the proxy container did not come up. Run: $cli logs $proxy_name" >&2
  exit 1
}

if [ "${1:-}" = proxy-stop ]; then
  "$cli" stop "$proxy_name" >/dev/null 2>&1 || true
  exit 0
fi

require_env
if [ "${PI_SKIP_HOST_SETUP:-}" = 1 ]; then
  proxy_ip_value="172.30.240.2"
else
  ensure_network
  ensure_proxy
  if [ "${1:-}" = proxy ]; then
    exec "$cli" logs -f "$proxy_name"
  fi
  proxy_ip_value=$(proxy_ip)
fi
proxy_url="http://${proxy_ip_value}:${port}"

args=(run --rm -i --init --network pi-locked
  --env-file "$env_file"
  --cpus "${PI_CPUS:-4}" --memory "${PI_MEMORY:-4G}"
  -e TERM=xterm-256color
  -e "OPENROUTER_API_KEY=${placeholder}"
  -e PI_TELEMETRY=0 -e GH_TELEMETRY=0
  -e "HTTP_PROXY=${proxy_url}" -e "HTTPS_PROXY=${proxy_url}"
  -e "http_proxy=${proxy_url}" -e "https_proxy=${proxy_url}"
  -e NO_PROXY= -e no_proxy=
  -e NODE_EXTRA_CA_CERTS=/etc/pi-proxy-ca/ca.pem
  -v "$cfg/certs:/etc/pi-proxy-ca:ro"
  -v pi-agent-home:/root/.pi/agent)
if [ -t 0 ] && [ -t 1 ]; then args+=(-t); fi

clone=""
if [ "${1:-}" = --clone ]; then
  clone="${2:?--clone needs OWNER/REPO}"; shift 2
  [[ "$clone" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "run.sh: bad repo '$clone'" >&2; exit 2; }
fi
[ $# -gt 0 ] || set -- pi

read -r -d '' prep <<'EOF' || true
git config --global http.proxy "$HTTPS_PROXY"
git config --global https.proxy "$HTTPS_PROXY"
exec "$@"
EOF

if [ "$1" = check ]; then
  read -r -d '' script <<'EOF' || true
s=0
echo "== OpenRouter key"
if [ "$OPENROUTER_API_KEY" = "sk-or-v1-placeholder" ]; then echo "Pi has the placeholder"
else echo "FAIL: the real OpenRouter key is in the Pi container"; s=1; fi
echo "== OpenRouter"
if r=$(curl -fsS -m 20 --cacert /etc/pi-proxy-ca/ca.pem https://openrouter.ai/api/v1/key); then
  printf '%s\n' "$r" | jq '.data | {label: .label, limit: .limit, remaining: .limit_remaining, usage: .usage}'
else
  echo "FAIL: OpenRouter. See: container logs pi-proxy"
  s=1
fi
echo "== GitHub"
gh auth status || s=1
[ -z "$1" ] || git ls-remote "https://github.com/$1.git" HEAD || s=1
echo "== other sites"
if curl -fsS -m 15 -o /dev/null https://example.com; then
  echo "FAIL: example.com was reachable"; s=1
else echo "example.com blocked"; fi
echo "== no route around the proxy"
if env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    curl -m 5 -fsS -o /dev/null https://github.com; then
  echo "FAIL: the container reached GitHub directly"; s=1
else echo "direct connection failed"; fi
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
elif [ "$PWD" = "$HOME" ] || [ "$PWD" = / ]; then
  echo "run.sh: refusing to mount $PWD; cd into a project first" >&2
  exit 1
else
  args+=(-v "$PWD:$PWD" -w "$PWD")
fi

set -- bash -c "$prep" prep "$@"
exec "$cli" "${args[@]}" "${PI_IMAGE:-pi-agent:local}" "$@"
