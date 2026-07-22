from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
MERGER = REPOSITORY / "scripts" / "merge_gupabal_hooks.py"
HOOK = REPOSITORY / ".codex" / "hooks" / "gupabal_hooks.py"
HOOK_TEMPLATE = REPOSITORY / ".codex" / "hooks" / "gupabal-hooks.template.json"


@unittest.skipUnless(os.name == "nt", "Windows cmd.exe contract test")
class GupabalWindowsCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_merger(
        self, target: Path, hook_source: Path = HOOK
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        return subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(MERGER),
                "--source",
                str(HOOK_TEMPLATE),
                "--hook-script-source",
                str(hook_source),
                "--target",
                str(target),
                "--backup-suffix",
                "windows-test",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )

    @staticmethod
    def pre_tool_command(target: Path) -> str:
        configuration = json.loads(target.read_text(encoding="utf-8"))
        return configuration["hooks"]["PreToolUse"][0]["hooks"][0][
            "commandWindows"
        ]

    def test_generated_command_runs_once_from_cmd_metacharacter_path(self) -> None:
        target = (
            self.root
            / "A!GUPABAL_BANG_TEST!B %PATH% & (한글🚀) O'Brien"
            / "hooks.json"
        )
        counter = self.root / "invocations.txt"
        probe = self.root / "probe hook.py"
        probe.write_text(
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            f"counter = Path({str(counter)!r})\n"
            "if json.loads(sys.stdin.read()) != {'probe': '한글🚀'}:\n"
            "    raise SystemExit(9)\n"
            "if sys.argv[1:] != ['PreToolUse']:\n"
            "    raise SystemExit(10)\n"
            "value = int(counter.read_text(encoding='utf-8')) if counter.exists() else 0\n"
            "counter.write_text(str(value + 1), encoding='utf-8')\n",
            encoding="utf-8",
        )
        installed = self.run_merger(target, probe)
        self.assertEqual(installed.returncode, 0, installed.stderr)

        windows_command = self.pre_tool_command(target)
        self.assertNotIn("GUPABAL_BANG_TEST", windows_command)
        self.assertNotIn("%PATH%", windows_command)
        self.assertNotIn("한글", windows_command)
        command_processor = os.environ.get("COMSPEC", "cmd.exe")
        environment = os.environ.copy()
        environment["GUPABAL_BANG_TEST"] = "EXPANDED"
        for expected_count, delayed_expansion in enumerate(("OFF", "ON"), start=1):
            completed = subprocess.run(
                [
                    command_processor,
                    "/D",
                    "/S",
                    f"/V:{delayed_expansion}",
                    "/C",
                    windows_command,
                ],
                input=json.dumps({"probe": "한글🚀"}, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"command: {windows_command}\nstdout: {completed.stdout}\nstderr: {completed.stderr}",
            )
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            self.assertEqual(
                counter.read_text(encoding="utf-8"), str(expected_count)
            )

    def test_generated_command_propagates_hook_exit_code(self) -> None:
        target = self.root / "exit-code" / "hooks.json"
        probe = self.root / "exit hook.py"
        probe.write_text("raise SystemExit(37)\n", encoding="utf-8")
        installed = self.run_merger(target, probe)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        windows_command = self.pre_tool_command(target)
        command_processor = os.environ.get("COMSPEC", "cmd.exe")

        completed = subprocess.run(
            [command_processor, "/D", "/S", "/V:ON", "/C", windows_command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(completed.returncode, 37, completed.stderr)


if __name__ == "__main__":
    unittest.main()
