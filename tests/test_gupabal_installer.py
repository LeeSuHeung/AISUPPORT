from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install_gupabal.py"
MANIFEST_PATH = REPOSITORY_ROOT / "gupabal-manifest.json"
START_MARKER = "<!-- BEGIN CODEX GAME TEAM -->"
END_MARKER = "<!-- END CODEX GAME TEAM -->"

INSTALLER_SPEC = importlib.util.spec_from_file_location(
    "gupabal_installer_under_test", INSTALLER
)
if INSTALLER_SPEC is None or INSTALLER_SPEC.loader is None:
    raise RuntimeError(f"Could not load installer module: {INSTALLER}")
INSTALLER_MODULE = importlib.util.module_from_spec(INSTALLER_SPEC)
sys.modules[INSTALLER_SPEC.name] = INSTALLER_MODULE
INSTALLER_SPEC.loader.exec_module(INSTALLER_MODULE)


def snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    """Return a content snapshot suitable for proving a dry run made no writes."""
    if not root.exists():
        return {}

    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.fsencode(os.readlink(path)))
        elif path.is_dir():
            snapshot[relative] = ("directory", None)
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        else:
            snapshot[relative] = ("other", None)
    return snapshot


def normalized_lf_hash(path: Path) -> str:
    contents = path.read_bytes().decode("utf-8")
    normalized = contents.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def count_managed_handlers(configuration: dict[str, Any]) -> int:
    count = 0
    hooks = configuration.get("hooks", {})
    if not isinstance(hooks, dict):
        return 0
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for handler in group["hooks"]:
                if not isinstance(handler, dict):
                    continue
                commands = (
                    handler.get("command"),
                    handler.get("commandWindows"),
                    handler.get("command_windows"),
                )
                if any(
                    isinstance(command, str) and "gupabal_hooks_" in command
                    for command in commands
                ):
                    count += 1
    return count


class GupabalInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
        cls.manifest_files: dict[str, str] = cls.manifest["files"]

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.sandbox = Path(self.temporary_directory.name) / "한글 대상 폴더"
        self.sandbox.mkdir()
        self.skills_root = self.sandbox / "사용자 스킬"
        self.codex_home = self.sandbox / "코덱스 홈"
        self.agents_file = self.codex_home / "AGENTS.md"

    def run_installer(
        self,
        *arguments: str,
        skills_root: Path | None = None,
        agents_file: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--target",
                str(skills_root or self.skills_root),
                "--agents-file",
                str(agents_file or self.agents_file),
                *arguments,
            ],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=environment,
            check=False,
        )

    def assert_succeeded(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def assert_failed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(
            result.returncode,
            0,
            f"installer unexpectedly succeeded:\n{result.stdout}",
        )

    def write_user_hooks(self, codex_home: Path | None = None) -> dict[str, Any]:
        home = codex_home or self.codex_home
        home.mkdir(parents=True, exist_ok=True)
        configuration: dict[str, Any] = {
            "description": "사용자 Hook 설정",
            "userSetting": {"preserve": True},
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "^shell_command$",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python user_hook.py",
                                "timeout": 7,
                            }
                        ],
                    }
                ],
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python session_hook.py",
                            }
                        ],
                    }
                ],
            },
        }
        (home / "hooks.json").write_text(
            json.dumps(configuration, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return configuration

    def assert_manifest_matches_actual_sources(self) -> None:
        self.assertEqual(self.manifest["version"], 1)
        self.assertTrue(self.manifest_files)
        for relative, expected_hash in self.manifest_files.items():
            with self.subTest(source=relative):
                source = REPOSITORY_ROOT.joinpath(*PurePosixPath(relative).parts)
                self.assertTrue(source.is_file(), f"missing manifest source: {relative}")
                self.assertEqual(normalized_lf_hash(source), expected_hash)

    def test_dry_run_leaves_every_target_unchanged(self) -> None:
        self.codex_home.mkdir(parents=True)
        self.agents_file.write_text("# 사용자 전역 지침\n", encoding="utf-8")
        self.write_user_hooks()
        before = snapshot_tree(self.sandbox)

        result = self.run_installer("--dry-run")

        self.assert_succeeded(result)
        self.assertEqual(snapshot_tree(self.sandbox), before)
        self.assertFalse(self.skills_root.exists())
        self.assertIn("no files were written", result.stdout)

    def test_manifest_rejects_an_entry_whose_source_was_removed(self) -> None:
        canonical_files, _ = INSTALLER_MODULE.collect_canonical_sources()
        modified_manifest = json.loads(json.dumps(self.manifest))
        modified_manifest["files"][".agents/skills/gupabal-game/removed.md"] = "0" * 64
        manifest_path = self.sandbox / "manifest-with-removed-source.json"
        manifest_path.write_text(
            json.dumps(modified_manifest, ensure_ascii=False), encoding="utf-8"
        )

        with self.assertRaisesRegex(
            INSTALLER_MODULE.InstallerError, "does not exactly match"
        ):
            INSTALLER_MODULE.validate_manifest(canonical_files, manifest_path)

    def test_install_then_verify_uses_manifest_pinned_sources(self) -> None:
        self.assert_manifest_matches_actual_sources()

        install = self.run_installer()
        verify = self.run_installer("--verify")

        self.assert_succeeded(install)
        self.assert_succeeded(verify)
        self.assertIn("Verified Gupabal", verify.stdout)

        skill_prefix = PurePosixPath(".agents/skills")
        codex_prefix = PurePosixPath(".codex")
        for relative in self.manifest_files:
            source_relative = PurePosixPath(relative)
            source = REPOSITORY_ROOT.joinpath(*source_relative.parts)
            if source_relative.parts[:2] == skill_prefix.parts:
                destination_relative = source_relative.relative_to(skill_prefix)
                destination = self.skills_root.joinpath(*destination_relative.parts)
                self.assertEqual(destination.read_bytes(), source.read_bytes())
            elif source_relative.parts[:2] == (".codex", "agents"):
                destination_relative = source_relative.relative_to(codex_prefix)
                destination = self.codex_home.joinpath(*destination_relative.parts)
                self.assertEqual(destination.read_bytes(), source.read_bytes())

        expected_guidance = (
            REPOSITORY_ROOT / ".codex" / "gupabal" / "AGENTS.md"
        ).read_text(encoding="utf-8")
        self.assertIn(expected_guidance.strip(), self.agents_file.read_text(encoding="utf-8"))

        hook_source = REPOSITORY_ROOT / ".codex" / "hooks" / "gupabal_hooks.py"
        script_hash = hashlib.sha256(hook_source.read_bytes()).hexdigest()[:16]
        installed_hook = self.codex_home / "hooks" / f"gupabal_hooks_{script_hash}.py"
        self.assertEqual(installed_hook.read_bytes(), hook_source.read_bytes())

    def test_reinstall_is_idempotent_for_handlers_scripts_and_backups(self) -> None:
        self.codex_home.mkdir(parents=True)
        self.agents_file.write_text("# 사용자 지침\n", encoding="utf-8")
        self.write_user_hooks()
        first = self.run_installer()
        self.assert_succeeded(first)

        first_configuration_bytes = (self.codex_home / "hooks.json").read_bytes()
        first_configuration = json.loads(first_configuration_bytes.decode("utf-8"))
        first_scripts = sorted(self.codex_home.glob("hooks/gupabal_hooks_*.py"))
        first_backups = {
            path.relative_to(self.sandbox).as_posix(): path.read_bytes()
            for path in self.sandbox.rglob("*backup-*")
            if path.is_file()
        }
        self.assertEqual(count_managed_handlers(first_configuration), 3)
        self.assertEqual(len(first_scripts), 1)
        self.assertTrue(first_backups)

        second = self.run_installer()

        self.assert_succeeded(second)
        second_configuration_bytes = (self.codex_home / "hooks.json").read_bytes()
        second_configuration = json.loads(second_configuration_bytes.decode("utf-8"))
        second_scripts = sorted(self.codex_home.glob("hooks/gupabal_hooks_*.py"))
        second_backups = {
            path.relative_to(self.sandbox).as_posix(): path.read_bytes()
            for path in self.sandbox.rglob("*backup-*")
            if path.is_file()
        }
        self.assertEqual(count_managed_handlers(second_configuration), 3)
        self.assertEqual(len(second_scripts), 1)
        self.assertEqual(second_configuration_bytes, first_configuration_bytes)
        self.assertEqual(second_scripts, first_scripts)
        self.assertEqual(second_backups, first_backups)

    def test_existing_user_hooks_are_preserved(self) -> None:
        original = self.write_user_hooks()

        result = self.run_installer()

        self.assert_succeeded(result)
        installed = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["description"], original["description"])
        self.assertEqual(installed["userSetting"], original["userSetting"])
        self.assertIn(
            original["hooks"]["PreToolUse"][0],
            installed["hooks"]["PreToolUse"],
        )
        self.assertEqual(installed["hooks"]["SessionStart"], original["hooks"]["SessionStart"])
        self.assertEqual(count_managed_handlers(installed), 3)

    def test_agent_conflict_without_force_fails_before_any_target_write(self) -> None:
        conflicting_agent = self.codex_home / "agents" / "gupabal_client.toml"
        conflicting_agent.parent.mkdir(parents=True)
        conflicting_agent.write_text("# 사용자 agent 설정\n", encoding="utf-8")
        before = snapshot_tree(self.sandbox)

        result = self.run_installer()

        self.assert_failed(result)
        self.assertEqual(snapshot_tree(self.sandbox), before)
        self.assertIn("--force", result.stderr)

    def test_force_backs_up_and_replaces_conflicting_agent(self) -> None:
        conflicting_agent = self.codex_home / "agents" / "gupabal_client.toml"
        conflicting_agent.parent.mkdir(parents=True)
        original = "# 사용자 agent 설정\n".encode("utf-8")
        conflicting_agent.write_bytes(original)
        source = REPOSITORY_ROOT / ".codex" / "agents" / conflicting_agent.name

        install = self.run_installer("--force")
        verify = self.run_installer("--verify")

        self.assert_succeeded(install)
        self.assert_succeeded(verify)
        self.assertNotIn("CONFLICT", install.stderr)
        self.assertEqual(conflicting_agent.read_bytes(), source.read_bytes())
        backups = sorted(conflicting_agent.parent.glob(f"{conflicting_agent.name}.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_stale_agent_requires_force_and_is_backed_up(self) -> None:
        install = self.run_installer()
        self.assert_succeeded(install)
        stale_agent = self.codex_home / "agents" / "gupabal_retired.toml"
        original = b'name = "retired"\n'
        stale_agent.write_bytes(original)
        before = snapshot_tree(self.sandbox)

        verify_before = self.run_installer("--verify")
        without_force = self.run_installer()

        self.assert_failed(verify_before)
        self.assertIn("stale agent", verify_before.stdout)
        self.assert_failed(without_force)
        self.assertEqual(snapshot_tree(self.sandbox), before)

        forced = self.run_installer("--force")
        verify_after = self.run_installer("--verify")

        self.assert_succeeded(forced)
        self.assert_succeeded(verify_after)
        self.assertFalse(stale_agent.exists())
        backups = sorted(stale_agent.parent.glob(f"{stale_agent.name}.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_skill_target_symlink_is_rejected_without_writes(self) -> None:
        real_target = self.sandbox / "real-skill-target"
        real_target.mkdir()
        linked_target = self.sandbox / "linked-skill-target"
        try:
            linked_target.symlink_to(real_target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")
        before = snapshot_tree(self.sandbox)

        result = self.run_installer(skills_root=linked_target)

        self.assert_failed(result)
        self.assertIn("symbolic link", result.stderr)
        self.assertEqual(snapshot_tree(self.sandbox), before)

    def test_force_rejects_broken_or_duplicate_markers_without_writes(self) -> None:
        expected_block = (
            REPOSITORY_ROOT / ".codex" / "gupabal" / "AGENTS.md"
        ).read_text(encoding="utf-8").strip()
        cases = {
            "깨진 마커": f"# 사용자 지침\n\n{START_MARKER}\n미완성 블록\n",
            "중복 마커": (
                f"# 사용자 지침\n\n{expected_block}\n\n"
                f"{expected_block}\n"
            ),
        }

        for case_name, original in cases.items():
            with self.subTest(case=case_name):
                case_root = self.sandbox / case_name
                skills_root = case_root / "사용자 스킬"
                codex_home = case_root / "코덱스 홈"
                agents_file = codex_home / "AGENTS.md"
                codex_home.mkdir(parents=True)
                agents_file.write_text(original, encoding="utf-8")
                before = snapshot_tree(case_root)

                result = self.run_installer(
                    "--force",
                    skills_root=skills_root,
                    agents_file=agents_file,
                )

                self.assert_failed(result)
                self.assertEqual(snapshot_tree(case_root), before)
                self.assertEqual(agents_file.read_text(encoding="utf-8"), original)
                self.assertIn("Malformed CODEX GAME TEAM markers", result.stderr)


if __name__ == "__main__":
    unittest.main()
