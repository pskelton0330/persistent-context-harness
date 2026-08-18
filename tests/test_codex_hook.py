#!/usr/bin/env python3
"""Tests for the Codex hook shim's output envelope.

The Codex integration is not exercised by an end-to-end CI job (it needs a
signed-in Codex and a per-hook trust step), so this guards the one thing that
silently broke priming once: emit() must hand Codex the SAME hook envelope the
shared hooks already produce — {"hookSpecificOutput": {...}} — unchanged.
Unwrapping it to a bare {"additionalContext": ...} made Codex ignore the injected
context entirely (SessionStart priming fired but reached the model as nothing).

    python tests/test_codex_hook.py
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "codex" / "hooks"))

import codex_hook  # noqa: E402


def emit_output(text: str) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        codex_hook.emit(text)
    return buf.getvalue().strip()


class TestEmit(unittest.TestCase):
    def test_hookspecificoutput_envelope_is_passed_through_unchanged(self) -> None:
        envelope = json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "CTX"}}
        )
        out = emit_output(envelope)
        # Must be the SAME envelope — not unwrapped. This is the priming fix.
        self.assertEqual(json.loads(out), json.loads(envelope))
        self.assertIn("hookSpecificOutput", json.loads(out))

    def test_decision_payload_passed_through(self) -> None:
        # The Stop / credential-guard shape must reach the host as-is.
        payload = json.dumps({"decision": "block", "reason": "secret"})
        self.assertEqual(json.loads(emit_output(payload)), json.loads(payload))

    def test_empty_output_emits_nothing(self) -> None:
        self.assertEqual(emit_output(""), "")

    def test_non_json_text_is_wrapped_not_dropped(self) -> None:
        # Plain text never comes from the shared hooks, but must not vanish.
        out = emit_output("plain note")
        self.assertTrue(out)
        self.assertIn("plain note", out)


if __name__ == "__main__":
    unittest.main()
