#!/usr/bin/env python3
"""Tests for install/merge-claude-settings.py.

This is the only install step that modifies a file the user already owns and has
probably customised. A bug here costs someone their Claude Code configuration,
so the blast radius is pinned down by test rather than by inspection.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "install" / "merge-claude-settings.py"


def run(settings: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--settings", str(settings), *args],
        capture_output=True, text=True,
    )


class MergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = Path(self._tmp.name) / "settings.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, data: dict) -> None:
        self.settings.write_text(json.dumps(data), encoding="utf-8")

    def read(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def commands(self) -> list[str]:
        return [
            hook["command"]
            for entries in self.read().get("hooks", {}).values()
            for entry in entries
            for hook in entry.get("hooks", [])
        ]

    def ours(self) -> int:
        # The generated commands spell the path with forward slashes
        # (Path.as_posix()), so on Windows str(ROOT) — which uses backslashes —
        # would never match. Check both spellings, mirroring is_ours().
        needles = (str(ROOT), ROOT.as_posix())
        return sum(any(n in c for n in needles) for c in self.commands())

    # -- core guarantees --------------------------------------------------

    def test_preserves_every_other_setting(self) -> None:
        self.write({
            "model": "opus",
            "permissions": {"allow": ["Bash"]},
            "someFutureKey": {"nested": [1, 2]},
        })
        self.assertEqual(run(self.settings).returncode, 0)
        data = self.read()
        self.assertEqual(data["model"], "opus")
        self.assertEqual(data["permissions"], {"allow": ["Bash"]})
        self.assertEqual(data["someFutureKey"], {"nested": [1, 2]})

    def test_keeps_hooks_belonging_to_others(self) -> None:
        self.write({"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "say done"}]}],
            "Notification": [{"hooks": [{"type": "command", "command": "say hi"}]}],
        }})
        run(self.settings)
        self.assertIn("say done", self.commands())
        self.assertIn("say hi", self.commands())

    def test_installs_all_hook_events(self) -> None:
        self.write({})
        run(self.settings)
        for event in ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"):
            self.assertIn(event, self.read()["hooks"], event)

    def test_idempotent(self) -> None:
        self.write({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]}})
        for _ in range(4):
            run(self.settings)
        self.assertEqual(self.ours(), 5)
        self.assertEqual(sum(c == "say done" for c in self.commands()), 1)

    def test_uninstall_removes_only_ours(self) -> None:
        self.write({"model": "opus", "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]}})
        run(self.settings)
        run(self.settings, "--uninstall")
        self.assertEqual(self.ours(), 0)
        self.assertIn("say done", self.commands())
        self.assertEqual(self.read()["model"], "opus")

    def test_dry_run_changes_nothing(self) -> None:
        self.write({"model": "opus"})
        before = self.settings.read_text()
        result = run(self.settings, "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.settings.read_text(), before)

    def test_writes_a_backup(self) -> None:
        self.write({"model": "opus"})
        run(self.settings)
        backups = list(self.settings.parent.glob("settings.json.backup-*"))
        self.assertTrue(backups, "no backup written")
        self.assertEqual(json.loads(backups[0].read_text())["model"], "opus")

    # -- refusing to act on nonsense --------------------------------------

    def test_refuses_invalid_json(self) -> None:
        self.settings.write_text("not json", encoding="utf-8")
        self.assertNotEqual(run(self.settings).returncode, 0)
        self.assertEqual(self.settings.read_text(), "not json")

    def test_refuses_non_object(self) -> None:
        self.settings.write_text("[1,2,3]", encoding="utf-8")
        self.assertNotEqual(run(self.settings).returncode, 0)

    def test_handles_malformed_hooks_value(self) -> None:
        self.write({"hooks": "nonsense", "model": "opus"})
        self.assertEqual(run(self.settings).returncode, 0)
        self.assertEqual(self.read()["model"], "opus")

    def test_creates_file_when_absent(self) -> None:
        self.assertFalse(self.settings.exists())
        self.assertEqual(run(self.settings).returncode, 0)
        self.assertTrue(self.settings.exists())
        self.assertEqual(self.ours(), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
