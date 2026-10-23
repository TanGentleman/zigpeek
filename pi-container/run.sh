#!/usr/bin/env bash
# Run Pi inside Apple's container, on a host-only network.
#   run.sh                         Pi on the current folder
#   run.sh --clone OWNER/REPO      Pi on a clone kept in a volume
#   run.sh check [OWNER/REPO]      keys, GitHub, and the network lock
#   run.sh proxy                   follow the proxy container's logs
#   run.sh proxy-stop              stop the proxy container
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
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

addr_file() { printf '%s\n' "$cfg/private/proxy.addr"; }

# `container inspect` prints pretty JSON. Current releases nest the value in
# status.state. Older releases use a top-level status string. Split on "}"
# so either shape is one record.
proxy_state() {
  json=$("$cli" inspect "$proxy_name" 2>/dev/null) || { printf '\n'; return; }
  printf '%s\n' "$json" | awk '
    BEGIN { RS = "}" }
    /"state"[[:space:]]*:[[:space:]]*"/ || /"status"[[:space:]]*:[[:space:]]*"/ {
      s = $0
      sub(/.*"(state|status)"[[:space:]]*:[[:space:]]*"/, "", s)
      sub(/".*/, "", s)
      if (s ~ /^(running|stopped|stopping|unknown)$/) state = s
    }
    END { print state }
  '
}

valid_ip() {
  local ip=$1 o
  [[ $ip =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  for o in "${BASH_REMATCH[@]:1}"; do
    ((10#$o <= 255)) || return 1
  done
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
  state=$(proxy_state || true)
  state=$(printf '%s\n' "$state" | sed -n '1p')
  if [ "$state" = running ]; then
    return
  fi
  # The address file is published only after the socket is bound. Drop a
  # stale one so a previous run cannot look ready during this boot.
  rm -f "$(addr_file)"
  if [ "$state" = stopped ] || [ "$state" = stopping ]; then
    "$cli" start "$proxy_name"
    return
  fi
  "$cli" run -d --name "$proxy_name" --init \
    --cpus 1 --memory 1G \
    --network default --network pi-locked \
    --env-file "$cfg/proxy.env" \
    -v "$cfg/private:/private" -v "$cfg/certs:/certs" \
    "$proxy_image" >/dev/null
}

# Pi reaches the proxy on the locked network. Ask from inside that container,
# which is the path Pi uses.
proxy_answers() {
  "$cli" exec "$proxy_name" /usr/local/bin/python3 -c \
    'import sys,urllib.request
ip, port = sys.argv[1], sys.argv[2]
body = urllib.request.urlopen("http://%s:%s/health" % (ip, port), timeout=2).read()
raise SystemExit(0 if body == b"pi-container-proxy\n" else 1)' \
    "$1" "$port"
}

proxy_ip() {
  file=$(addr_file)
  ip=""
  i=0
  tries="${PI_PROXY_WAIT:-90}"
  while [ "$i" -lt "$tries" ]; do
    if [ -f "$file" ]; then
      ip=$(tr -d '[:space:]' < "$file" || true)
      if valid_ip "$ip" && proxy_answers "$ip" >/dev/null 2>&1; then
        printf '%s\n' "$ip"
        return
      fi
    fi
    i=$((i + 1))
    sleep 1
  done
  if valid_ip "${ip:-}"; then
    echo "run.sh: pi-proxy is listening on ${ip}:${port} but did not answer from inside the container. Run: $cli logs $proxy_name" >&2
  else
    echo "run.sh: pi-proxy did not report an address. Run: $cli logs $proxy_name" >&2
  fi
  exit 1
}

# Tests source this file to call the functions above. They do not start a container.
if [ "${PI_SOURCE_ONLY:-}" = 1 ]; then
  return 0 2>/dev/null || exit 0
fi

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
# An IP, not a name. Host-only networks have no DNS, so a name failing
# only proves that, and still leaves TCP egress open when the Mac forwards.
code=$(env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy \
    curl -sS -m 5 -o /dev/null -w '%{http_code}' http://1.1.1.1/ || true)
if [ "$code" != 000 ]; then
  echo "FAIL: the container reached the internet directly (HTTP $code)"; s=1
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
