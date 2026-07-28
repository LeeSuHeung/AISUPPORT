#!/usr/bin/env python3
"""Merge AISUPPORT-managed Gupabal handlers without replacing user hooks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


MANAGED_SCRIPT_MARKER = "gupabal_hooks_"
LEGACY_SCRIPT_NAME = "gupabal_hooks.py"
MANAGED_SCRIPT_PATTERN = re.compile(r"^gupabal_hooks_[0-9a-f]{16}\.py$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--hook-script-source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--backup-suffix", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--verify-removed", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--dry-run-removed", action="store_true")
    mode.add_argument("--remove", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    hooks = value.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise ValueError(f"hooks must be an object: {path}")
    return value


def replace_tokens(
    value: Any, command: str, windows_commands: dict[str, str]
) -> Any:
    if isinstance(value, dict):
        return {
            key: replace_tokens(item, command, windows_commands)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [replace_tokens(item, command, windows_commands) for item in value]
    if isinstance(value, str):
        rendered = value.replace("__GUPABAL_COMMAND__", command)
        for event_hint, windows_command in windows_commands.items():
            rendered = rendered.replace(
                f"__GUPABAL_WINDOWS_COMMAND__ {event_hint}", windows_command
            )
        if "__GUPABAL_WINDOWS_COMMAND__" in rendered:
            raise ValueError("Unsupported Windows Hook command template")
        return rendered
    return value


def is_managed_handler(handler: Any, hooks_directory: Path) -> bool:
    if not isinstance(handler, dict):
        return False
    command = handler.get("command")
    if not isinstance(command, str):
        return False
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    if len(arguments) == 3:
        script_argument = arguments[1]
    elif len(arguments) == 5 and arguments[1:3] == ["-X", "utf8"]:
        script_argument = arguments[3]
    else:
        return False
    script_path = Path(script_argument).expanduser().resolve(strict=False)
    script_name = script_path.name
    managed_name = script_name == LEGACY_SCRIPT_NAME or bool(
        MANAGED_SCRIPT_PATTERN.fullmatch(script_name)
    )
    return managed_name and script_path.parent == hooks_directory.resolve(strict=False)


def remove_managed_handlers(groups: list[Any], hooks_directory: Path) -> list[Any]:
    cleaned: list[Any] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            cleaned.append(group)
            continue
        handlers = group["hooks"]
        retained = [
            handler
            for handler in handlers
            if not is_managed_handler(handler, hooks_directory)
        ]
        if len(retained) == len(handlers):
            cleaned.append(group)
        elif retained:
            updated_group = dict(group)
            updated_group["hooks"] = retained
            cleaned.append(updated_group)
    return cleaned


def merge(
    existing: dict[str, Any], managed: dict[str, Any], hooks_directory: Path
) -> dict[str, Any]:
    result = dict(existing)
    if "description" not in result and isinstance(managed.get("description"), str):
        result["description"] = managed["description"]
    existing_hooks = result.get("hooks")
    existing_hooks = dict(existing_hooks) if isinstance(existing_hooks, dict) else {}
    for event, groups in list(existing_hooks.items()):
        if not isinstance(groups, list):
            raise ValueError(f"existing hook event must be a list and was not changed: {event}")
        existing_hooks[event] = remove_managed_handlers(groups, hooks_directory)
    managed_hooks = managed.get("hooks")
    if not isinstance(managed_hooks, dict):
        raise ValueError("managed hooks must be an object")
    for event, groups in managed_hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"managed hook event must be a list: {event}")
        current = existing_hooks.get(event)
        current = list(current) if isinstance(current, list) else []
        existing_hooks[event] = current + groups
    result["hooks"] = existing_hooks
    return result


def remove(existing: dict[str, Any], hooks_directory: Path) -> dict[str, Any]:
    result = dict(existing)
    existing_hooks = result.get("hooks")
    if not isinstance(existing_hooks, dict):
        return result
    cleaned_hooks = dict(existing_hooks)
    for event, groups in existing_hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"existing hook event must be a list and was not changed: {event}")
        cleaned_hooks[event] = remove_managed_handlers(groups, hooks_directory)
    result["hooks"] = cleaned_hooks
    return result


def powershell_literal(value: str) -> str:
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("Windows Hook argument contains an invalid control character")
    return "'" + value.replace("'", "''") + "'"


def windows_hook_command(executable: str, hook_script: str, event_hint: str) -> str:
    powershell = (
        f"& {powershell_literal(executable)} -X utf8 "
        f"{powershell_literal(hook_script)} {powershell_literal(event_hint)}\n"
        "exit $LASTEXITCODE"
    )
    encoded = base64.b64encode(powershell.encode("utf-16-le")).decode("ascii")
    return (
        "powershell.exe -NoLogo -NoProfile -NonInteractive "
        f"-EncodedCommand {encoded}"
    )


def main() -> int:
    args = parse_args()
    source = args.source.resolve(strict=True)
    hook_script_source = args.hook_script_source.resolve(strict=True)
    target = args.target.expanduser().resolve(strict=False)
    script_hash = hashlib.sha256(hook_script_source.read_bytes()).hexdigest()[:16]
    hook_script = (target.parent / "hooks" / f"{MANAGED_SCRIPT_MARKER}{script_hash}.py").resolve(strict=False)

    executable = str(Path(sys.executable).resolve(strict=False))
    unix_command = (
        f"{shlex.quote(executable)} -X utf8 {shlex.quote(str(hook_script))}"
    )
    windows_commands = {
        event_hint: windows_hook_command(executable, str(hook_script), event_hint)
        for event_hint in ("SubagentStop", "PreToolUse", "PostToolUse")
    }
    managed = replace_tokens(read_json(source), unix_command, windows_commands)
    existing = read_json(target) if target.is_file() else {}
    merged = (
        remove(existing, hook_script.parent)
        if args.remove or args.verify_removed or args.dry_run_removed
        else merge(existing, managed, hook_script.parent)
    )
    rendered = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    previous = target.read_text(encoding="utf-8-sig") if target.is_file() else None
    script_matches = hook_script.is_file() and hook_script.read_bytes() == hook_script_source.read_bytes()
    config_matches = previous == rendered

    if args.verify_removed:
        removal_matches = merged == existing
        print(f"{'OK' if removal_matches else 'MISMATCH'} {target}")
        return 0 if removal_matches else 1

    if args.dry_run_removed:
        removal_matches = merged == existing
        print(f"{'KEEP' if removal_matches else 'REMOVE MANAGED'} {target}")
        return 0

    if args.remove:
        config_changed = target.is_file() and merged != existing
        if not config_changed:
            print(f"Unchanged: {target}")
            return 0
        backup = Path(f"{target}.backup-{args.backup_suffix}")
        shutil.copy2(target, backup)
        print(f"Backed up: {backup}")
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write(rendered)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        print(f"Updated: {target}")
        return 0

    if args.verify:
        print(f"{'OK' if script_matches else 'MISMATCH'} {hook_script}")
        print(f"{'OK' if config_matches else 'MISMATCH'} {target}")
        return 0 if script_matches and config_matches else 1

    if args.dry_run:
        print(f"{'KEEP' if script_matches else 'INSTALL'} {hook_script}")
        print(f"{'KEEP' if config_matches else 'UPDATE'} {target}")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    hook_script.parent.mkdir(parents=True, exist_ok=True)
    if script_matches:
        print(f"Unchanged: {hook_script}")
    elif hook_script.is_file():
        if hook_script.read_bytes() != hook_script_source.read_bytes():
            raise ValueError(f"versioned hook script hash collision: {hook_script}")
    else:
        shutil.copy2(hook_script_source, hook_script)
        print(f"Installed: {hook_script}")

    if config_matches:
        print(f"Unchanged: {target}")
        return 0

    if target.is_file():
        backup = Path(f"{target}.backup-{args.backup_suffix}")
        shutil.copy2(target, backup)
        print(f"Backed up: {backup}")

    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Updated: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
