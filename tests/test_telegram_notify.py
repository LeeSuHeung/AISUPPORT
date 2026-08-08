from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
NOTIFIER_PATH = ROOT / ".codex" / "hooks" / "telegram_notify.py"
INSTALLER_PATH = ROOT / "scripts" / "install-telegram-notify.py"

SPEC = importlib.util.spec_from_file_location("telegram_notify", NOTIFIER_PATH)
assert SPEC and SPEC.loader
NOTIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NOTIFIER)


class TelegramNotifierTests(unittest.TestCase):
    def test_completion_message_does_not_include_conversation(self) -> None:
        payload = {
            "cwd": r"C:\Users\tester\secret-project",
            "input-messages": ["private request"],
            "last-assistant-message": "private result",
        }
        message = NOTIFIER.completion_message(payload)
        self.assertEqual(message, "Codex 작업 완료\n프로젝트: secret-project")
        self.assertNotIn("private", message)

    def test_notify_posts_message_and_preserves_delegate(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"ok": true, "result": {}}'
        payload = json.dumps(
            {
                "type": "agent-turn-complete",
                "cwd": r"C:\work\Newbie",
                "input-messages": ["do not send this"],
            }
        )
        environment = {
            "TELEGRAM_BOT_TOKEN": "123:test-token",
            "TELEGRAM_CHAT_ID": "456",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(NOTIFIER.urllib.request, "urlopen", return_value=response) as urlopen,
            mock.patch.object(NOTIFIER.subprocess, "run") as delegated,
        ):
            self.assertEqual(
                NOTIFIER.notify(["--delegate", "existing-notifier", payload]), 0
            )

        delegated.assert_called_once()
        self.assertEqual(delegated.call_args.args[0], ["existing-notifier", payload])
        request = urlopen.call_args.args[0]
        values = NOTIFIER.urllib.parse.parse_qs(request.data.decode("utf-8"))
        self.assertEqual(values["chat_id"], ["456"])
        self.assertEqual(values["text"], ["Codex 작업 완료\n프로젝트: Newbie"])
        self.assertNotIn("do not send this", request.data.decode("utf-8"))

    def test_missing_credentials_skips_telegram(self) -> None:
        payload = json.dumps({"type": "agent-turn-complete", "cwd": "/work/app"})
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.dict(
                os.environ, {"CODEX_HOME": temporary}, clear=True
            ),
            mock.patch.object(NOTIFIER.urllib.request, "urlopen") as urlopen,
        ):
            self.assertEqual(NOTIFIER.notify([payload]), 0)
        urlopen.assert_not_called()


class TelegramInstallerTests(unittest.TestCase):
    def test_install_preserves_comment_delimited_table_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / "codex-home"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            managed_block = (
                "# BEGIN AISUPPORT GLIF MCP\n"
                "[mcp_servers.glif]\n"
                'url = "https://glif.app/api/mcp"\n'
                'auth = "oauth"\n'
                'default_tools_approval_mode = "writes"\n'
                "# END AISUPPORT GLIF MCP\n"
            )
            config.write_text(managed_block, encoding="utf-8")

            install = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(INSTALLER_PATH),
                    "--codex-home",
                    str(codex_home),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            installed = config.read_text(encoding="utf-8")
            self.assertIn(managed_block, installed)
            self.assertLess(installed.index("notify ="), installed.index(managed_block))

    def test_install_verify_and_remove_preserve_existing_notifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / "codex-home"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            original = (
                'notify = ["existing-notifier", "turn-ended"]\n\n'
                "[features]\n"
                "hooks = false\n"
            )
            config.write_text(original, encoding="utf-8")

            install = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(INSTALLER_PATH),
                    "--codex-home",
                    str(codex_home),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            installed = config.read_text(encoding="utf-8")
            self.assertIn("telegram_notify_", installed)
            self.assertIn('"--delegate", "existing-notifier", "turn-ended"', installed)
            self.assertTrue(list(codex_home.glob("config.toml.backup-*")))

            verify = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(INSTALLER_PATH),
                    "--codex-home",
                    str(codex_home),
                    "--verify",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)

            remove = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(INSTALLER_PATH),
                    "--codex-home",
                    str(codex_home),
                    "--remove",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remove.returncode, 0, remove.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
