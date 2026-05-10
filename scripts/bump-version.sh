#!/usr/bin/env bash
# Bumps the version in both pyproject.toml files and the offline-extra
# pin so they stay in lockstep. Usage: ./scripts/bump-version.sh 0.5.0
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <new-version>" >&2
  exit 2
fi

new="$1"
repo="$(cd "$(dirname "$0")/.." && pwd)"
main="$repo/pyproject.toml"
data="$repo/packages/zigpeek-offline/pyproject.toml"

# sed -i differs between BSD (macOS) and GNU; pass an empty backup arg both ways
sed_inplace() { sed -i.bak "$@" && rm -f "${@: -1}.bak"; }

sed_inplace "s/^version = \".*\"/version = \"$new\"/" "$main"
sed_inplace "s/^version = \".*\"/version = \"$new\"/" "$data"
sed_inplace "s/zigpeek-offline==[0-9][0-9a-zA-Z.+-]*/zigpeek-offline==$new/" "$main"

echo "Bumped both pyprojects + offline pin to $new"
echo "Next: git commit -am 'release $new' && git tag v$new && git push --follow-tags"
