#!/usr/bin/env python3
"""Tests for lib/harness_config.py — the path/scope foundation.

Every other component resolves its paths through this module, so a regression
here silently misroutes the whole harness. Run with:

    python3 tests/test_config.py

Standard library only, so it runs under any python3 without the venv extras.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness_config import (  # noqa: E402
    HarnessConfig,
    in_project_scope,
    is_excluded,
    should_retrieve,
    under,
)


class ConfigTestCase(unittest.TestCase):
    """Builds a throwaway harness root with a real config file."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "config").mkdir()
        for sub in ("mykb/lessons", "mykb/reference", "proj-a/sub/deep", "proj-b", "elsewhere"):
            (self.root / sub).mkdir(parents=True)
        # Keep the environment from leaking into assertions.
        self._saved = {
            k: os.environ.pop(k)
            for k in list(os.environ)
            if k.startswith("KB_")
        }

    def tearDown(self) -> None:
        os.environ.update(self._saved)
        self._tmp.cleanup()

    def write_config(self, body: str) -> HarnessConfig:
        (self.root / "config" / "harness.env").write_text(body, encoding="utf-8")
        return HarnessConfig(root=self.root)

    def write_roots_json(self, body: str, kb: str = "mykb") -> None:
        """Write project-roots.json BEFORE constructing the config.

        HarnessConfig snapshots this file once at construction (so a single
        scope verdict cannot be assembled from two different file versions), so
        writing it afterwards would not be seen.
        """
        reference = self.root / kb / "reference"
        reference.mkdir(parents=True, exist_ok=True)
        (reference / "project-roots.json").write_text(body, encoding="utf-8")


class TestEnvFileParsing(ConfigTestCase):
    def test_quoted_value_with_trailing_comment(self) -> None:
        """A comment after a quoted value must not leak into the value."""
        cfg = self.write_config('KB_WEEKLY_AGENT="claude --model opus"   # note\n')
        self.assertEqual(cfg.weekly_agent, "claude --model opus")

    def test_export_prefix_is_accepted(self) -> None:
        cfg = self.write_config('export KB_WEEKLY_AGENT="codex exec"\n')
        self.assertEqual(cfg.weekly_agent, "codex exec")

    def test_unquoted_value_and_comment(self) -> None:
        cfg = self.write_config("KB_EMBED_MODEL=my-embedder # inline\n")
        self.assertEqual(cfg.embed_model, "my-embedder")

    def test_shell_defaulted_form_is_not_silently_misread(self) -> None:
        """The `${KEY:-default}` form is NOT part of the grammar any more.

        It must not be silently treated as the default value; it warns and is
        taken literally, so a stale config is visible rather than surprising.
        """
        cfg = self.write_config('KB_RETRIEVER="${KB_RETRIEVER:-semantic}"\n')
        self.assertNotEqual(cfg.retriever, "semantic")
        self.assertTrue(any("$" in w for w in cfg.warnings))

    def test_env_still_wins_over_file(self) -> None:
        os.environ["KB_RETRIEVER"] = "keyword"
        cfg = self.write_config("KB_RETRIEVER=semantic\n")
        self.assertEqual(cfg.retriever, "keyword")

    def test_comments_and_blank_lines_ignored(self) -> None:
        cfg = self.write_config("# heading\n\n   \n# KB_EMBED_MODEL=ignored\n")
        self.assertEqual(cfg.embed_model, "nomic-embed-text")

    def test_tilde_and_vars_expand(self) -> None:
        cfg = self.write_config('KB_ROOT="$HOME/somewhere"\n')
        self.assertEqual(cfg.kb_root, Path(os.path.expanduser("~/somewhere")).resolve())

    def test_embed_dim_is_int(self) -> None:
        cfg = self.write_config("KB_EMBED_DIM=1024\n")
        self.assertEqual(cfg.embed_dim, 1024)
        self.assertIsInstance(cfg.embed_dim, int)

    def test_missing_config_file_yields_defaults(self) -> None:
        cfg = HarnessConfig(root=self.root)
        self.assertEqual(cfg.kb_root, (self.root / "wiki").resolve())
        self.assertEqual(cfg.state_dir, (self.root / "state").resolve())

    def test_env_beats_config_file(self) -> None:
        os.environ["KB_EMBED_MODEL"] = "from-env"
        cfg = self.write_config("KB_EMBED_MODEL=from-file\n")
        self.assertEqual(cfg.embed_model, "from-env")


class TestDerivedPaths(ConfigTestCase):
    def test_state_dir_is_outside_the_kb(self) -> None:
        """Generated state must never land inside the user's KB git history."""
        cfg = self.write_config(f'KB_ROOT="{self.root}/mykb"\n')
        self.assertFalse(
            under(cfg.state_dir, cfg.kb_root),
            "state_dir must not be inside KB_ROOT",
        )
        self.assertTrue(under(cfg.index_db, cfg.state_dir))
        self.assertTrue(under(cfg.retrieval_log, cfg.state_dir))

    def test_lesson_and_system_dirs_hang_off_kb_root(self) -> None:
        cfg = self.write_config(f'KB_ROOT="{self.root}/mykb"\n')
        self.assertEqual(cfg.lessons_dir, cfg.kb_root / "lessons")
        self.assertEqual(cfg.systems_dir, cfg.kb_root / "systems")


class TestScope(ConfigTestCase):
    def config(self) -> HarnessConfig:
        return self.write_config(
            f'KB_ROOT="{self.root}/mykb"\n'
            f'KB_WORK_ROOTS="{self.root}/proj-a:{self.root}/proj-b"\n'
        )

    def test_work_roots_and_subdirs_are_in_scope(self) -> None:
        cfg = self.config()
        self.assertTrue(in_project_scope(self.root / "proj-a", cfg))
        self.assertTrue(in_project_scope(self.root / "proj-a/sub/deep", cfg))
        self.assertTrue(in_project_scope(self.root / "proj-b", cfg))

    def test_unrelated_dir_is_out_of_scope(self) -> None:
        self.assertFalse(in_project_scope(self.root / "elsewhere", self.config()))

    def test_kb_is_always_excluded_without_being_configured(self) -> None:
        """Retrieving KB context while editing the KB is a feedback loop."""
        cfg = self.config()
        self.assertTrue(is_excluded(cfg.kb_root, cfg))
        self.assertTrue(is_excluded(cfg.kb_root / "lessons", cfg))

    def test_should_retrieve_combines_both_gates(self) -> None:
        cfg = self.config()
        self.assertTrue(should_retrieve(self.root / "proj-a", cfg))
        self.assertFalse(should_retrieve(cfg.kb_root, cfg))
        self.assertFalse(should_retrieve(self.root / "elsewhere", cfg))

    def test_extra_excluded_roots_from_env(self) -> None:
        cfg = self.config()
        os.environ["KB_EXCLUDED_ROOTS"] = str(self.root / "proj-b")
        self.assertTrue(is_excluded(self.root / "proj-b", cfg))
        self.assertFalse(should_retrieve(self.root / "proj-b", cfg))

    def test_project_roots_json_takes_precedence(self) -> None:
        self.write_roots_json(
            '{"version": 1, "project_roots": ['
            f'{{"path": "{self.root}/elsewhere", "enabled": true}},'
            f'{{"path": "{self.root}/proj-a", "enabled": false}}'
            "]}"
        )
        cfg = self.config()
        roots = [str(p) for p in cfg.project_roots]
        self.assertIn(str((self.root / "elsewhere").resolve()), roots)
        self.assertNotIn(
            str((self.root / "proj-a").resolve()),
            roots,
            "enabled:false roots must be dropped",
        )

    def test_malformed_project_roots_json_falls_back(self) -> None:
        """A broken config must degrade, not crash the hook on every prompt."""
        self.write_roots_json("{ not json")
        self.assertTrue(in_project_scope(self.root / "proj-a", self.config()))

    def test_under_rejects_sibling_prefix(self) -> None:
        """/a/proj-a-old must not count as inside /a/proj-a."""
        self.assertFalse(under(self.root / "proj-a-old", self.root / "proj-a"))
        self.assertTrue(under(self.root / "proj-a", self.root / "proj-a"))

    def test_nonexistent_path_does_not_raise(self) -> None:
        cfg = self.config()
        self.assertFalse(in_project_scope(self.root / "no/such/dir", cfg))


class TestReviewFindings(ConfigTestCase):
    """Regressions for defects found in peer review (REQ-...-architecture).

    Each test names the finding it locks down so a future refactor that
    reintroduces the bug fails loudly.
    """

    def test_f1_excluded_roots_honoured_from_config_file(self) -> None:
        """F1: KB_EXCLUDED_ROOTS was read from os.environ only, so the
        documented harness.env setting was silently ignored."""
        cfg = self.write_config(
            f'KB_ROOT="{self.root}/mykb"\n'
            f'KB_WORK_ROOTS="{self.root}/proj-a"\n'
            f'KB_EXCLUDED_ROOTS="{self.root}/proj-a/sub"\n'
        )
        self.assertIn(
            str((self.root / "proj-a/sub").resolve()),
            [str(p) for p in cfg.excluded_roots],
        )
        self.assertFalse(should_retrieve(self.root / "proj-a/sub", cfg))
        self.assertFalse(should_retrieve(self.root / "proj-a/sub/deep", cfg))
        self.assertTrue(should_retrieve(self.root / "proj-a", cfg))

    def test_f2_bad_embed_dim_does_not_raise(self) -> None:
        """F2: int() on a garbage value raised during construction, which would
        crash the UserPromptSubmit hook on every turn."""
        cfg = self.write_config("KB_EMBED_DIM=oops\n")
        self.assertEqual(cfg.embed_dim, 768)
        self.assertTrue(any("KB_EMBED_DIM" in w for w in cfg.warnings))

    def test_f2_out_of_range_embed_dim_rejected(self) -> None:
        self.assertEqual(self.write_config("KB_EMBED_DIM=0\n").embed_dim, 768)
        self.assertEqual(self.write_config("KB_EMBED_DIM=-5\n").embed_dim, 768)

    def test_f2_roots_json_as_list_of_strings(self) -> None:
        """F2: entries were assumed to be objects; a string entry raised
        AttributeError on .get()."""
        self.write_roots_json(f'{{"project_roots": ["{self.root}/proj-a"]}}')
        cfg = self.write_config(f'KB_ROOT="{self.root}/mykb"\n')
        self.assertIn(str((self.root / "proj-a").resolve()), [str(p) for p in cfg.project_roots])

    def test_f2_roots_json_top_level_list_ignored(self) -> None:
        """F2: a valid top-level JSON array reached .get() and raised."""
        self.write_roots_json("[]")
        cfg = self.write_config(f'KB_ROOT="{self.root}/mykb"\n')
        self.assertIsInstance(cfg.project_roots, list)  # must not raise

    def test_f2_hostile_json_shapes_do_not_raise(self) -> None:
        for body in ('{"project_roots": {"a": 1}}', '{"project_roots": [null, 3]}',
                     '{"excluded_roots": "nope"}', "null", '"a string"',
                     '{"project_roots": [{"path": 5}]}'):
            self.write_roots_json(body)
            fresh = self.write_config(f'KB_ROOT="{self.root}/mykb"\n')
            self.assertIsInstance(fresh.project_roots, list, body)
            self.assertIsInstance(fresh.excluded_roots, list, body)

    def test_f3_value_is_literal_not_shell_expanded(self) -> None:
        """F3: the file is read, never sourced, so no substitution happens."""
        cfg = self.write_config('KB_WEEKLY_AGENT="claude $(whoami)"\n')
        self.assertEqual(cfg.weekly_agent, "claude $(whoami)")
        self.assertTrue(any("command substitution" in w for w in cfg.warnings))

    def test_f3_single_and_double_quotes_behave_identically(self) -> None:
        double = self.write_config('KB_EMBED_MODEL="my model"\n').embed_model
        single = self.write_config("KB_EMBED_MODEL='my model'\n").embed_model
        self.assertEqual(double, single)
        self.assertEqual(double, "my model")

    def test_f3_only_leading_home_expands(self) -> None:
        cfg = self.write_config("KB_ROOT=~/kbdir\n")
        self.assertEqual(cfg.kb_root, Path(os.path.expanduser("~/kbdir")).resolve())
        mid = self.write_config("KB_EMBED_MODEL=a/$HOME/b\n")
        self.assertEqual(mid.embed_model, "a/$HOME/b")

    def test_f3_unterminated_quote_is_ignored_with_warning(self) -> None:
        cfg = self.write_config('KB_EMBED_MODEL="oops\n')
        self.assertEqual(cfg.embed_model, "nomic-embed-text")
        self.assertTrue(any("unterminated" in w for w in cfg.warnings))

    def test_f3_non_assignment_line_warns(self) -> None:
        cfg = self.write_config("this is not a config line\n")
        self.assertTrue(any("not KEY=VALUE" in w for w in cfg.warnings))

    def test_f4_kb_exclusion_survives_case_variant_spelling(self) -> None:
        """F4: on a case-insensitive filesystem (macOS default) a differently
        cased spelling of KB_ROOT resolved to the same directory but compared
        unequal, so retrieval could fire INSIDE the KB."""
        kb = self.root / "proj-a" / "KB"
        kb.mkdir(parents=True, exist_ok=True)
        cfg = self.write_config(
            f'KB_ROOT="{kb}"\nKB_WORK_ROOTS="{self.root}/proj-a"\n'
        )
        variant = self.root / "proj-a" / "kb"
        if not variant.exists():
            self.skipTest("filesystem is case-sensitive; variant cannot alias")
        self.assertTrue(is_excluded(variant, cfg), "case variant must still be excluded")
        self.assertFalse(should_retrieve(variant, cfg))

    def test_f4_kb_nested_under_project_root_still_excluded(self) -> None:
        """Exclusion must win over containment when the KB lives inside a
        managed project root — a realistic layout."""
        kb = self.root / "proj-a" / "knowledge"
        kb.mkdir(parents=True, exist_ok=True)
        cfg = self.write_config(
            f'KB_ROOT="{kb}"\nKB_WORK_ROOTS="{self.root}/proj-a"\n'
        )
        self.assertTrue(in_project_scope(kb, cfg))
        self.assertTrue(is_excluded(kb, cfg))
        self.assertFalse(should_retrieve(kb, cfg))

    def test_f4_symlinked_kb_still_excluded(self) -> None:
        real = self.root / "real-kb"
        real.mkdir(exist_ok=True)
        link = self.root / "proj-a" / "linked-kb"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        cfg = self.write_config(
            f'KB_ROOT="{real}"\nKB_WORK_ROOTS="{self.root}/proj-a"\n'
        )
        self.assertTrue(is_excluded(link, cfg), "symlink to the KB must be excluded")
        self.assertFalse(should_retrieve(link, cfg))

    def test_f4_dotdot_traversal_into_kb_excluded(self) -> None:
        cfg = self.write_config(
            f'KB_ROOT="{self.root}/mykb"\nKB_WORK_ROOTS="{self.root}"\n'
        )
        sneaky = self.root / "proj-a" / ".." / "mykb" / "lessons"
        self.assertTrue(is_excluded(sneaky, cfg))
        self.assertFalse(should_retrieve(sneaky, cfg))

    def test_sibling_prefix_not_treated_as_inside(self) -> None:
        (self.root / "proj-a-old").mkdir(exist_ok=True)
        cfg = self.write_config(f'KB_WORK_ROOTS="{self.root}/proj-a"\n')
        self.assertFalse(in_project_scope(self.root / "proj-a-old", cfg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
