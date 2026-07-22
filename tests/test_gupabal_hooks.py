from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
HOOK = REPOSITORY / ".codex" / "hooks" / "gupabal_hooks.py"
MERGER = REPOSITORY / "scripts" / "merge_gupabal_hooks.py"
HOOK_SOURCE = REPOSITORY / ".codex" / "hooks" / "gupabal-hooks.template.json"
DECISION_TEMPLATE = REPOSITORY / ".agents" / "skills" / "gupabal-game" / "references" / "decision-template.json"
DECISION_POLICY = REPOSITORY / ".agents" / "skills" / "gupabal-game" / "references" / "decision-policy.md"
GUPABAL_SKILL = REPOSITORY / ".agents" / "skills" / "gupabal-game" / "SKILL.md"
GUPABAL_GUIDE = REPOSITORY / "GUPABAL_GAME.md"


def load_hook_module():
    spec = importlib.util.spec_from_file_location("gupabal_hooks_under_test", HOOK)
    if spec is None or spec.loader is None:
        raise RuntimeError("Hook 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_hook(self, event: dict) -> tuple[subprocess.CompletedProcess[str], dict | None]:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(HOOK)],
            input=json.dumps(event, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        payload = json.loads(completed.stdout) if completed.stdout.strip() else None
        return completed, payload

    def run_verifier(
        self, root: Path | None = None, *, include_repo_argument: bool = True
    ) -> tuple[subprocess.CompletedProcess[str], dict | None]:
        command = [sys.executable, "-X", "utf8", str(HOOK), "--verify-project"]
        if include_repo_argument:
            command.append(str(root or self.root))
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        payload = json.loads(completed.stdout) if completed.stdout.strip() else None
        return completed, payload

    @staticmethod
    def png_header(width: int, height: int) -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                len(data).to_bytes(4, "big")
                + kind
                + data
                + zlib.crc32(kind + data).to_bytes(4, "big")
            )

        ihdr = (
            width.to_bytes(4, "big")
            + height.to_bytes(4, "big")
            + b"\x08\x06\x00\x00\x00"
        )
        pixels = b"".join(b"\x00" + (b"\x00" * width * 4) for _ in range(height))
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(pixels))
            + chunk(b"IEND", b"")
        )

    @staticmethod
    def structural_jpeg(*, progressive: bool = False, scans: int = 1) -> bytes:
        sof_marker = b"\xc2" if progressive else b"\xc0"
        sof_payload = b"\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        sof = b"\xff" + sof_marker + b"\x00\x0b" + sof_payload
        sos_payload = b"\x01\x01\x00\x00\x3f\x00"
        sos = b"\xff\xda\x00\x08" + sos_payload + b"\x01"
        return b"\xff\xd8" + sof + (sos * scans) + b"\xff\xd9"

    @staticmethod
    def structural_gif(*, frames: int = 1, with_comment: bool = False) -> bytes:
        header = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
            b"\x00\x00\x00\xff\xff\xff"
        )
        comment = b"\x21\xfe\x03abc\x00" if with_comment else b""
        image = (
            b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00"
            b"\x02\x02\x44\x01\x00"
        )
        return header + comment + (image * frames) + b"\x3b"

    @staticmethod
    def empty_idat_png() -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                len(data).to_bytes(4, "big")
                + kind
                + data
                + zlib.crc32(kind + data).to_bytes(4, "big")
            )

        ihdr = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", b"")
            + chunk(b"IEND", b"")
        )

    @staticmethod
    def webp_chunk(kind: bytes, payload: bytes) -> bytes:
        padding = b"\x00" if len(payload) % 2 else b""
        return kind + len(payload).to_bytes(4, "little") + payload + padding

    @classmethod
    def riff_webp(cls, *chunks: tuple[bytes, bytes]) -> bytes:
        body = b"WEBP" + b"".join(
            cls.webp_chunk(kind, payload) for kind, payload in chunks
        )
        return b"RIFF" + len(body).to_bytes(4, "little") + body

    @staticmethod
    def vp8_header(first_partition_length: int = 1) -> bytes:
        frame_tag = ((first_partition_length << 5) | 0x10).to_bytes(3, "little")
        return frame_tag + b"\x9d\x01\x2a\x01\x00\x01\x00"

    @staticmethod
    def vp8l_header() -> bytes:
        return b"\x2f\x00\x00\x00\x00"

    @staticmethod
    def vp8x_header(*, animated: bool = False) -> bytes:
        flags = b"\x02" if animated else b"\x00"
        return flags + b"\x00\x00\x00" + b"\x00\x00\x00" + b"\x00\x00\x00"

    @staticmethod
    def contract_payload(policy: dict) -> dict:
        agreement = policy["agreement"]
        return {
            "schema_version": policy["schema_version"],
            "feature": policy["feature"],
            "revision": agreement["revision"],
            "summary": agreement["summary"],
            "invariants": agreement["invariants"],
            "spec_refs": sorted(
                agreement["spec_refs"], key=lambda item: item["path"]
            ),
            "ownership": policy["ownership"],
            "checks": policy["checks"],
        }

    @classmethod
    def bind_contract(cls, policy: dict) -> str:
        encoded = json.dumps(
            cls.contract_payload(policy),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        agreement = policy["agreement"]
        agreement["contract_digest"] = digest
        approval_status = (
            "AGREE" if agreement.get("status") in {"approved", "completed"} else "PENDING"
        )
        agreement["approvals"] = {
            role: {
                "status": approval_status,
                "revision": agreement["revision"],
                "contract_digest": digest,
            }
            for role in ("planner", "art", "client", "server")
        }
        return digest

    def write_policy(self, *, status: str = "approved") -> Path:
        decision = self.root / ".codex" / "gupabal" / "decision.json"
        decision.parent.mkdir(parents=True, exist_ok=True)
        policy = {
            "schema_version": 2,
            "enabled": True,
            "feature": "실제 테스트 대상",
            "planning_allow": [],
            "agreement": {
                "status": status,
                "revision": 1,
                "summary": "테스트 계약",
                "invariants": ["역할별 계약을 지킨다."],
                "spec_refs": [],
                "contract_digest": None,
                "approvals": {},
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
        }
        self.bind_contract(policy)
        decision.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
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

    def test_disabled_policy_is_silent_and_malformed_policy_blocks_implementation(self) -> None:
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
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("decision.json", output["permissionDecisionReason"])

        repair = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n@@\n-x\n+y\n*** End Patch",
        )
        _, repair_payload = self.run_hook(repair)
        self.assertIsNone(repair_payload)

    def test_nested_decision_does_not_shadow_git_root_policy(self) -> None:
        self.write_policy(status="planning")
        nested = self.root / "Client"
        nested_decision = nested / ".codex" / "gupabal" / "decision.json"
        nested_decision.parent.mkdir(parents=True)
        nested_decision.write_text(
            json.dumps({"schema_version": 1, "enabled": False}),
            encoding="utf-8",
        )

        _, payload = self.run_hook(
            self.patch_event(
                nested,
                "PreToolUse",
                "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
            )
        )
        self.assertEqual(
            payload["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_git_file_marks_worktree_root(self) -> None:
        (self.root / ".git").rmdir()
        (self.root / ".git").write_text(
            "gitdir: C:/example/worktrees/test\n", encoding="utf-8"
        )
        self.write_policy(status="planning")

        _, payload = self.run_hook(
            self.patch_event(
                self.root,
                "PreToolUse",
                "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
            )
        )
        self.assertEqual(
            payload["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_oversized_and_unsupported_decisions_block_except_small_repair(self) -> None:
        decision = self.write_policy()
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        repair = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n@@\n-x\n+y\n*** End Patch",
        )

        decision.write_bytes(b" " * 1_048_577)
        _, oversized_payload = self.run_hook(implementation)
        self.assertEqual(
            oversized_payload["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        _, oversized_repair = self.run_hook(repair)
        self.assertIsNone(oversized_repair)

        decision.write_text(
            json.dumps({"schema_version": 999, "enabled": True}),
            encoding="utf-8",
        )
        _, unsupported_payload = self.run_hook(implementation)
        self.assertEqual(
            unsupported_payload["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        _, unsupported_repair = self.run_hook(repair)
        self.assertIsNone(unsupported_repair)

    def test_invalid_decision_repair_rejects_delete_move_and_mixed_files(self) -> None:
        decision = self.write_policy()
        decision.write_text("{broken", encoding="utf-8")
        patches = (
            "*** Begin Patch\n*** Delete File: .codex/gupabal/decision.json\n*** End Patch",
            "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n*** Move to: decision-old.json\n@@\n-x\n+y\n*** End Patch",
            "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n@@\n-x\n+y\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        for patch in patches:
            with self.subTest(patch=patch.splitlines()[1]):
                _, payload = self.run_hook(
                    self.patch_event(self.root, "PreToolUse", patch)
                )
                self.assertEqual(
                    payload["hookSpecificOutput"]["permissionDecision"], "deny"
                )

    def test_symlink_decision_allows_delete_only_repair(self) -> None:
        decision = self.write_policy()
        target = self.root / "external-decision.json"
        target.write_text(decision.read_text(encoding="utf-8"), encoding="utf-8")
        decision.unlink()
        try:
            decision.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symbolic link를 만들 권한이 없습니다: {error}")

        patches = {
            "implementation": "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
            "update": "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n@@\n-x\n+y\n*** End Patch",
            "delete": "*** Begin Patch\n*** Delete File: .codex/gupabal/decision.json\n*** End Patch",
        }
        for name in ("implementation", "update"):
            with self.subTest(name=name):
                _, payload = self.run_hook(
                    self.patch_event(self.root, "PreToolUse", patches[name])
                )
                self.assertEqual(
                    payload["hookSpecificOutput"]["permissionDecision"], "deny"
                )

        _, delete_payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", patches["delete"])
        )
        self.assertIsNone(delete_payload)

    def test_schema_v2_contract_digest_matches_golden_value(self) -> None:
        module = load_hook_module()
        policy = {
            "schema_version": 2,
            "feature": "한글 기능",
            "agreement": {
                "revision": 3,
                "summary": "요약",
                "invariants": ["A", "B"],
                "spec_refs": [
                    {
                        "path": "z.md",
                        "owner": "server",
                        "schema_version": 1,
                        "sha256": "f" * 64,
                    },
                    {
                        "path": "a.md",
                        "owner": "client",
                        "schema_version": 2,
                        "sha256": "0" * 64,
                    },
                ],
            },
            "ownership": {
                "art": [],
                "client": ["a.md"],
                "server": ["z.md"],
                "shared": [],
            },
            "checks": {"exclude": []},
        }
        self.assertEqual(
            module.compute_contract_digest(policy),
            "7c38c03f168793aa6f4d7f0bd235b672e1b5e0c680e9aa30cfd959d59c6ba403",
        )
        policy["agreement"]["spec_refs"].reverse()
        self.assertEqual(
            module.compute_contract_digest(policy),
            "7c38c03f168793aa6f4d7f0bd235b672e1b5e0c680e9aa30cfd959d59c6ba403",
        )

    def test_schema_v2_template_and_guidance_require_bound_approvals(self) -> None:
        template = json.loads(DECISION_TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(template["schema_version"], 2)
        agreement = template["agreement"]
        self.assertEqual(agreement["revision"], 1)
        self.assertIsNone(agreement["contract_digest"])
        self.assertEqual(agreement["spec_refs"], [])
        for role in ("planner", "art", "client", "server"):
            self.assertEqual(
                agreement["approvals"][role],
                {"status": "PENDING", "revision": 1, "contract_digest": None},
            )

        policy_text = DECISION_POLICY.read_text(encoding="utf-8")
        skill_text = GUPABAL_SKILL.read_text(encoding="utf-8")
        for required in ("contract_digest", "spec_refs", "--verify-project"):
            self.assertIn(required, policy_text)
            self.assertIn(required, skill_text)

    def test_skill_uses_installer_verified_versioned_hook(self) -> None:
        skill_text = GUPABAL_SKILL.read_text(encoding="utf-8")

        self.assertNotIn("<CODEX_HOME>/hooks/gupabal_hooks.py", skill_text)
        for required in (
            "installer verify",
            "gupabal_hooks_<sha16>.py",
            "`OK `",
            "`MISMATCH`",
            "Python 3.10+",
            "`CODEX_HOME`",
            "`--target`",
            "`--agents-file`",
            "`--verify-project`",
            "Do not decode",
        ):
            self.assertIn(required, skill_text)

    def test_skill_and_policy_document_completed_and_cancelled_closures(self) -> None:
        skill_text = GUPABAL_SKILL.read_text(encoding="utf-8")
        policy_text = DECISION_POLICY.read_text(encoding="utf-8")

        self.assertIn("intentional cancellation", skill_text)
        self.assertIn("의도적인 취소", policy_text)
        for text in (skill_text, policy_text):
            for required in (
                "`enabled: false`",
                "`agreement.status: planning`",
                "`agreement.status: completed`",
                "`contract_digest: null`",
                "`unresolved: []`",
                "`PENDING`",
                "current revision",
            ):
                self.assertIn(required, text)

    def test_gupabal_guide_matches_fail_closed_and_runtime_policy(self) -> None:
        guide_text = GUPABAL_GUIDE.read_text(encoding="utf-8")

        self.assertNotIn(
            "합의 파일이 손상됐으면 작업을 강제로 막지는 않지만",
            guide_text,
        )
        for required in (
            "정확한 Git 루트",
            "fail-closed",
            "decision-only",
            "4 MiB",
            "schema v2",
            "contract_digest",
            "spec_refs",
            "정확히 한 owner",
            "source",
            "runtime",
            "`CODEX_HOME`",
            "`--target`",
            "`--agents-file`",
            "gupabal_hooks_<sha16>.py",
            "`checked: 0`",
            "exit `0`",
            "exit `1`",
            "exit `2`",
            "의도적인 취소",
            "Codex CLI의 `/hooks`",
            "decision-policy.md",
        ):
            self.assertIn(required, guide_text)

    def test_runtime_docs_require_integrated_then_explicit_python_verify(self) -> None:
        documents = (
            GUPABAL_SKILL.read_text(encoding="utf-8"),
            DECISION_POLICY.read_text(encoding="utf-8"),
            GUPABAL_GUIDE.read_text(encoding="utf-8"),
        )
        python_verify = (
            "<python> -X utf8 scripts/install_gupabal.py --target <exact> "
            "--agents-file <exact> --verify"
        )
        for document in documents:
            self.assertIn("install.ps1 -Verify", document)
            self.assertIn("install.sh --verify", document)
            self.assertIn(python_verify, document)
            self.assertLess(document.index("install.ps1 -Verify"), document.index(python_verify))
            self.assertLess(document.index("install.sh --verify"), document.index(python_verify))
            self.assertIn("PYTHONUTF8=0", document)
            self.assertIn("Unicode", document)
        self.assertIn("EncodedCommand", documents[0])

    def test_verify_project_success_is_deterministic_and_read_only(self) -> None:
        decision = self.write_policy()
        asset = self.root / "Assets" / "ui_button.png"
        asset.parent.mkdir()
        asset.write_bytes(self.png_header(2, 3))
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": 128,
            "naming_glob": "ui_*.png",
            "assets": [
                {
                    "path": "Assets/ui_button.png",
                    "width": 2,
                    "height": 3,
                    "max_bytes": 128,
                }
            ],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        before = {
            path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file()
        }

        first, first_payload = self.run_verifier()
        second, second_payload = self.run_verifier()
        after = {
            path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertTrue(first.stdout.endswith("\n"))
        self.assertEqual(first.stdout.count("\n"), 1)
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(
            first_payload,
            {
                "schema_version": 1,
                "status": "ok",
                "checked": 1,
                "findings": [],
                "errors": [],
            },
        )
        self.assertEqual(before, after)

    def test_verify_project_reports_missing_broken_size_and_name_findings(self) -> None:
        decision = self.write_policy()
        broken = self.root / "Assets" / "wrong.png"
        broken.parent.mkdir()
        broken.write_bytes(b"not a png and too large")
        wrong_size = self.root / "Assets" / "ui_size.png"
        wrong_size.write_bytes(self.png_header(2, 3))
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": 8,
            "naming_glob": "ui_*.png",
            "assets": [
                {"path": "Assets/missing.png", "width": 8, "height": 8},
                {"path": "Assets/wrong.png", "width": 4, "height": 4},
                {"path": "Assets/ui_size.png", "width": 9, "height": 10},
            ],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")

        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "findings")
        self.assertEqual(payload["checked"], 2)
        paths = [finding["path"] for finding in payload["findings"]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("Assets/missing.png", paths)
        joined = json.dumps(payload, ensure_ascii=False)
        self.assertIn("PNG 헤더", joined)
        self.assertIn("이름 규칙", joined)
        self.assertIn("8바이트", joined)
        self.assertIn("너비 2px", joined)
        self.assertIn("높이 3px", joined)

    def test_verify_project_honors_exclude_for_root_scan(self) -> None:
        decision = self.write_policy()
        included = self.root / "Assets" / "bad.png"
        ignored = self.root / "Assets" / "vendor" / "ignored.png"
        included.parent.mkdir()
        ignored.parent.mkdir()
        included.write_bytes(b"broken")
        ignored.write_bytes(b"broken")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")

        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 1)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn("Assets/bad.png", encoded)
        self.assertNotIn("Assets/vendor/ignored.png", encoded)
        self.assertEqual(payload["checked"], 1)

    def test_verify_project_does_not_overprune_single_character_exclude(self) -> None:
        decision = self.write_policy()
        broken = self.root / "Assets" / "cache" / "broken.png"
        broken.parent.mkdir(parents=True)
        broken.write_bytes(b"broken")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["exclude"] = ["Assets/cache/?"]
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 1)
        self.assertIn("Assets/cache/broken.png", json.dumps(payload, ensure_ascii=False))

    def test_verify_project_treats_exact_excluded_directory_as_subtree(self) -> None:
        decision = self.write_policy()
        hidden = self.root / "Assets" / "vendor" / "hidden.png"
        hidden.parent.mkdir(parents=True)
        hidden.write_bytes(self.png_header(1, 1))
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["exclude"] = ["Assets/vendor"]
        policy["checks"]["art"]["assets"] = [
            {"path": "Assets/vendor/hidden.png"}
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("checks.exclude", json.dumps(payload, ensure_ascii=False))

    def test_verify_project_rejects_root_scan_through_symlink_directory(self) -> None:
        decision = self.write_policy()
        external = self.root / "external-assets"
        external.mkdir()
        (external / "broken.png").write_bytes(b"broken")
        assets = self.root / "Assets"
        assets.mkdir()
        linked = assets / "linked"
        try:
            linked.symlink_to(external, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symbolic link를 만들 권한이 없습니다: {error}")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("symlink", json.dumps(payload, ensure_ascii=False))

    def test_link_detection_uses_legacy_windows_reparse_attributes(self) -> None:
        class LegacyWindowsPath:
            def is_symlink(self) -> bool:
                return False

            def lstat(self):
                return type(
                    "LegacyWindowsStat",
                    (),
                    {"st_file_attributes": stat.FILE_ATTRIBUTE_REPARSE_POINT},
                )()

        hook = load_hook_module()
        self.assertTrue(hook.is_link_or_junction(LegacyWindowsPath()))

    def test_verify_project_uses_exit_2_for_usage_policy_and_spec_errors(self) -> None:
        no_argument, no_argument_payload = self.run_verifier(
            include_repo_argument=False
        )
        self.assertEqual(no_argument.returncode, 2)
        self.assertEqual(no_argument_payload["status"], "error")

        no_policy, no_policy_payload = self.run_verifier()
        self.assertEqual(no_policy.returncode, 2)
        self.assertEqual(no_policy_payload["status"], "error")

        self.write_policy(status="planning")
        planning, planning_payload = self.run_verifier()
        self.assertEqual(planning.returncode, 2)
        self.assertEqual(planning_payload["status"], "error")

        decision = self.write_policy()
        spec_path = self.root / "Docs" / "contract.md"
        spec_path.parent.mkdir()
        spec_path.write_text("contract\n", encoding="utf-8")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("Docs/contract.md")
        policy["agreement"]["spec_refs"] = [
            {
                "path": "Docs/contract.md",
                "owner": "client",
                "schema_version": 1,
                "sha256": "0" * 64,
            }
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        invalid_spec, invalid_spec_payload = self.run_verifier()
        self.assertEqual(invalid_spec.returncode, 2)
        self.assertEqual(invalid_spec_payload["status"], "error")
        self.assertIn(
            "spec_refs", json.dumps(invalid_spec_payload, ensure_ascii=False)
        )

    def test_verify_project_rejects_unsupported_glob_syntax(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/[ab].png"],
            "max_file_bytes": None,
            "naming_glob": "ui_[ab].png",
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("glob", json.dumps(payload, ensure_ascii=False).lower())

    def test_verify_project_scans_more_than_post_hook_limit_once_each(self) -> None:
        decision = self.write_policy()
        assets = self.root / "Assets"
        assets.mkdir()
        for index in range(130):
            (assets / f"asset_{index:03}.bin").write_bytes(b"x")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**", "Assets/asset_*.bin"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [{"path": "Assets/asset_000.bin"}],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checked"], 130)

    def test_collector_does_not_enter_unrelated_directories(self) -> None:
        art = self.root / "Art"
        unrelated = self.root / "Unrelated"
        art.mkdir()
        unrelated.mkdir()
        (art / "icon.png").write_bytes(self.png_header(8, 8))
        (unrelated / "private.txt").write_text("unused", encoding="utf-8")
        hook = load_hook_module()
        original_iterdir = Path.iterdir

        def guarded_iterdir(path: Path):
            if path == unrelated:
                raise AssertionError("unrelated directory was scanned")
            return original_iterdir(path)

        with mock.patch.object(Path, "iterdir", guarded_iterdir):
            files, error = hook.collect_repository_files(
                self.root,
                {"checks": {"exclude": []}},
                ["Art/**"],
            )

        self.assertIsNone(error)
        self.assertEqual([relative for relative, _ in files], ["Art/icon.png"])

    def test_verify_project_enters_wildcard_directory_component(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["roots"] = ["Assets/ui_*/**"]
        self.bind_contract(policy)
        decision.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        target = self.root / "Assets" / "ui_icons" / "broken.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"not-a-png")

        completed, payload = self.run_verifier()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checked"], 1)
        self.assertEqual(payload["findings"][0]["path"], "Assets/ui_icons/broken.png")

    def test_verify_project_rejects_excluded_and_symlink_declared_assets(self) -> None:
        decision = self.write_policy()
        excluded_asset = self.root / "Assets" / "vendor" / "hidden.png"
        excluded_asset.parent.mkdir(parents=True)
        excluded_asset.write_bytes(self.png_header(1, 1))
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["assets"] = [
            {"path": "Assets/vendor/hidden.png"}
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        excluded_result, excluded_payload = self.run_verifier()
        self.assertEqual(excluded_result.returncode, 2)
        self.assertIn(
            "checks.exclude", json.dumps(excluded_payload, ensure_ascii=False)
        )

        decision = self.write_policy()
        target = self.root / "target.png"
        target.write_bytes(self.png_header(1, 1))
        linked = self.root / "Assets" / "linked.png"
        try:
            linked.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symbolic link를 만들 권한이 없습니다: {error}")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["assets"] = [{"path": "Assets/linked.png"}]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        symlink_result, symlink_payload = self.run_verifier()
        self.assertEqual(symlink_result.returncode, 2)
        self.assertIn("symlink", json.dumps(symlink_payload, ensure_ascii=False))

    def test_verify_project_rejects_declared_path_case_mismatch(self) -> None:
        decision = self.write_policy()
        asset = self.root / "Assets" / "Actual.png"
        asset.parent.mkdir()
        asset.write_bytes(self.png_header(1, 1))
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["assets"] = [{"path": "assets/actual.png"}]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("대소문자", json.dumps(payload, ensure_ascii=False))

    def test_verify_project_returns_2_when_dimensions_cannot_be_verified(self) -> None:
        decision = self.write_policy()
        unsupported = self.root / "Assets" / "source.psd"
        unsupported.parent.mkdir()
        unsupported.write_bytes(b"not an inspectable image")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"]["assets"] = [
            {"path": "Assets/source.psd", "width": 64, "height": 64}
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")

        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("검증할 수 없습니다", json.dumps(payload, ensure_ascii=False))

    def test_verify_project_does_not_wait_for_stdin(self) -> None:
        self.write_policy()
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                str(HOOK),
                "--verify-project",
                str(self.root),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            returncode = process.wait(timeout=5)
        finally:
            if process.stdin is not None:
                process.stdin.close()
        stdout = process.stdout.read() if process.stdout is not None else ""
        stderr = process.stderr.read() if process.stderr is not None else ""
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        self.assertEqual(returncode, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["status"], "ok")

    def test_verify_project_rejects_structurally_incomplete_image_headers(self) -> None:
        decision = self.write_policy()
        assets = self.root / "Assets"
        assets.mkdir()
        corrupt_png = bytearray(self.png_header(1, 1))
        corrupt_png[29] ^= 0x01
        (assets / "bad_crc.png").write_bytes(corrupt_png)
        (assets / "header_only.png").write_bytes(self.png_header(1, 1)[:33])
        (assets / "no_size.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (assets / "sof_only.jpg").write_bytes(
            b"\xff\xd8\xff\xc0\x00\x07\x08\x00\x01\x00\x01"
        )
        (assets / "short.gif").write_bytes(b"GIF89a\x01\x00\x01\x00")
        (assets / "header_only.gif").write_bytes(
            b"GIF89a\x01\x00\x01\x00\x00\x00\x00"
        )
        (assets / "valid_progressive.jpg").write_bytes(
            self.structural_jpeg(progressive=True, scans=2)
        )
        (assets / "valid_extensions.gif").write_bytes(
            self.structural_gif(frames=2, with_comment=True)
        )
        stub_webp = (
            b"RIFF"
            + (23).to_bytes(4, "little")
            + b"WEBPVP8X"
            + (10).to_bytes(4, "little")
            + b"\x00" * 10
            + b"x"
        )
        (assets / "stub.webp").write_bytes(stub_webp)
        empty_image_chunk_webp = (
            b"RIFF"
            + (30).to_bytes(4, "little")
            + b"WEBPVP8X"
            + (10).to_bytes(4, "little")
            + b"\x00" * 10
            + b"VP8 "
            + (0).to_bytes(4, "little")
        )
        (assets / "empty_chunk.webp").write_bytes(empty_image_chunk_webp)
        (assets / "comment.svg").write_text(
            '<svg width="1" height="1"><!-- <!DOCTYPE harmless> --></svg>',
            encoding="utf-8",
        )
        (assets / "upper.svg").write_text(
            '<SVG width="1" height="1"></SVG>', encoding="utf-8"
        )
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")

        completed, payload = self.run_verifier()
        self.assertEqual(completed.returncode, 1)
        finding_paths = sorted(
            {finding["path"] for finding in payload["findings"]}
        )
        self.assertEqual(
            finding_paths,
            [
                "Assets/bad_crc.png",
                "Assets/empty_chunk.webp",
                "Assets/header_only.gif",
                "Assets/header_only.png",
                "Assets/no_size.jpg",
                "Assets/short.gif",
                "Assets/sof_only.jpg",
                "Assets/stub.webp",
                "Assets/upper.svg",
            ],
        )
        self.assertNotIn(
            "Assets/comment.svg", json.dumps(payload, ensure_ascii=False)
        )

    def test_verify_project_rejects_header_only_png_and_webp_payloads(self) -> None:
        decision = self.write_policy()
        assets = self.root / "Assets"
        assets.mkdir()
        (assets / "empty_idat.png").write_bytes(self.empty_idat_png())
        (assets / "header_only_vp8.webp").write_bytes(
            self.riff_webp((b"VP8 ", self.vp8_header()))
        )
        (assets / "header_only_vp8l.webp").write_bytes(
            self.riff_webp((b"VP8L", self.vp8l_header()))
        )
        (assets / "header_only_anmf.webp").write_bytes(
            self.riff_webp(
                (b"VP8X", self.vp8x_header(animated=True)),
                (b"ANMF", b"\x00" * 16),
            )
        )
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")

        completed, payload = self.run_verifier()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(
            sorted(finding["path"] for finding in payload["findings"]),
            [
                "Assets/empty_idat.png",
                "Assets/header_only_anmf.webp",
                "Assets/header_only_vp8.webp",
                "Assets/header_only_vp8l.webp",
            ],
        )

    def test_verify_project_accepts_structural_webp_payloads(self) -> None:
        decision = self.write_policy()
        assets = self.root / "Assets"
        assets.mkdir()
        (assets / "valid_vp8.webp").write_bytes(
            self.riff_webp((b"VP8 ", self.vp8_header() + b"\x00"))
        )
        (assets / "valid_vp8l.webp").write_bytes(
            self.riff_webp((b"VP8L", self.vp8l_header() + b"\x00"))
        )
        animated_payload = b"\x00" * 16 + self.webp_chunk(
            b"VP8L", self.vp8l_header() + b"\x00"
        )
        (assets / "valid_animated.webp").write_bytes(
            self.riff_webp(
                (b"VP8X", self.vp8x_header(animated=True)),
                (b"ANIM", b"\x00" * 6),
                (b"ANMF", animated_payload),
            )
        )
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["checks"]["art"] = {
            "roots": ["Assets/**"],
            "max_file_bytes": None,
            "naming_glob": None,
            "assets": [],
        }
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")

        completed, payload = self.run_verifier()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checked"], 3)

    def test_svg_parser_is_loaded_lazily(self) -> None:
        source = HOOK.read_text(encoding="utf-8")
        self.assertNotIn("import xml.etree.ElementTree", source)
        self.assertIn("from xml.etree import ElementTree", source)

    def test_active_v1_requires_decision_only_migration_but_disabled_v1_is_silent(self) -> None:
        decision = self.root / ".codex" / "gupabal" / "decision.json"
        decision.parent.mkdir(parents=True)
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        decision.write_text(
            json.dumps({"schema_version": 1, "enabled": False}), encoding="utf-8"
        )
        _, disabled_payload = self.run_hook(implementation)
        self.assertIsNone(disabled_payload)

        decision.write_text(
            json.dumps({"schema_version": 1, "enabled": True}), encoding="utf-8"
        )
        _, active_payload = self.run_hook(implementation)
        self.assertEqual(
            active_payload["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        migration = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Update File: .codex/gupabal/decision.json\n@@\n-  \"schema_version\": 1\n+  \"schema_version\": 2\n*** End Patch",
        )
        _, migration_payload = self.run_hook(migration)
        self.assertIsNone(migration_payload)

    def test_only_exact_false_disables_a_supported_policy(self) -> None:
        decision = self.root / ".codex" / "gupabal" / "decision.json"
        decision.parent.mkdir(parents=True)
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        invalid_policies = (
            {"schema_version": 2},
            {"schema_version": 2, "enabled": 1},
            {"schema_version": 2, "enabled": "false"},
            {"schema_version": 2, "enabled": None},
            {"schema_version": True, "enabled": False},
            {"schema_version": 1.0, "enabled": False},
            {"schema_version": 2.0, "enabled": False},
            {"schema_version": 99, "enabled": False},
        )
        for policy in invalid_policies:
            with self.subTest(policy=policy):
                decision.write_text(json.dumps(policy), encoding="utf-8")
                _, payload = self.run_hook(implementation)
                self.assertIsNotNone(payload)
                self.assertEqual(
                    payload["hookSpecificOutput"]["permissionDecision"], "deny"
                )

        decision.write_text(
            json.dumps({"schema_version": 2, "enabled": False}), encoding="utf-8"
        )
        _, disabled_payload = self.run_hook(implementation)
        self.assertIsNone(disabled_payload)

    def test_stale_contract_and_stale_role_approval_are_denied(self) -> None:
        decision = self.write_policy()
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        _, valid_payload = self.run_hook(implementation)
        self.assertIsNone(valid_payload)

        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["agreement"]["summary"] = "승인 뒤 바뀐 계약"
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, stale_contract = self.run_hook(implementation)
        stale_reason = stale_contract["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("contract_digest", stale_reason)

        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["agreement"]["approvals"]["planner"]["revision"] = 0
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, stale_approval = self.run_hook(implementation)
        stale_reason = stale_approval["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("planner", stale_reason)
        self.assertIn("revision", stale_reason)

    def test_schema_v2_requires_revision_summary_and_invariants(self) -> None:
        decision = self.write_policy()
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        cases = (
            ("revision", False),
            ("summary", ""),
            ("invariants", []),
        )
        for field, value in cases:
            with self.subTest(field=field):
                policy = json.loads(decision.read_text(encoding="utf-8"))
                policy["agreement"][field] = value
                self.bind_contract(policy)
                decision.write_text(json.dumps(policy), encoding="utf-8")
                _, payload = self.run_hook(implementation)
                self.assertIn(
                    field,
                    payload["hookSpecificOutput"]["permissionDecisionReason"],
                )
                decision = self.write_policy()

    def test_spec_ref_normalizes_line_endings_and_detects_content_change(self) -> None:
        decision = self.write_policy()
        spec_path = self.root / "Docs" / "contract.md"
        spec_path.parent.mkdir()
        spec_path.write_bytes(b"alpha\r\nbeta\r\n")
        normalized_hash = hashlib.sha256(b"alpha\nbeta\n").hexdigest()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("Docs/contract.md")
        policy["agreement"]["spec_refs"] = [
            {
                "path": "Docs/contract.md",
                "owner": "client",
                "schema_version": 1,
                "sha256": normalized_hash,
            }
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        _, valid_payload = self.run_hook(implementation)
        self.assertIsNone(valid_payload)

        spec_path.write_text("changed\n", encoding="utf-8")
        _, changed_payload = self.run_hook(implementation)
        reason = changed_payload["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("spec_refs", reason)
        self.assertIn("sha256", reason)

    def test_invalid_spec_refs_are_denied(self) -> None:
        decision = self.write_policy()
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("Docs/missing.md")
        policy["agreement"]["spec_refs"] = [
            {
                "path": "Docs/missing.md",
                "owner": "client",
                "schema_version": 1,
                "sha256": "0" * 64,
            }
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, missing_payload = self.run_hook(implementation)
        self.assertIn(
            "spec_refs",
            missing_payload["hookSpecificOutput"]["permissionDecisionReason"],
        )

        spec_path = self.root / "Docs" / "owned.md"
        spec_path.parent.mkdir(exist_ok=True)
        spec_path.write_text("contract\n", encoding="utf-8")
        policy = json.loads(self.write_policy().read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("Docs/owned.md")
        policy["agreement"]["spec_refs"] = [
            {
                "path": "Docs/owned.md",
                "owner": "server",
                "schema_version": 1,
                "sha256": hashlib.sha256(b"contract\n").hexdigest(),
            }
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, owner_payload = self.run_hook(implementation)
        owner_reason = owner_payload["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("spec_refs", owner_reason)
        self.assertIn("owner", owner_reason)

    def test_spec_ref_symlink_is_denied(self) -> None:
        decision = self.write_policy()
        target = self.root / "contract-target.md"
        target.write_text("contract\n", encoding="utf-8")
        linked = self.root / "Docs" / "contract.md"
        linked.parent.mkdir()
        try:
            linked.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symbolic link를 만들 권한이 없습니다: {error}")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("Docs/contract.md")
        policy["agreement"]["spec_refs"] = [
            {
                "path": "Docs/contract.md",
                "owner": "client",
                "schema_version": 1,
                "sha256": hashlib.sha256(b"contract\n").hexdigest(),
            }
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(
                self.root,
                "PreToolUse",
                "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
            )
        )
        reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("spec_refs", reason)
        self.assertIn("symlink", reason)

    def test_duplicate_json_keys_nan_and_unknown_contract_fields_are_denied(self) -> None:
        decision = self.write_policy()
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        invalid_documents = (
            '{"schema_version":2,"schema_version":2,"enabled":true}',
            '{"schema_version":2,"enabled":true,"feature":NaN}',
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                decision.write_text(document, encoding="utf-8")
                _, payload = self.run_hook(implementation)
                self.assertEqual(
                    payload["hookSpecificOutput"]["permissionDecision"], "deny"
                )

        for location, field in (("top", "unexpected"), ("agreement", "retry_policy")):
            with self.subTest(location=location):
                decision = self.write_policy()
                policy = json.loads(decision.read_text(encoding="utf-8"))
                if location == "top":
                    policy[field] = "not covered by digest"
                else:
                    policy["agreement"][field] = "not covered by digest"
                decision.write_text(json.dumps(policy), encoding="utf-8")
                _, payload = self.run_hook(implementation)
                self.assertIn(
                    "허용되지 않은 필드",
                    payload["hookSpecificOutput"]["permissionDecisionReason"],
                )

        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["agreement"]["approvals"]["observer"] = {
            "status": "AGREE",
            "revision": 1,
            "contract_digest": policy["agreement"]["contract_digest"],
        }
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, extra_role = self.run_hook(implementation)
        self.assertIn(
            "approvals",
            extra_role["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_approved_spec_patch_is_blocked_until_contract_is_reopened(self) -> None:
        decision = self.write_policy()
        spec_path = self.root / "Docs" / "contract.md"
        spec_path.parent.mkdir()
        spec_path.write_text("contract\n", encoding="utf-8")
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"].append("Docs/contract.md")
        policy["agreement"]["spec_refs"] = [
            {
                "path": "Docs/contract.md",
                "owner": "client",
                "schema_version": 1,
                "sha256": hashlib.sha256(b"contract\n").hexdigest(),
            }
        ]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        spec_patch = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Update File: Docs/contract.md\n@@\n-contract\n+changed\n*** End Patch",
        )
        _, approved_payload = self.run_hook(spec_patch)
        reason = approved_payload["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("spec_refs", reason)
        self.assertIn("revision", reason)

        policy["agreement"]["status"] = "planning"
        policy["agreement"]["revision"] = 2
        policy["agreement"]["contract_digest"] = None
        policy["agreement"]["approvals"] = {
            role: {"status": "PENDING", "revision": 2, "contract_digest": None}
            for role in ("planner", "art", "client", "server")
        }
        policy["planning_allow"] = ["Docs/contract.md"]
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, planning_payload = self.run_hook(spec_patch)
        self.assertIsNone(planning_payload)

    def test_completed_approval_snapshot_cannot_be_reactivated(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["enabled"] = False
        policy["agreement"]["status"] = "completed"
        policy["agreement"]["contract_digest"] = None
        policy["agreement"]["approvals"] = {
            role: {
                "status": "PENDING",
                "revision": policy["agreement"]["revision"],
                "contract_digest": None,
            }
            for role in ("planner", "art", "client", "server")
        }
        decision.write_text(json.dumps(policy), encoding="utf-8")
        implementation = self.patch_event(
            self.root,
            "PreToolUse",
            "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
        )
        _, completed_payload = self.run_hook(implementation)
        self.assertIsNone(completed_payload)

        policy["enabled"] = True
        policy["agreement"]["status"] = "approved"
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, replay_payload = self.run_hook(implementation)
        self.assertEqual(
            replay_payload["hookSpecificOutput"]["permissionDecision"], "deny"
        )

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

    def test_unowned_file_is_denied(self) -> None:
        self.write_policy()
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Other/a.txt\n+x\n*** End Patch")
        )
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("소유 역할", output["permissionDecisionReason"])

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
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: Client/settings.json\n@@\n-x\n+y\n*** End Patch"
        _, pre_payload = self.run_hook(self.patch_event(self.root, "PreToolUse", patch))
        pre_output = pre_payload["hookSpecificOutput"]
        self.assertEqual(pre_output["permissionDecision"], "deny")
        self.assertIn("소유 역할", pre_output["permissionDecisionReason"])

        target = self.root / "Client" / "settings.json"
        target.parent.mkdir()
        target.write_text("{invalid", encoding="utf-8")
        _, post_payload = self.run_hook(self.patch_event(self.root, "PostToolUse", patch))
        self.assertIn("JSON 문법 오류", post_payload["hookSpecificOutput"]["additionalContext"])

    def test_overlapping_owners_are_denied(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["server"] = ["Client/**", "Server/**"]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(self.root, "PreToolUse", "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch")
        )
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("둘 이상", output["permissionDecisionReason"])

    def test_overlapping_patterns_for_same_owner_pass(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"]["client"] = ["Client/**", "Client/UI/**"]
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(
                self.root,
                "PreToolUse",
                "*** Begin Patch\n*** Add File: Client/UI/a.cs\n+x\n*** End Patch",
            )
        )
        self.assertIsNone(payload)

    def test_empty_ownership_is_denied(self) -> None:
        decision = self.write_policy()
        policy = json.loads(decision.read_text(encoding="utf-8"))
        policy["ownership"] = {"art": [], "client": [], "server": [], "shared": []}
        self.bind_contract(policy)
        decision.write_text(json.dumps(policy), encoding="utf-8")
        _, payload = self.run_hook(
            self.patch_event(
                self.root,
                "PreToolUse",
                "*** Begin Patch\n*** Add File: Client/a.cs\n+x\n*** End Patch",
            )
        )
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("소유 역할", output["permissionDecisionReason"])

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
        self.bind_contract(policy)
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
        self.bind_contract(policy)
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
        self.bind_contract(policy)
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
        self.bind_contract(policy)
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
        self.bind_contract(policy)
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
        for raw_input in ("not-json", "[]"):
            with self.subTest(raw_input=raw_input):
                completed = subprocess.run(
                    [sys.executable, "-X", "utf8", str(HOOK), "PreToolUse"],
                    input=raw_input,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(completed.returncode, 0)
                payload = json.loads(completed.stdout)
                output = payload["hookSpecificOutput"]
                self.assertEqual(output["hookEventName"], "PreToolUse")
                self.assertNotIn("permissionDecision", output)
                self.assertIn("차단하지", output["additionalContext"])

    def test_oversized_pre_tool_event_is_blocked_before_json_parsing(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(HOOK), "PreToolUse"],
            input="x" * 8_388_609,
            capture_output=True,
            text=True,
            encoding="utf-8",
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
        self.assertIn("powershell.exe", installed_handler["commandWindows"])
        self.assertIn("-EncodedCommand ", installed_handler["commandWindows"])
        self.assertNotIn("gupabal_hooks_", installed_handler["commandWindows"])
        self.assertIn("-X utf8", installed_handler["command"])
        self.assertNotIn("-X utf8", installed_handler["commandWindows"])
        installed_script = next((target.parent / "hooks").glob("gupabal_hooks_*.py"))
        self.assertEqual(installed_script.read_bytes(), HOOK.read_bytes())
        second = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Unchanged", second.stdout)

    def test_merger_dry_run_does_not_create_config_or_script(self) -> None:
        target = self.root / "config" / "hooks.json"
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
                "dry-run",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("INSTALL", completed.stdout)
        self.assertIn("UPDATE", completed.stdout)
        self.assertFalse(target.exists())
        self.assertFalse((target.parent / "hooks").exists())

    def test_merger_verify_succeeds_after_install(self) -> None:
        target = self.root / "hooks.json"
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
            "verify",
        ]
        installed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(installed.returncode, 0, installed.stderr)

        verified = subprocess.run(command + ["--verify"], capture_output=True, text=True, check=False)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(verified.stdout.count("OK "), 2)

    def test_merger_verify_fails_when_installed_script_differs(self) -> None:
        target = self.root / "hooks.json"
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
            "verify-script",
        ]
        installed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        installed_script = next((target.parent / "hooks").glob("gupabal_hooks_*.py"))
        installed_script.write_bytes(installed_script.read_bytes() + b"\n# tampered\n")

        verified = subprocess.run(command + ["--verify"], capture_output=True, text=True, check=False)
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn(f"MISMATCH {installed_script.resolve()}", verified.stdout)

    def test_merger_verify_fails_when_config_differs(self) -> None:
        target = self.root / "hooks.json"
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
            "verify-config",
        ]
        installed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        config = json.loads(target.read_text(encoding="utf-8"))
        config["hooks"]["PreToolUse"] = []
        target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        verified = subprocess.run(command + ["--verify"], capture_output=True, text=True, check=False)
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn(f"MISMATCH {target.resolve()}", verified.stdout)

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
        stale_script = target.parent / "hooks" / "gupabal_hooks_deadbeefdeadbeef.py"
        stale_pre_command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(stale_script))} PreToolUse"
        )
        stale_stop_command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(stale_script))} Stop"
        )
        user_command = "python user_gupabal_hooks_helper.py"
        target.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "^apply_patch$",
                                "hooks": [
                                    {"type": "command", "command": stale_pre_command},
                                    {"type": "command", "command": "python user_pre.py"},
                                    {"type": "command", "command": user_command},
                                ],
                            }
                        ],
                        "Stop": [
                            {
                                "hooks": [
                                    {"type": "command", "command": stale_stop_command}
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
        self.assertEqual(sum(handler.get("command") == user_command for handler in pre_handlers), 1)
        self.assertFalse(any(handler.get("command") == stale_pre_command for handler in pre_handlers))
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
