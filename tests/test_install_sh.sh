#!/usr/bin/env sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test_root=$(mktemp -d)
test_user_path="$test_root/사용자 홈 with spaces"
skill_target="$test_user_path/.agents/skills"
agents_file="$test_user_path/.codex/AGENTS.md"
first_log="$test_root/first.log"
second_log="$test_root/second.log"
trap 'rm -rf -- "$test_root"' EXIT HUP INT TERM

node -e 'if (Number(process.versions.node.split(".")[0]) < 18) process.exit(1)'
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
    mkdir -p -- "$test_root/bin"
    printf '%s\n' '#!/usr/bin/env sh' 'exec python "$@"' > "$test_root/bin/python3"
    chmod +x "$test_root/bin/python3"
    PATH="$test_root/bin:$PATH"
    export PATH
fi

mkdir -p -- "$test_user_path"
sh "$repository/install.sh" --target "$skill_target" --agents-file "$agents_file" > "$first_log"
sh "$repository/install.sh" --target "$skill_target" --agents-file "$agents_file" > "$second_log"
sh "$repository/install.sh" --target "$skill_target" --agents-file "$agents_file" --verify >/dev/null

grep -Eq 'UP-TO-DATE|Unchanged:' "$second_log"
test -f "$skill_target/short/SKILL.md"
test -f "$skill_target/gupabal-game/references/decision-policy.md"
test -f "$test_user_path/.codex/agents/gupabal_planner.toml"

python3 - "$test_user_path" <<'PY'
import json
import pathlib
import sys

test_user_path = pathlib.Path(sys.argv[1])
hooks_path = test_user_path / ".codex" / "hooks.json"
assert not hooks_path.exists()
PY

sh "$repository/install.sh" --target "$skill_target" --agents-file "$agents_file" --with-hooks >/dev/null
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

printf '%s\n' 'POSIX install wrapper tests passed'
