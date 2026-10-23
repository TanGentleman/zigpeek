#!/usr/bin/env bash
# Run Pi inside Apple's container, on a host-only network.
#   run.sh                         Pi on the current folder
#   run.sh --clone OWNER/REPO      Pi on a clone kept in a volume
#   run.sh check [OWNER/REPO]      keys, GitHub, and the network lock
#   run.sh proxy                   run the allowlist proxy in the foreground
#   run.sh proxy-stop              stop the background proxy
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
env_file="${PI_ENV_FILE:-$HOME/.config/pi-container/env}"
cfg="${PI_CONFIG_DIR:-$HOME/.config/pi-container}"
port="${PI_PROXY_PORT:-8888}"
proxy_url="http://host.container.internal:${port}"
placeholder="sk-or-v1-placeholder"
cli="${CONTAINER_CLI:-container}"

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

ensure_certs() {
  if [ -f "$cfg/certs/ca.pem" ] && [ -f "$cfg/private/openrouter.pem" ]; then
    return
  fi
  mkdir -p "$cfg/certs" "$cfg/private"
  chmod 700 "$cfg/private"
  command -v openssl >/dev/null || { echo "run.sh: openssl is required" >&2; exit 1; }
  openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout "$cfg/private/ca.key" -out "$cfg/certs/ca.pem" \
    -subj "/CN=pi-container proxy"
  openssl req -newkey rsa:2048 -nodes \
    -keyout "$cfg/private/openrouter.key" -out "$cfg/private/openrouter.csr" \
    -subj "/CN=openrouter.ai"
  printf '%s\n' \
    "subjectAltName=DNS:openrouter.ai,DNS:*.openrouter.ai" \
    "basicConstraints=CA:FALSE" \
    "extendedKeyUsage=serverAuth" > "$cfg/private/openrouter.ext"
  openssl x509 -req -in "$cfg/private/openrouter.csr" \
    -CA "$cfg/certs/ca.pem" -CAkey "$cfg/private/ca.key" -CAserial "$cfg/private/ca.srl" -CAcreateserial \
    -out "$cfg/private/openrouter.pem" -days 825 -sha256 \
    -extfile "$cfg/private/openrouter.ext"
  chmod 644 "$cfg/certs/ca.pem"
  chmod 600 "$cfg/private/ca.key" "$cfg/private/openrouter.key" "$cfg/private/openrouter.pem"
  rm -f "$cfg/private/openrouter.csr" "$cfg/private/openrouter.ext"
}

proxy_healthy() {
  curl -fsS -m 2 "http://127.0.0.1:${port}/health" 2>/dev/null | grep -qx "pi-container-proxy"
}

start_proxy() {
  command -v python3 >/dev/null || { echo "run.sh: python3 is required (brew install python)" >&2; exit 1; }
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    || { echo "run.sh: python 3.11 or newer is required" >&2; exit 1; }
  if [ -f "$cfg/proxy.pid" ] && kill -0 "$(cat "$cfg/proxy.pid")" 2>/dev/null; then
    if [ "$here/proxy.py" -nt "$cfg/proxy.pid" ] || ! proxy_healthy; then
      kill "$(cat "$cfg/proxy.pid")" 2>/dev/null || true
      sleep 0.2
    else
      return
    fi
  fi
  env -i PATH="$PATH" HOME="$HOME" \
    PI_ENV_FILE="$env_file" PI_PROXY_PORT="$port" \
    PI_PROXY_CERT="$cfg/private/openrouter.pem" PI_PROXY_KEY="$cfg/private/openrouter.key" \
    nohup python3 "$here/proxy.py" >>"$cfg/proxy.log" 2>&1 &
  echo $! > "$cfg/proxy.pid"
  i=0
  while [ "$i" -lt 30 ]; do
    proxy_healthy && return
    i=$((i + 1))
    sleep 0.1
  done
  echo "run.sh: proxy did not start. See $cfg/proxy.log" >&2
  exit 1
}

ensure_network() {
  names=$("$cli" network list -q) || { echo "run.sh: container network list failed" >&2; exit 1; }
  printf '%s\n' "$names" | grep -qx pi-locked && return
  "$cli" network create --internal pi-locked
}

if [ "${1:-}" = proxy-stop ]; then
  [ -f "$cfg/proxy.pid" ] && kill "$(cat "$cfg/proxy.pid")" 2>/dev/null || true
  rm -f "$cfg/proxy.pid"
  exit 0
fi

require_env
ensure_certs
if [ "${1:-}" = proxy ]; then
  echo "proxy on 127.0.0.1:${port}; Ctrl-C stops it" >&2
  exec env -i PATH="$PATH" HOME="$HOME" \
    PI_ENV_FILE="$env_file" PI_PROXY_PORT="$port" \
    PI_PROXY_CERT="$cfg/private/openrouter.pem" PI_PROXY_KEY="$cfg/private/openrouter.key" \
    python3 "$here/proxy.py"
fi
if [ "${PI_SKIP_HOST_SETUP:-}" != 1 ]; then
  start_proxy
  ensure_network
fi

args=(run --rm -i --init --network pi-locked
  --env-file "$env_file"
  --cpus "${PI_CPUS:-4}" --memory "${PI_MEMORY:-4G}"
  -e TERM=xterm-256color
  -e "OPENROUTER_API_KEY=${placeholder}"
  -e PI_TELEMETRY=0 -e GH_TELEMETRY=0
  -e "HTTP_PROXY=${proxy_url}" -e "HTTPS_PROXY=${proxy_url}"
  -e "http_proxy=${proxy_url}" -e "https_proxy=${proxy_url}"
  -e NO_PROXY=host.container.internal -e no_proxy=host.container.internal
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
echo "== OpenRouter key stays on the Mac"
if [ "$OPENROUTER_API_KEY" = "sk-or-v1-placeholder" ]; then echo "container has the placeholder"
else echo "FAIL: the real OpenRouter key is in the container"; s=1; fi
echo "== OpenRouter"
if r=$(curl -fsS -m 20 --cacert /etc/pi-proxy-ca/ca.pem https://openrouter.ai/api/v1/key); then
  printf '%s\n' "$r" | jq '.data | {label: .label, limit: .limit, remaining: .limit_remaining, usage: .usage}'
else
  echo "FAIL: OpenRouter. If the name host.container.internal did not resolve, run:"
  echo "  sudo container system dns create host.container.internal --localhost 203.0.113.113"
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
