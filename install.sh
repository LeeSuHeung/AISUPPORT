#!/usr/bin/env sh
set -eu

target_home="${1:-$HOME}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_root="$script_dir/bundle"
agent_destination="$target_home/.codex/agents"
skill_destination="$target_home/.agents/skills/gupabal-game"
global_instructions="$target_home/.codex/AGENTS.md"
timestamp=$(date +%Y%m%d-%H%M%S)

if ! python_executable=$(command -v python3); then
    printf '%s\n' 'Python 3.10 or newer is required to install and run the Gupabal game Hooks.' >&2
    exit 1
fi
if ! "$python_executable" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    printf '%s\n' 'Python 3.10 or newer is required to install and run the Gupabal game Hooks.' >&2
    exit 1
fi

install_managed_file() {
    source_file=$1
    destination_file=$2
    destination_directory=$(dirname -- "$destination_file")
    mkdir -p -- "$destination_directory"

    if [ -f "$destination_file" ] && cmp -s -- "$source_file" "$destination_file"; then
        printf 'Unchanged: %s\n' "$destination_file"
        return
    fi

    if [ -f "$destination_file" ]; then
        cp -- "$destination_file" "$destination_file.backup-$timestamp"
    fi

    cp -- "$source_file" "$destination_file"
    printf 'Installed: %s\n' "$destination_file"
}

remove_legacy_managed_file() {
    legacy_file=$1
    if [ ! -f "$legacy_file" ]; then
        return
    fi

    cp -- "$legacy_file" "$legacy_file.backup-$timestamp"
    rm -- "$legacy_file"
    printf 'Removed legacy name: %s\n' "$legacy_file"
}

mkdir -p -- "$agent_destination" "$skill_destination/agents" "$(dirname -- "$global_instructions")"

for file_name in gupabal_planner.toml gupabal_art_designer.toml gupabal_client.toml gupabal_server.toml; do
    install_managed_file "$source_root/agents/$file_name" "$agent_destination/$file_name"
done

install_managed_file \
    "$source_root/skills/gupabal-game/SKILL.md" \
    "$skill_destination/SKILL.md"
install_managed_file \
    "$source_root/skills/gupabal-game/agents/openai.yaml" \
    "$skill_destination/agents/openai.yaml"
install_managed_file \
    "$source_root/skills/gupabal-game/references/decision-template.json" \
    "$skill_destination/references/decision-template.json"
install_managed_file \
    "$source_root/skills/gupabal-game/references/decision-policy.md" \
    "$skill_destination/references/decision-policy.md"

"$python_executable" "$source_root/hooks/merge_hooks.py" \
    --source "$source_root/hooks/hooks.json" \
    --hook-script-source "$source_root/hooks/gupabal_hooks.py" \
    --target "$target_home/.codex/hooks.json" \
    --backup-suffix "$timestamp"

for file_name in game_planner.toml game_art_designer.toml game_client.toml game_server.toml; do
    remove_legacy_managed_file "$agent_destination/$file_name"
done

legacy_skill_destination="$target_home/.agents/skills/coordinate-game-feature-team"
remove_legacy_managed_file "$legacy_skill_destination/SKILL.md"
remove_legacy_managed_file "$legacy_skill_destination/agents/openai.yaml"

start_marker='<!-- BEGIN CODEX GAME TEAM -->'
end_marker='<!-- END CODEX GAME TEAM -->'
base_file=$(mktemp)
output_file=$(mktemp)
trap 'rm -f -- "$base_file" "$output_file"' EXIT HUP INT TERM

if [ -f "$global_instructions" ]; then
    awk -v start="$start_marker" -v end="$end_marker" '
        $0 == start { inside = 1; next }
        $0 == end { inside = 0; next }
        !inside && ($0 == "# Universal Game Development Team" || $0 == "# 구파발게임 개발팀") { legacy = 1; next }
        legacy && $0 == "- 여러 에이전트가 동일한 파일을 동시에 수정하지 않게 한다." { legacy = 0; next }
        !inside && !legacy { print }
    ' "$global_instructions" > "$base_file"
else
    : > "$base_file"
fi

{
    cat "$base_file"
    if [ -s "$base_file" ]; then
        printf '\n'
    fi
    printf '%s\n' "$start_marker"
    cat "$source_root/AGENTS.md"
    printf '%s\n' "$end_marker"
} > "$output_file"

if [ -f "$global_instructions" ] && cmp -s -- "$output_file" "$global_instructions"; then
    printf 'Unchanged: %s\n' "$global_instructions"
else
    if [ -f "$global_instructions" ]; then
        cp -- "$global_instructions" "$global_instructions.backup-$timestamp"
    fi
    cp -- "$output_file" "$global_instructions"
    printf 'Updated: %s\n' "$global_instructions"
fi

printf '%s\n' 'Installation complete. Review the command Hooks in /hooks, then start a new Codex task.'
