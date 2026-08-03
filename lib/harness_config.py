#!/usr/bin/env python3
"""Single source of truth for every path the harness touches.

This is the Python half of a two-implementation contract; ``bin/_common.sh`` is
the shell half. Both read ``config/harness.env`` using the SAME strict grammar
(documented below) and derive the same values, so a shell hook and a Python hook
can never disagree about where the KB is or what is in scope.

Resolution order for every setting: environment variable > config/harness.env >
derived default. Nothing here may contain a user-specific path.

CONFIG FILE GRAMMAR (deliberately not shell):

    line       := blank | comment | assignment
    comment    := optional-ws '#' anything
    assignment := optional-ws KEY '=' VALUE
    KEY        := [A-Za-z_][A-Za-z0-9_]*
    VALUE      := bare-text | '"' text '"' | "'" text "'"

Values are LITERAL. No command substitution, no escapes, no variable expansion,
no line continuation -- with exactly one exception: a leading ``~/``, ``$HOME/``
or ``${HOME}/`` is expanded, because hand-editing a config full of absolute paths
is unpleasant. The installer writes fully-resolved absolute paths, so even that
is rarely needed.

The file is NOT sourced by the shell. An earlier version was, which made the two
implementations diverge on quoting, escapes and expansion -- one syntactically
valid file could yield different roots in shell and Python. Lines outside the
grammar are ignored with a warning rather than guessed at.

Import from a hook like::

    from harness_config import CONFIG, should_retrieve

Kept dependency-free and import-light on purpose: the prompt-submit hook runs on
every user turn, so this module must not shell out, must not do unbounded work,
and must never raise. Malformed input produces a conservative "do not retrieve"
verdict plus a diagnostic, never an exception.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

__all__ = [
    "CONFIG",
    "HarnessConfig",
    "under",
    "in_project_scope",
    "is_excluded",
    "should_retrieve",
]

PCH_ROOT = Path(__file__).resolve().parent.parent

# Bounds so a corrupt or hostile file cannot stall a hook that runs on every
# prompt. Real configs are a few hundred bytes and a handful of roots.
MAX_CONFIG_BYTES = 64 * 1024
MAX_ROOTS_BYTES = 256 * 1024
MAX_ROOTS = 256

# A leading `export ` is accepted purely as a kindness -- people type it from
# habit. Both parsers accept it identically, so it introduces no divergence.
_ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_HOME_PREFIXES = ("~/", "$HOME/", "${HOME}/")
_HOME_EXACT = ("~", "$HOME", "${HOME}")

# Diagnostics are printed to stderr at most once per process. Hooks emit context
# on stdout, so stderr is safe; repeating per prompt would be noise.
_warned = False


def _warn(messages: list[str]) -> None:
    global _warned
    if _warned or not messages:
        return
    _warned = True
    for message in messages[:10]:
        print(f"context-harness: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Config file parsing
# ---------------------------------------------------------------------------


def _expand_home(value: str) -> str:
    for prefix in _HOME_PREFIXES:
        if value.startswith(prefix):
            return str(Path.home() / value[len(prefix) :])
    if value in _HOME_EXACT:
        return str(Path.home())
    return value


def _parse_value(raw: str, key: str, warnings: list[str]) -> str | None:
    raw = raw.strip()
    if not raw:
        return ""

    quote = raw[0]
    if quote in {'"', "'"}:
        end = raw.find(quote, 1)
        if end == -1:
            warnings.append(f"config: unterminated quote for {key}; line ignored")
            return None
        value = raw[1:end]
        trailing = raw[end + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            warnings.append(f"config: trailing text after quoted {key}; line ignored")
            return None
    else:
        # Unquoted: ' #' begins a comment. A bare '#' is kept, so values that
        # legitimately contain one survive.
        value = raw.split(" #", 1)[0].strip()

    # These would be executed or expanded by a shell. We never source the file,
    # so they are literal here -- warn rather than silently behave differently
    # from what someone familiar with shell would expect.
    if "$(" in value or "`" in value:
        warnings.append(f"config: {key} contains command substitution; used literally")
    elif "$" in value and not value.startswith(_HOME_EXACT + _HOME_PREFIXES):
        warnings.append(f"config: {key} contains '$'; only a leading $HOME is expanded")

    return _expand_home(value)


def _parse_env_file(path: Path, warnings: list[str]) -> dict[str, str]:
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            warnings.append(f"config: {path} exceeds {MAX_CONFIG_BYTES} bytes; ignored")
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    out: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGN_RE.match(line)
        if not match:
            warnings.append(f"config: {path}:{number} is not KEY=VALUE; ignored")
            continue
        key, raw = match.group(1), match.group(2)
        value = _parse_value(raw, key, warnings)
        if value:
            out[key] = value
    return out


def _resolve(path_text: str | os.PathLike[str]) -> Path:
    path = Path(str(path_text)).expanduser()
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        # RuntimeError = symlink loop. Fall back to a lexical absolute path
        # rather than propagating into a hook.
        try:
            return Path(os.path.abspath(str(path)))
        except (OSError, ValueError):
            return path


def _split_roots(raw: str) -> list[Path]:
    parts = [part for part in raw.split(":") if part.strip()]
    return [_resolve(_expand_home(part.strip())) for part in parts[:MAX_ROOTS]]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class HarnessConfig:
    """Resolved paths and settings. Construct once; import ``CONFIG``.

    Construction is total: any malformed input is recorded in ``warnings`` and
    replaced with a safe default rather than raising.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PCH_ROOT
        self.warnings: list[str] = []
        self._file = _parse_env_file(self.root / "config" / "harness.env", self.warnings)

        self.kb_root = _resolve(self._get("KB_ROOT", str(self.root / "wiki")))

        # Generated artifacts (index, retrieval log, weekly drafts). Outside the
        # KB on purpose: machine state, not knowledge, and must never enter the
        # user's KB git history.
        self.state_dir = _resolve(self._get("KB_STATE_DIR", str(self.root / "state")))

        self.python = self._get("KB_PYTHON", "") or None
        self.retriever = self._get("KB_RETRIEVER", "keyword").strip().lower()
        self.embed_url = self._get("KB_EMBED_URL", "http://localhost:11434/api/embed")
        self.embed_model = self._get("KB_EMBED_MODEL", "nomic-embed-text")
        self.embed_dim = self._get_int("KB_EMBED_DIM", 768, minimum=1, maximum=65536)
        self.weekly_agent = self._get("KB_WEEKLY_AGENT", "claude")
        self.secret_backend = self._get("KB_SECRET_BACKEND", "auto")
        self.secret_service = self._get("KB_SECRET_SERVICE", "context-harness")

        # One immutable snapshot per instance. Reading the roots file twice (once
        # for project roots, once for exclusions) allowed a verdict to be
        # assembled from two different versions of the file.
        self._roots_data = self._load_roots_json()

        _warn(self.warnings)

    # -- lookup ------------------------------------------------------------

    def _get(self, name: str, default: str) -> str:
        value = os.environ.get(name)
        if value:
            return _expand_home(value.strip())
        return self._file.get(name, default)

    def _get_int(self, name: str, default: int, *, minimum: int, maximum: int) -> int:
        raw = self._get(name, str(default))
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            self.warnings.append(f"config: {name}={raw!r} is not an integer; using {default}")
            return default
        if not minimum <= value <= maximum:
            self.warnings.append(f"config: {name}={value} out of range; using {default}")
            return default
        return value

    # -- derived paths -----------------------------------------------------

    @property
    def lessons_dir(self) -> Path:
        return self.kb_root / "lessons"

    @property
    def systems_dir(self) -> Path:
        return self.kb_root / "systems"

    @property
    def index_db(self) -> Path:
        return self.state_dir / "lessons.db"

    @property
    def retrieval_log(self) -> Path:
        return self.state_dir / "retrieval-log.jsonl"

    @property
    def hot_file(self) -> Path:
        return self.kb_root / "hot.md"

    # -- scope -------------------------------------------------------------

    def _load_roots_json(self) -> dict:
        """Read the optional roots file, tolerating anything malformed."""
        candidate = os.environ.get("KB_PROJECT_ROOTS_FILE") or (
            self.kb_root / "reference" / "project-roots.json"
        )
        path = Path(candidate)
        try:
            if path.stat().st_size > MAX_ROOTS_BYTES:
                self.warnings.append(f"config: {path} too large; ignored")
                return {}
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return {}
        except RecursionError:
            self.warnings.append(f"config: {path} nested too deeply; ignored")
            return {}

        if not isinstance(data, dict):
            self.warnings.append(f"config: {path} is not a JSON object; ignored")
            return {}
        return data

    def _json_project_roots(self) -> list[Path]:
        entries = self._roots_data.get("project_roots")
        if not isinstance(entries, list):
            return []
        roots: list[Path] = []
        for entry in entries[:MAX_ROOTS]:
            if isinstance(entry, str):
                # Tolerate the plain-string form rather than crashing on it.
                roots.append(_resolve(_expand_home(entry)))
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("enabled", True) is False:
                continue
            path = entry.get("path")
            if isinstance(path, str) and path.strip():
                roots.append(_resolve(_expand_home(path.strip())))
        return roots

    @property
    def project_roots(self) -> list[Path]:
        """Directories where priming and recall should fire.

        Precedence: KB_PROJECT_ROOTS env > project-roots.json > KB_WORK_ROOTS.
        """
        env = os.environ.get("KB_PROJECT_ROOTS", "").strip()
        if env:
            return _split_roots(env)
        roots = self._json_project_roots()
        if roots:
            return roots
        return _split_roots(self._get("KB_WORK_ROOTS", str(Path.home())))

    @property
    def excluded_roots(self) -> list[Path]:
        """Directories where retrieval must stay silent.

        The KB is always excluded, without configuration: retrieving KB context
        into a session that is editing the KB is a feedback loop.
        """
        roots = [self.kb_root]

        entries = self._roots_data.get("excluded_roots")
        if isinstance(entries, list):
            roots += [
                _resolve(_expand_home(entry.strip()))
                for entry in entries[:MAX_ROOTS]
                if isinstance(entry, str) and entry.strip()
            ]

        # Read through _get so the setting works from harness.env, not just the
        # process environment.
        configured = self._get("KB_EXCLUDED_ROOTS", "")
        if configured.strip():
            roots += _split_roots(configured)
        return roots

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HarnessConfig kb_root={self.kb_root} retriever={self.retriever}>"


CONFIG = HarnessConfig()


# ---------------------------------------------------------------------------
# Scope predicates
# ---------------------------------------------------------------------------


def under(path: Path | str, root: Path | str) -> bool:
    """True if ``path`` is ``root`` or lives inside it.

    Compares by filesystem identity, not just spelling. A pure string compare is
    wrong on a case-insensitive filesystem (the macOS default), where
    ``/Users/a/KB`` and ``/users/a/kb`` are the same directory but compare
    unequal -- which would let retrieval fire inside the KB.
    """
    resolved_path = _resolve(path)
    resolved_root = _resolve(root)

    # Cheap lexical check first; also the only option for paths that do not
    # exist yet (tests, not-yet-created project dirs).
    try:
        resolved_path.relative_to(resolved_root)
        return True
    except ValueError:
        pass

    try:
        root_stat = resolved_root.stat()
    except (OSError, ValueError):
        return False

    for candidate in (resolved_path, *resolved_path.parents):
        try:
            if os.path.samestat(candidate.stat(), root_stat):
                return True
        except (OSError, ValueError):
            continue
    return False


def in_project_scope(path: Path | str, config: HarnessConfig | None = None) -> bool:
    cfg = config or CONFIG
    try:
        return any(under(path, root) for root in cfg.project_roots)
    except Exception:  # pragma: no cover - hot path must never raise
        return False


def is_excluded(path: Path | str, config: HarnessConfig | None = None) -> bool:
    cfg = config or CONFIG
    try:
        return any(under(path, root) for root in cfg.excluded_roots)
    except Exception:  # pragma: no cover - fail closed: treat as excluded
        return True


def should_retrieve(path: Path | str, config: HarnessConfig | None = None) -> bool:
    """The single gate hooks use: in a managed project, and not inside the KB."""
    cfg = config or CONFIG
    return in_project_scope(path, cfg) and not is_excluded(path, cfg)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Inspect resolved harness config.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--contains", metavar="PATH")
    parser.add_argument("--excluded", metavar="PATH")
    parser.add_argument("--retrieve", metavar="PATH")
    args = parser.parse_args()

    if args.contains:
        raise SystemExit(0 if in_project_scope(args.contains) else 1)
    if args.excluded:
        raise SystemExit(0 if is_excluded(args.excluded) else 1)
    if args.retrieve:
        raise SystemExit(0 if should_retrieve(args.retrieve) else 1)

    resolved = {
        "root": str(CONFIG.root),
        "kb_root": str(CONFIG.kb_root),
        "state_dir": str(CONFIG.state_dir),
        "python": CONFIG.python,
        "retriever": CONFIG.retriever,
        "embed_model": CONFIG.embed_model,
        "embed_dim": CONFIG.embed_dim,
        "weekly_agent": CONFIG.weekly_agent,
        "project_roots": [str(p) for p in CONFIG.project_roots],
        "excluded_roots": [str(p) for p in CONFIG.excluded_roots],
        "warnings": CONFIG.warnings,
    }
    if args.json:
        print(json.dumps(resolved, indent=2))
    else:
        for key, value in resolved.items():
            print(f"{key}: {value}")
