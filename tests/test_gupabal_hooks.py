from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
HOOK = REPOSITORY / "bundle" / "hooks" / "gupabal_hooks.py"
MERGER = REPOSITORY / "bundle" / "hooks" / "merge_hooks.py"
HOOK_SOURCE = REPOSITORY / "bundle" / "hooks" / "hooks.json"


class HookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_hook(self, event: dict) -> tuple[subprocess.CompletedProcess[str], dict | None]:
        completed = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(event, ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout) if completed.stdout.strip() else None
        return completed, payload

    def write_policy(self, *, status: str = "approved") -> Path:
        decision = self.root / ".codex" / "gupabal" / "decision.json"
        decision.parent.mkdir(parents=True)
        decision.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "enabled": True,
                    "feature": "실제 테스트 대상",
                    "planning_allow": [],
                    "agreement": {
                        "status": status,
                        "approvals": {
                            "planner": "AGREE" if status == "approved" else "PENDING",
                            "art": "AGREE" if status == "approved" else "PENDING",
                            "client": "AGREE" if status == "approved" else "PENDING",
                            "server": "AGREE" if status == "approved" else "PENDING",
                        },
                        "unresolved": [],
                    },
                    "ownership": {
                        "art": ["Assets/**"],
                        "client": ["Client/**"],
                        "server": ["Server/**"],
                        "shared": [],
                    },
                    "checks": {
                        "exclude": ["**/vendor/**"],
                        "art": {"roots": ["Assets/**"], "assets": []},
                        "client": {"roots": ["Client/**"]},
                        "server": {"roots": ["Server/**"]},
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return decision

    @staticmethod
    def patch_event(root: Path, event_name: str, patch: str) -> dict:
        event = {
            "hook_event_name": event_name,
            "cwd": str(root),
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
        if event_name == "PostToolUse":
            event["tool_response"] = "Done"
        return event

    def test_inactive_repository_is_silent(self) -> None:
        completed, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch")
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIsNone(payload)

    def test_disabled_policy_is_silent_and_malformed_policy_warns(self) -> None:
        decision = self.write_policy(status="planning")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["enabled"] = False
        decision.write_text(json.dumps(policy), encoding="utf-8")
        event = self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch")
        _, disabled_payload = self.run_hook(event)
        self.assertIsNone(disabled_payload)
        decision.write_text("{broken", encoding="utf-8")
        _, malformed_payload = self.run_hook(event)
        output = malformed_payload["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", output)
        self.assertIn("합의 파일을 적용하지 못했습니다", output["additionalContext"])

    def test_subagent_result_is_requested_only_once(self) -> None:
        event = {
            "hook_event_name": "SubagentStop",
            "agent_type": "gupabal_client",
            "last_assistant_message": "검토했습니다.",
            "stop_hook_active": False,
        }
        _, payload = self.run_hook(event)
        self.assertEqual(payload["decision"], "block")
        event["stop_hook_active"] = True
        _, second_payload = self.run_hook(event)
        self.assertIsNone(second_payload)

    def test_complete_subagent_result_passes(self) -> None:
        message = """완료했습니다.
GUPABAL_RESULT
scope: Client/UI.cs
risks: NONE
verification: unit test passed
END_GUPABAL_RESULT
"""
        _, payload = self.run_hook(
            {
                "hook_event_name": "SubagentStop",
                "agent_type": "구파발클라이언트",
                "last_assistant_message": message,
                "stop_hook_active": False,
            }
        )
        self.assertIsNone(payload)

    def test_subagent_result_marker_must_be_at_end(self) -> None:
        message = """GUPABAL_RESULT
scope: Client/UI.cs
risks: NONE
verification: unit test passed
END_GUPABAL_RESULT
표식 뒤에 다른 결과가 있습니다.
"""
        _, payload = self.run_hook(
            {
                "hook_event_name": "SubagentStop",
                "agent_type": "gupabal_client",
                "last_assistant_message": message,
                "stop_hook_active": False,
            }
        )
        self.assertEqual(payload["decision"], "block")

    def test_planning_policy_blocks_implementation_patch(self) -> None:
        self.write_policy(status="planning")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch")
        )
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")

    def test_planning_policy_allows_decision_file_patch(self) -> None:
        self.write_policy(status="planning")
        _, payload = self.run_hook(
            self.patch_event(
                self.root,
                "PreToolUse",
                "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n@@\n-x\n+y\n*** End Patch",
            )
        )
        self.assertIsNone(payload)

    def test_planning_allow_path_passes(self) -> None:
        decision = self.write_policy(status="planning")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["planning_allow"] = ["Docs/Planning/**"]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Docs/Planning/feature.md\n+x\n*** End Patch")
        )
        self.assertIsNone(payload)

    def test_single_star_does_not_allow_nested_planning_path(self) -> None:
        decision = self.write_policy(status="planning")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["planning_allow"] = ["Docs/*.md"]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Docs/Nested/feature.md\n+x\n*** End Patch")
        )
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_oversized_patch_is_blocked_when_policy_is_active(self) -> None:
        self.write_policy(status="planning")
        oversized_patch = "*** Begin Patch\n*** Update File: Client/a.cs\n" + ("x" * 4_194_304)
        _, payload = self.run_hook(self.patch_event(self.root, "PreToolUse", oversized_patch))
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_oversized_decision_creation_is_blocked_without_policy(self) -> None:
        oversized_patch = (
            "*** Begin Patch\n*** Add File: .codex/gupabal/decision.json\n+{}\n"
            + ("x" * 4_194_304)
        )
        _, payload = self.run_hook(self.patch_event(self.root, "PreToolUse", oversized_patch))
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_decision_creation_must_be_separate_from_implementation(self) -> None:
        patch = """*** Begin Patch
*** Add File: .codex/gupabal/decision.json
+{}
*** Add File: Client/a.cs
+x
*** End Patch"""
        _, payload = self.run_hook(self.patch_event(self.root, "PreToolUse", patch))
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_existing_decision_change_must_be_separate_from_implementation(self) -> None:
        self.write_policy()
        patch = """*** Begin Patch
*** Update File: .codex/gupabal/decision.json
@@
-x
+y
*** Update File: Client/a.cs
@@
-x
+y
*** End Patch"""
        _, payload = self.run_hook(self.patch_event(self.root, "PreToolUse", patch))
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_unowned_file_warns_without_denying(self) -> None:
        self.write_policy()
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Other/a.txt\n+x\n*** End Patch")
        )
        output = payload["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", output)
        self.assertIn("소유 경로", output["additionalContext"])

    def test_unresolved_items_block_implementation_after_approvals(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["agreement"]["unresolved"] = ["서버 재시도 계약"]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Server/a.cs\n+x\n*** End Patch")
        )
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("미결정 1건", output["permissionDecisionReason"])

    def test_check_root_does_not_hide_missing_owner_but_still_routes_post_check(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"] = []
        decision.write_text(json.dumps(policy), encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: Client/settings.json\n@@\n-x\n+y\n*** End Patch"
        _, pre_payload = self.run_hook(self.patch_event(self.root, "PreToolUse", patch))
        self.assertIn("소유 경로", pre_payload["hookSpecificOutput"]["additionalContext"])

        target = self.root / "Client" / "settings.json"
        target.parent.mkdir()
        target.write_text("{invalid", encoding="utf-8")
        _, post_payload = self.run_hook(self.patch_event(self.root, "PostToolUse", patch))
        self.assertIn("JSON 문법 오류", post_payload["hookSpecificOutput"]["additionalContext"])

    def test_overlapping_owners_warn_without_denying(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["server"] = ["Client/**", "Server/**"]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch")
        )
        output = payload["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", output)
        self.assertIn("담당자가 둘 이상", output["additionalContext"])

    def test_post_hook_reports_invalid_client_json(self) -> None:
        self.write_policy()
        target = self.root / "Client" / "settings.json"
        target.parent.mkdir()
        target.write_text("{invalid", encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Client/settings.json\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIn("JSON 문법 오류", payload["hookSpecificOutput"]["additionalContext"])

    def test_post_hook_reports_empty_json(self) -> None:
        self.write_policy()
        target = self.root / "Client" / "empty.json"
        target.parent.mkdir()
        target.write_text("", encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Client/empty.json\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIn("JSON 문법 오류", payload["hookSpecificOutput"]["additionalContext"])

    def test_large_json_is_deferred_with_warning(self) -> None:
        self.write_policy()
        target = self.root / "Client" / "large.json"
        target.parent.mkdir()
        target.write_bytes(b" " * 1_048_577)
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Client/large.json\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIn("완료 검증", payload["hookSpecificOutput"]["additionalContext"])

    def test_post_hook_reports_invalid_png(self) -> None:
        self.write_policy()
        target = self.root / "Assets" / "broken.png"
        target.parent.mkdir()
        target.write_bytes(b"not a png")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Assets/broken.png\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIn("PNG 헤더", payload["hookSpecificOutput"]["additionalContext"])

    def test_fake_png_without_ihdr_is_rejected(self) -> None:
        self.write_policy()
        target = self.root / "Assets" / "fake.png"
        target.parent.mkdir()
        target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Assets/fake.png\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIn("PNG 헤더", payload["hookSpecificOutput"]["additionalContext"])

    def test_malformed_webp_and_svg_are_rejected(self) -> None:
        self.write_policy()
        assets = self.root / "Assets"
        assets.mkdir()
        (assets / "bad.webp").write_bytes(b"RIFF\x04\x00\x00\x00WEBP")
        (assets / "bad.svg").write_text("<svg><g>", encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: Assets/bad.webp\n@@\n-x\n+y\n*** Update File: Assets/bad.svg\n@@\n-x\n+y\n*** End Patch"
        _, payload = self.run_hook(self.patch_event(self.root, "PostToolUse", patch))
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("WebP 헤더", context)
        self.assertIn("SVG XML 문법", context)

    def test_webp_chunk_size_is_validated(self) -> None:
        self.write_policy()
        target = self.root / "Assets" / "bad-size.webp"
        target.parent.mkdir()
        target.write_bytes(b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X" + (0).to_bytes(4, "little") + b"\x00" * 10)
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Assets/bad-size.webp\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIn("VP8X 헤더", payload["hookSpecificOutput"]["additionalContext"])

    def test_jpeg_without_early_dimensions_does_not_false_alarm(self) -> None:
        self.write_policy()
        target = self.root / "Assets" / "large-metadata.jpg"
        target.parent.mkdir()
        app_payload = b"x" * 65_533
        sof = b"\xff\xc0\x00\x11\x08\x00\x10\x00\x10" + b"\x00" * 10
        target.write_bytes(b"\xff\xd8\xff\xe1\xff\xff" + app_payload + sof + b"\xff\xd9")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Assets/large-metadata.jpg\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIsNone(payload)

    def test_broken_image_does_not_repeat_dimension_findings(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["assets"] = [{"path": "Assets/broken.png", "width": 64, "height": 64}]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        target = self.root / "Assets" / "broken.png"
        target.parent.mkdir()
        target.write_bytes(b"broken")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Assets/broken.png\n@@\n-x\n+y\n*** End Patch")
        )
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("PNG 헤더", context)
        self.assertNotIn("검증할 수 없습니다", context)

    def test_declared_art_asset_deletion_is_reported(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["assets"] = [{"path": "Assets/required.png", "width": 64, "height": 64}]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Delete File: Assets/required.png\n*** End Patch")
        )
        self.assertIn("선언된 아트 에셋", payload["hookSpecificOutput"]["additionalContext"])

    def test_boolean_is_not_used_as_byte_limit(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["max_file_bytes"] = True
        policy["checks"]["art"]["assets"] = [{"path": "Assets/source.psd", "max_bytes": True}]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        target = self.root / "Assets" / "source.psd"
        target.parent.mkdir()
        target.write_bytes(b"not a parsed image")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: Assets/source.psd\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIsNone(payload)

    def test_hidden_path_pattern_is_preserved(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"] = [".github/**"]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Update File: .github/workflows/test.yml\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIsNone(payload)

    def test_root_level_generated_directory_is_excluded(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("node_modules/**")
        policy["checks"]["exclude"].append("**/node_modules/**")
        decision.write_text(json.dumps(policy), encoding="utf-8")
        target = self.root / "node_modules" / "broken.json"
        target.parent.mkdir()
        target.write_text("{invalid", encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "*** Begin Patch\n*** Update File: node_modules/broken.json\n@@\n-x\n+y\n*** End Patch")
        )
        self.assertIsNone(payload)

    def test_post_hook_stops_at_total_read_budget(self) -> None:
        self.write_policy()
        client = self.root / "Client"
        client.mkdir()
        patch_lines = ["*** Begin Patch"]
        for index in range(17):
            relative = f"Client/file{index}.txt"
            (self.root / relative).write_bytes(b"x" * 1_048_576)
            patch_lines.extend((f"*** Update File: {relative}", "@@", "-x", "+y"))
        patch_lines.append("*** End Patch")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PostToolUse", "\n".join(patch_lines))
        )
        self.assertIn("한도", payload["hookSpecificOutput"]["additionalContext"])

    def test_malformed_input_fails_open(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not-json",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_oversized_pre_tool_event_is_blocked_before_json_parsing(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(HOOK), "PreToolUse"],
            input="x" * 8_388_609,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_merger_preserves_user_hook_and_is_idempotent(self) -> None:
        target = self.root / "hooks.json"
        target.write_text(
            json.dumps(
                {
                    "description": "user hooks",
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {"type": "command", "command": "python user_stop.py"}
                                ]
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(MERGER),
            "--source",
            str(HOOK_SOURCE),
            "--hook-script-source",
            str(HOOK),
            "--target",
            str(target),
            "--backup-suffix",
            "test",
        ]
        first = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(first.returncode, 0, first.stderr)
        merged = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(merged["description"], "user hooks")
        self.assertIn("Stop", merged["hooks"])
        self.assertEqual(len(merged["hooks"]["PreToolUse"]), 1)
        installed_handler = merged["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertNotIn("__GUPABAL", installed_handler["command"])
        self.assertNotIn("__GUPABAL", installed_handler["commandWindows"])
        self.assertIn("gupabal_hooks_", installed_handler["commandWindows"])
        installed_script = next((target.parent / "hooks").glob("gupabal_hooks_*.py"))
        self.assertEqual(installed_script.read_bytes(), HOOK.read_bytes())
        second = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Unchanged", second.stdout)

    def test_merger_rejects_invalid_existing_event_without_changes(self) -> None:
        target = self.root / "hooks.json"
        original = json.dumps({"hooks": {"PreToolUse": {"not": "a list"}}})
        target.write_text(original, encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(MERGER),
                "--source",
                str(HOOK_SOURCE),
                "--hook-script-source",
                str(HOOK),
                "--target",
                str(target),
                "--backup-suffix",
                "test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertFalse((target.parent / "hooks").exists())

    def test_merger_preserves_user_handler_and_removes_stale_managed_events(self) -> None:
        target = self.root / "hooks.json"
        target.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "^apply_patch$",
                                "hooks": [
                                    {"type": "command", "command": "python gupabal_hooks_old.py PreToolUse"},
                                    {"type": "command", "command": "python user_pre.py"},
                                ],
                            }
                        ],
                        "Stop": [
                            {
                                "hooks": [
                                    {"type": "command", "command": "python gupabal_hooks_old.py Stop"}
                                ]
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(MERGER),
                "--source",
                str(HOOK_SOURCE),
                "--hook-script-source",
                str(HOOK),
                "--target",
                str(target),
                "--backup-suffix",
                "test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        merged = json.loads(target.read_text(encoding="utf-8"))
        pre_handlers = [
            handler
            for group in merged["hooks"]["PreToolUse"]
            for handler in group.get("hooks", [])
        ]
        self.assertEqual(sum(handler.get("command") == "python user_pre.py" for handler in pre_handlers), 1)
        self.assertFalse(any("gupabal_hooks_old.py" in handler.get("command", "") for handler in pre_handlers))
        self.assertEqual(merged["hooks"]["Stop"], [])

    def test_hook_content_change_changes_trusted_command(self) -> None:
        target = self.root / "hooks.json"
        hook_copy = self.root / "source_hook.py"
        hook_copy.write_bytes(HOOK.read_bytes())

        def install() -> str:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MERGER),
                    "--source",
                    str(HOOK_SOURCE),
                    "--hook-script-source",
                    str(hook_copy),
                    "--target",
                    str(target),
                    "--backup-suffix",
                    "version",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = json.loads(target.read_text(encoding="utf-8"))
            return data["hooks"]["PreToolUse"][0]["hooks"][0]["commandWindows"]

        first_command = install()
        hook_copy.write_bytes(hook_copy.read_bytes() + b"\n# version change\n")
        second_command = install()
        self.assertNotEqual(first_command, second_command)
        self.assertEqual(len(list((target.parent / "hooks").glob("gupabal_hooks_*.py"))), 2)


if __name__ == "__main__":
    unittest.main()
