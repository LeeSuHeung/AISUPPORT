#!/usr/bin/env sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$script_directory/scripts/install-aisupport.sh" "$@"
