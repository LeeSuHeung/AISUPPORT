#!/usr/bin/env sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test_root=$(mktemp -d)
test_user_path="$test_root/사용자 홈 with spaces"
first_log="$test_root/first.log"
second_log="$test_root/second.log"
trap 'rm -rf -- "$test_root"' EXIT HUP INT TERM

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
    mkdir -p -- "$test_root/bin"
    printf '%s\n' '#!/usr/bin/env sh' 'exec python "$@"' > "$test_root/bin/python3"
    chmod +x "$test_root/bin/python3"
    PATH="$test_root/bin:$PATH"
    export PATH
fi

mkdir -p -- "$test_user_path"
sh "$repository/install.sh" "$test_user_path" > "$first_log"
sh "$repository/install.sh" "$test_user_path" > "$second_log"

grep -q 'Unchanged:' "$second_log"
test -f "$test_user_path/.agents/skills/gupabal-game/references/decision-policy.md"

python3 - "$test_user_path" <<'PY'
import json
import pathlib
import sys

test_user_path = pathlib.Path(sys.argv[1])
hooks_path = test_user_path / ".codex" / "hooks.json"
hooks = json.loads(hooks_path.read_text(encoding="utf-8-sig"))
for event_name in ("SubagentStop", "PreToolUse", "PostToolUse"):
    assert len(hooks["hooks"][event_name]) == 1
versioned_scripts = list((test_user_path / ".codex" / "hooks").glob("gupabal_hooks_*.py"))
assert len(versioned_scripts) == 1
PY

printf '%s\n' 'install.sh x2 with spaced Unicode home OK'
