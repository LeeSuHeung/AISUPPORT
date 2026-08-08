#!/usr/bin/env python3
"""Install the AISUPPORT Telegram notifier without replacing an existing notifier."""

from __future__ import annotations

import argparse
import ast
import codecs
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPOSITORY_ROOT / ".codex" / "hooks" / "telegram_notify.py"
MANIFEST = REPOSITORY_ROOT / "telegram-manifest.json"
RUNTIME_PATTERN = re.compile(r"^telegram_notify_[0-9a-f]{16}\.py$")


class InstallerError(RuntimeError):
    """A concise installer error."""


@dataclass(frozen=True)
class ConfigText:
    text: str
    bom: bool
    newline: str


@dataclass(frozen=True)
class NotifyAssignment:
    value_start: int
    value_end: int
    assignment_start: int
    assignment_end: int
    value: list[str]


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-home", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--remove", action="store_true")
    return parser.parse_args(arguments)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest() -> None:
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstallerError(f"Invalid Telegram manifest: {MANIFEST}") from error
    if not isinstance(manifest, dict):
        raise InstallerError(f"Invalid Telegram manifest: {MANIFEST}")
    files = manifest.get("files")
    if manifest.get("version") != 1 or not isinstance(files, dict):
        raise InstallerError(f"Invalid Telegram manifest: {MANIFEST}")
    expected = {
        ".codex/hooks/telegram_notify.py",
        "scripts/install-telegram-notify.py",
    }
    if set(files) != expected:
        raise InstallerError("Telegram manifest file list does not match installer sources")
    for relative, digest in files.items():
        path = REPOSITORY_ROOT / Path(relative)
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise InstallerError(f"Telegram source integrity mismatch: {path}")


def read_config(path: Path) -> ConfigText:
    if not path.exists():
        return ConfigText("", False, "\n")
    path_stat = path.lstat()
    if not stat.S_ISREG(path_stat.st_mode):
        raise InstallerError(f"Codex config must be a regular file: {path}")
    raw = path.read_bytes()
    bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InstallerError(f"Codex config must use UTF-8: {path}") from error
    newline = "\r\n" if "\r\n" in text else "\n"
    return ConfigText(text, bom, newline)


def scan_array_end(text: str, start: int) -> int:
    if start >= len(text) or text[start] != "[":
        raise InstallerError("Root notify value must be a string array")
    depth = 0
    quote = None
    escaped = False
    comment = False
    for index in range(start, len(text)):
        character = text[index]
        if comment:
            if character in "\r\n":
                comment = False
            continue
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "'\"":
            quote = character
        elif character == "#":
            comment = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    raise InstallerError("Root notify array is not closed")


def parse_notify_value(raw: str) -> list[str]:
    try:
        import tomllib

        value: Any = tomllib.loads(f"notify = {raw}")["notify"]
    except ModuleNotFoundError:
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError) as error:
            raise InstallerError("Root notify value could not be parsed") from error
    except Exception as error:
        raise InstallerError("Root notify value could not be parsed") from error
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstallerError("Root notify value must be a string array")
    return value


def find_notify(text: str) -> NotifyAssignment | None:
    table = re.search(r"(?m)^[ \t]*\[", text)
    root_end = table.start() if table else len(text)
    matches = list(re.finditer(r"(?m)^[ \t]*notify[ \t]*=", text[:root_end]))
    if not matches:
        return None
    if len(matches) != 1:
        raise InstallerError("Codex config contains duplicate root notify values")
    match = matches[0]
    value_start = match.end()
    while value_start < len(text) and text[value_start] in " \t":
        value_start += 1
    value_end = scan_array_end(text, value_start)
    line_end = text.find("\n", value_end)
    assignment_end = len(text) if line_end < 0 else line_end + 1
    return NotifyAssignment(
        value_start=value_start,
        value_end=value_end,
        assignment_start=match.start(),
        assignment_end=assignment_end,
        value=parse_notify_value(text[value_start:value_end]),
    )


def is_managed_script(value: str, hooks_directory: Path) -> bool:
    path = Path(value).expanduser().resolve(strict=False)
    return (
        bool(RUNTIME_PATTERN.fullmatch(path.name))
        and path.parent == hooks_directory.resolve(strict=False)
    )


def unwrap_notify(command: list[str], hooks_directory: Path) -> tuple[list[str], bool]:
    for index, value in enumerate(command):
        if not is_managed_script(value, hooks_directory):
            continue
        remaining = command[index + 1 :]
        if not remaining:
            return [], True
        if remaining[0] != "--delegate":
            raise InstallerError("Managed Telegram notify command is malformed")
        return remaining[1:], True
    return command, False


def encoded_command(command: list[str]) -> str:
    return json.dumps(command, ensure_ascii=False)


def insert_notify(text: str, command: list[str], newline: str) -> str:
    table = re.search(r"(?m)^[ \t]*\[", text)
    position = table.start() if table else len(text)
    if table:
        for line in reversed(text[:position].splitlines(keepends=True)):
            if line.strip() and not line.lstrip().startswith("#"):
                break
            position -= len(line)
    prefix = text[:position]
    suffix = text[position:]
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += newline
    if prefix and not prefix.endswith(newline * 2):
        prefix += newline
    return prefix + f"notify = {encoded_command(command)}{newline}{newline}" + suffix


def update_config(
    config: ConfigText,
    hooks_directory: Path,
    runtime: Path,
    remove: bool = False,
) -> tuple[str, bool]:
    assignment = find_notify(config.text)
    current = assignment.value if assignment else []
    delegate, managed = unwrap_notify(current, hooks_directory)

    if remove:
        if not managed or assignment is None:
            return config.text, False
        if delegate:
            updated = (
                config.text[: assignment.value_start]
                + encoded_command(delegate)
                + config.text[assignment.value_end :]
            )
        else:
            updated = (
                config.text[: assignment.assignment_start]
                + config.text[assignment.assignment_end :]
            )
        return updated, updated != config.text

    expected = [sys.executable, "-X", "utf8", str(runtime)]
    if delegate:
        expected.extend(["--delegate", *delegate])
    if assignment is None:
        updated = insert_notify(config.text, expected, config.newline)
    else:
        updated = (
            config.text[: assignment.value_start]
            + encoded_command(expected)
            + config.text[assignment.value_end :]
        )
    return updated, updated != config.text


def ensure_directory(path: Path) -> None:
    if path.exists():
        path_stat = path.lstat()
        if not stat.S_ISDIR(path_stat.st_mode):
            raise InstallerError(f"Expected a directory: {path}")
    else:
        path.mkdir(parents=True)


def write_config(path: Path, config: ConfigText, text: str) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(f"{path.name}.backup-{suffix}")
        shutil.copy2(path, backup)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        payload = text.encode("utf-8")
        if config.bom:
            payload = codecs.BOM_UTF8 + payload
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return backup


def run(options: argparse.Namespace) -> int:
    verify_manifest()
    codex_home = options.codex_home.expanduser().resolve(strict=False)
    hooks_directory = codex_home / "hooks"
    config_path = codex_home / "config.toml"
    runtime = hooks_directory / f"telegram_notify_{sha256(SOURCE)[:16]}.py"
    config = read_config(config_path)
    updated, changed = update_config(
        config, hooks_directory, runtime, remove=options.remove
    )
    script_matches = runtime.is_file() and not runtime.is_symlink() and sha256(runtime) == sha256(SOURCE)

    if options.verify:
        print(f"{'OK' if script_matches else 'MISMATCH'} {runtime}")
        print(f"{'OK' if not changed else 'MISMATCH'} {config_path}")
        return 0 if script_matches and not changed else 1
    if options.dry_run:
        print(f"{'KEEP' if script_matches else 'INSTALL'} {runtime}")
        print(f"{'KEEP' if not changed else 'UPDATE'} {config_path}")
        return 0
    if options.remove:
        if not changed:
            print(f"Unchanged: {config_path}")
            return 0
        backup = write_config(config_path, config, updated)
        if backup:
            print(f"Backed up: {backup}")
        print(f"Restored: {config_path}")
        return 0

    ensure_directory(codex_home)
    ensure_directory(hooks_directory)
    if runtime.exists() and not script_matches:
        raise InstallerError(f"Versioned Telegram notifier collision: {runtime}")
    if not script_matches:
        shutil.copy2(SOURCE, runtime)
        print(f"Installed: {runtime}")
    else:
        print(f"Unchanged: {runtime}")
    if changed:
        backup = write_config(config_path, config, updated)
        if backup:
            print(f"Backed up: {backup}")
        print(f"Updated: {config_path}")
    else:
        print(f"Unchanged: {config_path}")
    return 0


def main(arguments: list[str] | None = None) -> int:
    try:
        return run(parse_arguments(arguments))
    except InstallerError as error:
        print(f"Telegram notifier installer failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
