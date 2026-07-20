#!/usr/bin/env sh
set -eu

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 18 or newer is required: https://nodejs.org/" >&2
  exit 1
fi

node_major="$(node -p "process.versions.node.split('.')[0]")"
if [ "$node_major" -lt 18 ]; then
  echo "Node.js 18 or newer is required. Found major version $node_major." >&2
  exit 1
fi

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec node "$script_directory/install-caveman.mjs" "$@"
