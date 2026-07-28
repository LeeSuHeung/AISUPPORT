#!/usr/bin/env python3
"""Install AISUPPORT's Gupabal skill, agents, guidance, and hooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional


MINIMUM_PYTHON = (3, 10)
START_MARKER = "<!-- BEGIN CODEX GAME TEAM -->"
END_MARKER = "<!-- END CODEX GAME TEAM -->"

SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parent.parent
MANIFEST_PATH = REPOSITORY_ROOT / "gupabal-manifest.json"
SKILL_SOURCE = REPOSITORY_ROOT / ".agents" / "skills" / "gupabal-game"
AGENT_SOURCE_DIRECTORY = REPOSITORY_ROOT / ".codex" / "agents"
GUIDANCE_SOURCE = REPOSITORY_ROOT / ".codex" / "gupabal" / "AGENTS.md"
HOOK_SCRIPT_SOURCE = REPOSITORY_ROOT / ".codex" / "hooks" / "gupabal_hooks.py"
HOOK_TEMPLATE_SOURCE = (
    REPOSITORY_ROOT / ".codex" / "hooks" / "gupabal-hooks.template.json"
)
HOOK_MERGER = REPOSITORY_ROOT / "scripts" / "merge_gupabal_hooks.py"

HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class InstallerError(RuntimeError):
    """An expected installer failure suitable for a concise CLI message."""


@dataclass(frozen=True)
class PathSnapshot:
    kind: str
    digest: Optional[str]

    @property
    def exists(self) -> bool:
        return self.kind != "missing"


@dataclass(frozen=True)
class ManagedPathState:
    label: str
    source: Path
    destination: Path
    expected_snapshot: PathSnapshot
    snapshot: PathSnapshot
    matches: bool
    reason: Optional[str]

    @property
    def exists(self) -> bool:
        return self.snapshot.exists

    @property
    def conflicts(self) -> bool:
        return self.exists and not self.matches


@dataclass(frozen=True)
class TextFormat:
    encoding: str
    bom: bytes
    newline: str


@dataclass(frozen=True)
class GuidanceState:
    path: Path
    exists: bool
    status: str
    contents: str
    text_format: TextFormat
    snapshot: PathSnapshot
    mode: int
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    reason: Optional[str] = None

    @property
    def conflicts(self) -> bool:
        return self.status == "conflict"


@dataclass(frozen=True)
class HookRun:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class StaleAgentState:
    path: Path
    snapshot: PathSnapshot


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def absolute_path(path: Path) -> Path:
    """Normalize dot segments without silently following a target symlink."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def parse_arguments(arguments: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install reviewed Gupabal sources from this AISUPPORT checkout. "
            "No source files are downloaded or executed during validation."
        )
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".agents" / "skills",
        help="skill target root (default: ~/.agents/skills)",
    )
    parser.add_argument(
        "--agents-file",
        type=Path,
        default=default_codex_home() / "AGENTS.md",
        help="global guidance file (default: $CODEX_HOME/AGENTS.md)",
    )
    parser.add_argument("--verify", action="store_true", help="verify installed content")
    parser.add_argument("--dry-run", action="store_true", help="show actions without writes")
    parser.add_argument(
        "--with-hooks",
        action="store_true",
        help="explicitly install and verify Gupabal command Hooks",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="back up and replace conflicting managed content",
    )
    options = parser.parse_args(arguments)
    if options.verify and options.force:
        parser.error("--verify and --force cannot be used together")
    if options.verify and options.dry_run:
        parser.error("--verify and --dry-run cannot be used together")
    options.target = absolute_path(options.target)
    options.agents_file = absolute_path(options.agents_file)
    return options


def normalized_lf_bytes(path: Path) -> bytes:
    try:
        contents = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise InstallerError(f"Canonical source is not valid UTF-8: {path}") from error
    return contents.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def normalized_lf_hash(path: Path) -> str:
    return hashlib.sha256(normalized_lf_bytes(path)).hexdigest()


def _safe_manifest_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return False
    return path.as_posix() == value


def _source_files(directory: Path) -> list[Path]:
    if not directory.is_dir() or directory.is_symlink():
        raise InstallerError(f"Expected canonical source directory: {directory}")
    files: list[Path] = []
    for root, directory_names, file_names in os.walk(directory, followlinks=False):
        root_path = Path(root)
        directory_names.sort()
        file_names.sort()
        for directory_name in directory_names:
            child = root_path / directory_name
            if child.is_symlink():
                raise InstallerError(f"Symbolic links are not allowed in canonical sources: {child}")
        for file_name in file_names:
            child = root_path / file_name
            child_stat = child.lstat()
            if not stat.S_ISREG(child_stat.st_mode):
                raise InstallerError(f"Expected canonical source file: {child}")
            files.append(child)
    return files


def collect_canonical_sources() -> tuple[list[Path], list[Path]]:
    skill_files = _source_files(SKILL_SOURCE)
    agent_files = sorted(AGENT_SOURCE_DIRECTORY.glob("gupabal_*.toml"))
    if not agent_files:
        raise InstallerError(
            f"No canonical Gupabal agent files found in {AGENT_SOURCE_DIRECTORY}"
        )
    for path in agent_files:
        try:
            path_stat = path.lstat()
        except OSError as error:
            raise InstallerError(f"Could not inspect canonical source: {path}") from error
        if not stat.S_ISREG(path_stat.st_mode):
            raise InstallerError(f"Expected canonical source file: {path}")

    fixed_files = [
        GUIDANCE_SOURCE,
        HOOK_SCRIPT_SOURCE,
        HOOK_TEMPLATE_SOURCE,
        HOOK_MERGER,
    ]
    for path in fixed_files:
        try:
            path_stat = path.lstat()
        except FileNotFoundError as error:
            raise InstallerError(f"Missing canonical source: {path}") from error
        if not stat.S_ISREG(path_stat.st_mode):
            raise InstallerError(f"Expected canonical source file: {path}")

    canonical_files = sorted(
        [*skill_files, *agent_files, *fixed_files],
        key=lambda path: path.relative_to(REPOSITORY_ROOT).as_posix(),
    )
    return canonical_files, agent_files


def validate_manifest(
    canonical_files: Iterable[Path], manifest_path: Path = MANIFEST_PATH
) -> int:
    canonical_files = list(canonical_files)
    try:
        manifest_value = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as error:
        raise InstallerError(f"Missing integrity manifest: {manifest_path}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstallerError(f"Invalid integrity manifest: {manifest_path}: {error}") from error

    if not isinstance(manifest_value, dict) or manifest_value.get("version") != 1:
        raise InstallerError(f"Unsupported Gupabal manifest format: {manifest_path}")
    declared_files = manifest_value.get("files")
    if not isinstance(declared_files, dict):
        raise InstallerError(f"Gupabal manifest files must be an object: {manifest_path}")

    for repository_path, expected_hash in declared_files.items():
        if not isinstance(repository_path, str) or not _safe_manifest_path(repository_path):
            raise InstallerError(f"Invalid path in Gupabal manifest: {repository_path!r}")
        if not isinstance(expected_hash, str) or not HASH_PATTERN.fullmatch(expected_hash):
            raise InstallerError(f"Invalid SHA-256 in Gupabal manifest: {repository_path}")

    actual_paths = {
        source.relative_to(REPOSITORY_ROOT).as_posix() for source in canonical_files
    }
    declared_paths = set(declared_files)
    if actual_paths != declared_paths:
        missing = sorted(actual_paths - declared_paths)
        stale = sorted(declared_paths - actual_paths)
        details: list[str] = []
        if missing:
            details.append(f"missing entries: {', '.join(missing)}")
        if stale:
            details.append(f"entries without canonical files: {', '.join(stale)}")
        raise InstallerError(
            "Gupabal manifest file list does not exactly match canonical sources"
            + (f" ({'; '.join(details)})" if details else "")
        )

    verified = 0
    for source in canonical_files:
        repository_path = source.relative_to(REPOSITORY_ROOT).as_posix()
        expected_hash = declared_files.get(repository_path)
        if expected_hash is None:
            raise InstallerError(f"Gupabal manifest is missing: {repository_path}")
        actual_hash = normalized_lf_hash(source)
        if actual_hash != expected_hash:
            raise InstallerError(
                f"Gupabal manifest hash mismatch: {repository_path} "
                f"(expected {expected_hash}, found {actual_hash})"
            )
        verified += 1
    return verified


def _digest_path(path: Path) -> PathSnapshot:
    try:
        root_stat = path.lstat()
    except FileNotFoundError:
        return PathSnapshot("missing", None)
    except OSError as error:
        raise InstallerError(f"Could not inspect target: {path}: {error}") from error

    if stat.S_ISREG(root_stat.st_mode):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise InstallerError(f"Could not read target: {path}: {error}") from error
        return PathSnapshot("file", digest)
    if stat.S_ISLNK(root_stat.st_mode):
        try:
            target = os.readlink(path)
        except OSError as error:
            raise InstallerError(f"Could not read symbolic link: {path}: {error}") from error
        return PathSnapshot("symlink", hashlib.sha256(os.fsencode(target)).hexdigest())
    if not stat.S_ISDIR(root_stat.st_mode):
        description = f"special:{stat.S_IFMT(root_stat.st_mode):o}:{root_stat.st_size}"
        return PathSnapshot("special", hashlib.sha256(description.encode()).hexdigest())

    digest = hashlib.sha256()
    digest.update(b"directory\0")
    try:
        for root, directory_names, file_names in os.walk(path, followlinks=False):
            root_path = Path(root)
            directory_names.sort()
            file_names.sort()
            for name in [*directory_names, *file_names]:
                child = root_path / name
                relative = child.relative_to(path).as_posix().encode("utf-8")
                child_stat = child.lstat()
                digest.update(relative)
                digest.update(b"\0")
                if stat.S_ISDIR(child_stat.st_mode) and not stat.S_ISLNK(child_stat.st_mode):
                    digest.update(b"directory\0")
                elif stat.S_ISREG(child_stat.st_mode):
                    contents = child.read_bytes()
                    digest.update(b"file\0")
                    digest.update(str(len(contents)).encode("ascii"))
                    digest.update(b"\0")
                    digest.update(contents)
                    digest.update(b"\0")
                elif stat.S_ISLNK(child_stat.st_mode):
                    digest.update(b"symlink\0")
                    digest.update(os.fsencode(os.readlink(child)))
                    digest.update(b"\0")
                else:
                    digest.update(f"special:{stat.S_IFMT(child_stat.st_mode):o}".encode())
                    digest.update(b"\0")
    except OSError as error:
        raise InstallerError(f"Could not inspect target directory: {path}: {error}") from error
    return PathSnapshot("directory", digest.hexdigest())


def inspect_managed_path(label: str, source: Path, destination: Path) -> ManagedPathState:
    expected = _digest_path(source)
    actual = _digest_path(destination)
    matches = expected == actual
    reason: Optional[str] = None
    if not matches:
        if not actual.exists:
            reason = "missing"
        elif actual.kind != expected.kind:
            reason = f"expected {expected.kind}, found {actual.kind}"
        else:
            reason = "content differs"
    return ManagedPathState(
        label=label,
        source=source,
        destination=destination,
        expected_snapshot=expected,
        snapshot=actual,
        matches=matches,
        reason=reason,
    )


def _decode_text(bytes_value: bytes, path: Path) -> tuple[str, TextFormat]:
    encoding = "utf-8"
    bom = b""
    payload = bytes_value
    if bytes_value.startswith(b"\xef\xbb\xbf"):
        bom = b"\xef\xbb\xbf"
        payload = bytes_value[3:]
    elif bytes_value.startswith(b"\xff\xfe"):
        encoding = "utf-16-le"
        bom = b"\xff\xfe"
        payload = bytes_value[2:]
    elif bytes_value.startswith(b"\xfe\xff"):
        encoding = "utf-16-be"
        bom = b"\xfe\xff"
        payload = bytes_value[2:]
    elif b"\x00" in bytes_value:
        raise InstallerError(
            f"Unsupported text encoding in {path}; UTF-16 requires a byte-order mark"
        )
    try:
        contents = payload.decode(encoding, errors="strict")
    except UnicodeDecodeError as error:
        raise InstallerError(f"Invalid {encoding.upper()} text in {path}") from error
    if "\r\n" in contents:
        newline = "\r\n"
    elif "\r" in contents:
        newline = "\r"
    else:
        newline = "\n"
    return contents, TextFormat(encoding=encoding, bom=bom, newline=newline)


def _encode_text(contents: str, text_format: TextFormat) -> bytes:
    return text_format.bom + contents.encode(text_format.encoding)


def _normalize_newlines(contents: str) -> str:
    return contents.replace("\r\n", "\n").replace("\r", "\n")


def read_expected_guidance() -> str:
    try:
        source_bytes = GUIDANCE_SOURCE.read_bytes()
    except OSError as error:
        raise InstallerError(f"Could not read guidance source: {GUIDANCE_SOURCE}") from error
    contents, _ = _decode_text(source_bytes, GUIDANCE_SOURCE)
    contents = _normalize_newlines(contents)
    if contents.count(START_MARKER) != 1 or contents.count(END_MARKER) != 1:
        raise InstallerError(
            f"Canonical guidance must contain one CODEX GAME TEAM marker pair: {GUIDANCE_SOURCE}"
        )
    start_index = contents.index(START_MARKER)
    end_marker_index = contents.index(END_MARKER)
    if end_marker_index < start_index:
        raise InstallerError(f"Canonical guidance marker order is invalid: {GUIDANCE_SOURCE}")
    end_index = end_marker_index + len(END_MARKER)
    if contents[:start_index].strip() or contents[end_index:].strip():
        raise InstallerError(
            f"Canonical guidance contains content outside its managed markers: {GUIDANCE_SOURCE}"
        )
    return contents[start_index:end_index]


def inspect_guidance(path: Path, expected_block: str) -> GuidanceState:
    snapshot = _digest_path(path)
    if not snapshot.exists:
        return GuidanceState(
            path=path,
            exists=False,
            status="missing",
            contents="",
            text_format=TextFormat("utf-8", b"", "\n"),
            snapshot=snapshot,
            mode=0o666,
        )
    if snapshot.kind != "file":
        raise InstallerError(f"AGENTS target must be a regular file: {path}")
    try:
        path_stat = path.lstat()
        file_bytes = path.read_bytes()
    except OSError as error:
        raise InstallerError(f"Could not read AGENTS target: {path}: {error}") from error
    contents, text_format = _decode_text(file_bytes, path)
    start_count = contents.count(START_MARKER)
    end_count = contents.count(END_MARKER)
    common = dict(
        path=path,
        exists=True,
        contents=contents,
        text_format=text_format,
        snapshot=snapshot,
        mode=stat.S_IMODE(path_stat.st_mode),
    )
    if start_count == 0 and end_count == 0:
        return GuidanceState(status="missing", **common)
    if start_count != 1 or end_count != 1:
        return GuidanceState(
            status="malformed",
            reason=f"marker count mismatch (start={start_count}, end={end_count})",
            **common,
        )
    start_index = contents.index(START_MARKER)
    end_marker_index = contents.index(END_MARKER)
    if end_marker_index < start_index:
        return GuidanceState(
            status="malformed",
            reason="marker order mismatch",
            **common,
        )
    end_index = end_marker_index + len(END_MARKER)
    existing_block = _normalize_newlines(contents[start_index:end_index])
    if existing_block == expected_block:
        return GuidanceState(
            status="current",
            start_index=start_index,
            end_index=end_index,
            **common,
        )
    return GuidanceState(
        status="conflict",
        start_index=start_index,
        end_index=end_index,
        reason="managed block differs",
        **common,
    )


def build_guidance_contents(state: GuidanceState, expected_block: str) -> str:
    localized_block = expected_block.replace("\n", state.text_format.newline)
    newline = state.text_format.newline
    if state.status == "missing":
        if not state.contents:
            return localized_block + newline
        if state.contents.endswith(newline + newline):
            separator = ""
        elif state.contents.endswith(newline):
            separator = newline
        else:
            separator = newline + newline
        return state.contents + separator + localized_block + newline
    if state.status == "conflict":
        if state.start_index is None or state.end_index is None:
            raise InstallerError(f"Cannot replace malformed CODEX GAME TEAM markers: {state.path}")
        return (
            state.contents[: state.start_index]
            + localized_block
            + state.contents[state.end_index :]
        )
    return state.contents


def _assert_snapshot(path: Path, expected: PathSnapshot) -> None:
    current = _digest_path(path)
    if current != expected:
        raise InstallerError(f"Target changed during installation: {path}")


def _available_backup_path(base: Path) -> Path:
    if not _digest_path(base).exists:
        return base
    counter = 1
    while True:
        candidate = Path(f"{base}-{counter}")
        if not _digest_path(candidate).exists:
            return candidate
        counter += 1


def _replace_with_staged_path(
    destination: Path,
    staged_path: Path,
    expected_snapshot: PathSnapshot,
    backup_path: Optional[Path],
) -> Optional[Path]:
    _assert_snapshot(destination, expected_snapshot)
    moved_backup: Optional[Path] = None
    if expected_snapshot.exists:
        if backup_path is None:
            raise InstallerError(f"Internal error: no backup path for {destination}")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = _available_backup_path(backup_path)
        os.replace(destination, backup_path)
        moved_backup = backup_path
    try:
        os.replace(staged_path, destination)
    except BaseException:
        if moved_backup is not None and not _digest_path(destination).exists:
            os.replace(moved_backup, destination)
        raise
    return moved_backup


def install_managed_path(
    state: ManagedPathState,
    backup_root: Path,
    backup_suffix: str,
) -> Optional[Path]:
    if state.matches:
        return None
    state.destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{state.destination.name}-gupabal-install-",
            dir=state.destination.parent,
        )
    )
    staged = temporary_parent / state.destination.name
    try:
        if state.expected_snapshot.kind == "directory":
            shutil.copytree(state.source, staged, symlinks=False)
        elif state.expected_snapshot.kind == "file":
            shutil.copy2(state.source, staged)
        else:
            raise InstallerError(f"Unsupported canonical source type: {state.source}")
        if _digest_path(staged) != state.expected_snapshot:
            raise InstallerError(f"Verification failed while staging {state.label}")
        backup_path = None
        if state.exists:
            backup_path = backup_root / f"{state.destination.name}.backup-{backup_suffix}"
        return _replace_with_staged_path(
            state.destination,
            staged,
            state.snapshot,
            backup_path,
        )
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)


def install_guidance(
    state: GuidanceState,
    expected_block: str,
    backup_suffix: str,
) -> Optional[Path]:
    if state.status == "current":
        return None
    updated_contents = build_guidance_contents(state, expected_block)
    encoded = _encode_text(updated_contents, state.text_format)
    destination = state.path
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}-gupabal-install-",
        suffix=".tmp",
        dir=destination.parent,
    )
    staged = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        if state.exists:
            try:
                os.chmod(staged, state.mode)
            except OSError:
                pass
        backup_path = (
            Path(f"{destination}.backup-{backup_suffix}") if state.exists else None
        )
        return _replace_with_staged_path(
            destination,
            staged,
            state.snapshot,
            backup_path,
        )
    finally:
        if staged.exists():
            staged.unlink()


def _container_error(path: Path, description: str) -> Optional[str]:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        return f"Could not inspect {description}: {path}: {error}"
    if stat.S_ISLNK(path_stat.st_mode):
        return f"{description} must not be a symbolic link: {path}"
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return f"{description} must not be a junction: {path}"
        except OSError as error:
            return f"Could not inspect {description}: {path}: {error}"
    else:
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        attributes = getattr(path_stat, "st_file_attributes", 0)
        if reparse_flag and attributes & reparse_flag:
            return f"{description} must not be a reparse point: {path}"
    if not stat.S_ISDIR(path_stat.st_mode):
        return f"{description} must be a directory: {path}"
    return None


def inspect_stale_agents(
    agent_directory: Path, expected_names: set[str]
) -> list[StaleAgentState]:
    if not agent_directory.exists():
        return []
    stale: list[StaleAgentState] = []
    for path in sorted(agent_directory.glob("gupabal_*.toml")):
        if path.name in expected_names:
            continue
        snapshot = _digest_path(path)
        if snapshot.kind != "file":
            raise InstallerError(f"Stale Gupabal agent must be a regular file: {path}")
        stale.append(StaleAgentState(path=path, snapshot=snapshot))
    return stale


def remove_stale_agent(state: StaleAgentState, backup_suffix: str) -> Path:
    _assert_snapshot(state.path, state.snapshot)
    backup = _available_backup_path(Path(f"{state.path}.backup-{backup_suffix}"))
    os.replace(state.path, backup)
    return backup


def _hook_collision_error(codex_home: Path) -> Optional[str]:
    hooks_configuration = codex_home / "hooks.json"
    config_snapshot = _digest_path(hooks_configuration)
    if config_snapshot.exists and config_snapshot.kind != "file":
        return f"Hooks target must be a regular file: {hooks_configuration}"

    hooks_directory = codex_home / "hooks"
    container_error = _container_error(hooks_directory, "Hooks directory")
    if container_error:
        return container_error

    script_hash = hashlib.sha256(HOOK_SCRIPT_SOURCE.read_bytes()).hexdigest()[:16]
    installed_script = hooks_directory / f"gupabal_hooks_{script_hash}.py"
    installed_snapshot = _digest_path(installed_script)
    if not installed_snapshot.exists:
        return None
    source_snapshot = _digest_path(HOOK_SCRIPT_SOURCE)
    if installed_snapshot != source_snapshot:
        return f"Versioned Hook script collision: {installed_script}"
    return None


def run_hook_merger(mode: str, codex_home: Path, backup_suffix: str) -> HookRun:
    if mode not in (
        "--verify",
        "--verify-removed",
        "--dry-run",
        "--dry-run-removed",
        "--remove",
        "install",
    ):
        raise InstallerError(f"Internal error: unsupported Hook merger mode {mode}")
    command = [
        sys.executable,
        str(HOOK_MERGER),
        "--source",
        str(HOOK_TEMPLATE_SOURCE),
        "--hook-script-source",
        str(HOOK_SCRIPT_SOURCE),
        "--target",
        str(codex_home / "hooks.json"),
        "--backup-suffix",
        backup_suffix,
    ]
    if mode != "install":
        command.append(mode)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
    except OSError as error:
        raise InstallerError(f"Could not start Hook merger: {error}") from error
    return HookRun(completed.returncode, completed.stdout, completed.stderr)


def _relay_hook_output(result: HookRun) -> None:
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )


def _managed_action(state: ManagedPathState, force: bool) -> str:
    if state.matches:
        return "KEEP"
    if state.exists:
        return "BACKUP+REPLACE" if force else "CONFLICT"
    return "INSTALL"


def _guidance_action(state: GuidanceState, force: bool) -> str:
    if state.status == "current":
        return "KEEP"
    if state.conflicts and not force:
        return "CONFLICT"
    if state.exists:
        return "BACKUP+UPDATE"
    return "INSTALL"


def _print_conflicts(
    states: Iterable[ManagedPathState],
    guidance: GuidanceState,
    stale_agents: Iterable[StaleAgentState] = (),
    *,
    emit: bool = True,
) -> list[str]:
    conflicts: list[str] = []
    for state in states:
        if state.conflicts:
            message = f"CONFLICT {state.label}: {state.destination} ({state.reason})"
            if emit:
                print(message, file=sys.stderr)
            conflicts.append(message)
    if guidance.conflicts:
        message = f"CONFLICT always-on: {guidance.path} ({guidance.reason})"
        if emit:
            print(message, file=sys.stderr)
        conflicts.append(message)
    for state in stale_agents:
        message = f"CONFLICT stale agent: {state.path}"
        if emit:
            print(message, file=sys.stderr)
        conflicts.append(message)
    return conflicts


def _verify(
    states: list[ManagedPathState],
    guidance: GuidanceState,
    stale_agents: list[StaleAgentState],
    codex_home: Path,
    backup_suffix: str,
    with_hooks: bool,
) -> int:
    failures = 0
    for state in states:
        status = "OK" if state.matches else "MISMATCH"
        detail = "" if state.matches else f" ({state.reason})"
        print(f"{status} {state.label}: {state.destination}{detail}")
        failures += 0 if state.matches else 1
    guidance_matches = guidance.status == "current"
    guidance_detail = "" if guidance_matches else f" ({guidance.reason or guidance.status})"
    print(
        f"{'OK' if guidance_matches else 'MISMATCH'} always-on: "
        f"{guidance.path}{guidance_detail}"
    )
    failures += 0 if guidance_matches else 1
    for state in stale_agents:
        print(f"MISMATCH stale agent: {state.path}")
        failures += 1

    if not with_hooks:
        hook_result = run_hook_merger("--verify-removed", codex_home, backup_suffix)
        _relay_hook_output(hook_result)
        if hook_result.returncode != 0:
            failures += 1
    else:
        collision_error = _hook_collision_error(codex_home)
        if collision_error:
            print(f"MISMATCH hooks: {collision_error}")
            failures += 1
        else:
            hook_result = run_hook_merger("--verify", codex_home, backup_suffix)
            _relay_hook_output(hook_result)
            if hook_result.returncode != 0:
                failures += 1

    if failures:
        print(f"Gupabal verification failed: {failures} managed item(s) differ", file=sys.stderr)
        return 1
    print(
        "Verified Gupabal skill, agents, guidance, and "
        f"hooks {'enabled' if with_hooks else 'disabled'}"
    )
    return 0


def run(options: argparse.Namespace) -> int:
    if sys.version_info < MINIMUM_PYTHON:
        found = ".".join(str(part) for part in sys.version_info[:3])
        raise InstallerError(f"Python 3.10 or newer is required; found {found}")

    canonical_files, agent_sources = collect_canonical_sources()
    verified_sources = validate_manifest(canonical_files)
    print(f"SOURCE OK {verified_sources} canonical file(s): {MANIFEST_PATH}")

    target_root: Path = options.target
    agents_file: Path = options.agents_file
    codex_home = agents_file.parent
    agent_target_directory = codex_home / "agents"

    container_errors = [
        _container_error(target_root, "Skill target root"),
        _container_error(codex_home, "CODEX_HOME"),
        _container_error(agent_target_directory, "Agent target directory"),
    ]
    for error in container_errors:
        if error:
            raise InstallerError(error)

    expected_guidance = read_expected_guidance()
    states = [
        inspect_managed_path(
            "skill gupabal-game",
            SKILL_SOURCE,
            target_root / "gupabal-game",
        )
    ]
    states.extend(
        inspect_managed_path(
            f"agent {source.name}",
            source,
            agent_target_directory / source.name,
        )
        for source in agent_sources
    )
    stale_agents = inspect_stale_agents(
        agent_target_directory, {source.name for source in agent_sources}
    )
    guidance = inspect_guidance(agents_file, expected_guidance)
    backup_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    if options.verify:
        return _verify(
            states,
            guidance,
            stale_agents,
            codex_home,
            backup_suffix,
            options.with_hooks,
        )

    preflight_errors: list[str] = []
    if guidance.status == "malformed":
        preflight_errors.append(
            f"Malformed CODEX GAME TEAM markers in {guidance.path}: {guidance.reason}; "
            "--force cannot repair malformed markers"
        )
    hook_preflight = None
    if options.with_hooks:
        hook_collision = _hook_collision_error(codex_home)
        if hook_collision:
            preflight_errors.append(hook_collision)
        else:
            hook_preflight = run_hook_merger("--dry-run", codex_home, backup_suffix)
            if hook_preflight.returncode != 0:
                details = (hook_preflight.stderr or hook_preflight.stdout).strip()
                preflight_errors.append(
                    "Hook merger dry-run failed" + (f": {details}" if details else "")
                )
    elif options.dry_run:
        hook_preflight = run_hook_merger(
            "--dry-run-removed", codex_home, backup_suffix
        )
        if hook_preflight.returncode != 0:
            details = (hook_preflight.stderr or hook_preflight.stdout).strip()
            preflight_errors.append(
                "Hook merger dry-run failed" + (f": {details}" if details else "")
            )

    conflicts = _print_conflicts(
        states, guidance, stale_agents, emit=not options.force
    )
    if conflicts and not options.force:
        preflight_errors.append(
            "Existing managed content differs; inspect it, then use --force to back up and replace it"
        )

    if preflight_errors:
        if hook_preflight is not None and hook_preflight.returncode != 0:
            _relay_hook_output(hook_preflight)
        raise InstallerError("; ".join(preflight_errors))

    if options.dry_run:
        for state in states:
            print(
                f"{_managed_action(state, options.force)} {state.label} -> "
                f"{state.destination}"
            )
        for state in stale_agents:
            print(f"BACKUP+REMOVE stale agent -> {state.path}")
        print(
            f"{_guidance_action(guidance, options.force)} always-on -> {guidance.path}"
        )
        if hook_preflight is not None:
            _relay_hook_output(hook_preflight)
        print(f"Hooks {'enabled' if options.with_hooks else 'disabled'}")
        print("Dry run complete; no files were written")
        return 0

    target_root.mkdir(parents=True, exist_ok=True)
    agent_target_directory.mkdir(parents=True, exist_ok=True)
    for index, state in enumerate(states):
        if state.matches:
            print(f"UP-TO-DATE {state.label}: {state.destination}")
            continue
        backup_root = (
            target_root.parent / "skill-backups"
            if index == 0
            else state.destination.parent
        )
        backup = install_managed_path(state, backup_root, backup_suffix)
        print(f"INSTALLED {state.label}: {state.destination}")
        if backup:
            print(f"BACKUP {backup}")

    for state in stale_agents:
        backup = remove_stale_agent(state, backup_suffix)
        print(f"REMOVED stale agent: {state.path}")
        print(f"BACKUP {backup}")

    if guidance.status == "current":
        print(f"UP-TO-DATE always-on: {guidance.path}")
    else:
        guidance_backup = install_guidance(
            guidance,
            expected_guidance,
            backup_suffix,
        )
        print(f"INSTALLED always-on: {guidance.path}")
        if guidance_backup:
            print(f"BACKUP {guidance_backup}")

    hook_result = run_hook_merger(
        "install" if options.with_hooks else "--remove", codex_home, backup_suffix
    )
    _relay_hook_output(hook_result)
    if hook_result.returncode != 0:
        raise InstallerError(
            f"Hook merger failed with exit status {hook_result.returncode}"
        )
    print(
        f"Installed Gupabal support into {target_root} and {codex_home} "
        f"(hooks {'enabled' if options.with_hooks else 'disabled'})"
    )
    if options.with_hooks:
        print("Review command Hooks in /hooks, then start a new Codex task")
    return 0


def main(arguments: Optional[list[str]] = None) -> int:
    options = parse_arguments(arguments)
    try:
        return run(options)
    except InstallerError as error:
        print(f"Gupabal installer failed: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"Gupabal installer failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
