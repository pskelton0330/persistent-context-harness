#!/usr/bin/env bash
# Install the optional extras that semantic recall and the weekly job need:
# a virtualenv with `requests` and `sqlite-vec`, plus the KB_PYTHON setting that
# points the harness at it.
#
# Everything else in the harness is stdlib-only and works without this. Run it
# when you want semantic search, which matches on meaning instead of keyword
# overlap and is what makes recall usable on a KB of any size.
#
#   bash install/install-extras.sh
#
# Idempotent: safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VENV="$ROOT/.venv"
CONFIG="$ROOT/config/harness.env"

echo "== context-harness extras =="

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "error: no python3 on PATH. Install Python 3.9+ and re-run." >&2
  exit 1
}
ver="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "-- python $ver ($PYTHON)"
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "error: python 3.9+ required, found $ver" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Virtualenv
# ---------------------------------------------------------------------------
# A dedicated venv rather than a global install: the harness should never fight
# with a project's own dependencies, and KB_PYTHON makes the choice explicit.
if [ -x "$VENV/bin/python" ]; then
  echo "-- reusing existing venv at $VENV"
else
  echo "-- creating venv at $VENV"
  "$PYTHON" -m venv "$VENV"
fi
VENV_PY="$VENV/bin/python"

echo "-- installing requests + sqlite-vec"
"$VENV_PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
if ! "$VENV_PY" -m pip install --quiet requests sqlite-vec; then
  echo "error: failed to install extras. Try re-running, or install them yourself:" >&2
  echo "  $VENV_PY -m pip install requests sqlite-vec" >&2
  exit 1
fi

# Verify rather than trust: a successful pip install can still leave an
# unusable sqlite-vec if the platform wheel does not match.
if ! "$VENV_PY" - <<'PY'
import sqlite3
import sqlite_vec  # noqa: F401
conn = sqlite3.connect(":memory:")
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.execute("CREATE VIRTUAL TABLE t USING vec0(embedding float[4])")
PY
then
  echo "error: sqlite-vec installed but cannot load (no wheel for this platform?)." >&2
  echo "       Set KB_RETRIEVER=keyword in $CONFIG to run without semantic search." >&2
  exit 1
fi
echo "-- verified: sqlite-vec loads and vec0 tables work"

# ---------------------------------------------------------------------------
# Record KB_PYTHON
# ---------------------------------------------------------------------------
touch "$CONFIG"
if grep -qE '^[[:space:]]*(export[[:space:]]+)?KB_PYTHON=' "$CONFIG" 2>/dev/null; then
  tmp="$CONFIG.tmp.$$"
  grep -vE '^[[:space:]]*(export[[:space:]]+)?KB_PYTHON=' "$CONFIG" > "$tmp"
  mv "$tmp" "$CONFIG"
fi
printf 'KB_PYTHON=%s\n' "$VENV_PY" >> "$CONFIG"
echo "-- set KB_PYTHON in $CONFIG"

# ---------------------------------------------------------------------------
# Embedding backend
# ---------------------------------------------------------------------------
# Checked but NOT installed: pulling a model is a big download and the user's
# choice. Semantic recall degrades to keyword when this is absent, so a missing
# backend is a warning, not a failure.
url="${KB_EMBED_URL:-http://localhost:11434/api/embed}"
base="${url%/api/embed}"
model="${KB_EMBED_MODEL:-nomic-embed-text}"
echo
if curl -sf --max-time 3 "$base/api/version" >/dev/null 2>&1; then
  echo "-- embedding backend reachable at $base"
  if curl -sf --max-time 5 -H 'Content-Type: application/json' \
       -d "{\"model\":\"$model\"}" "$base/api/show" >/dev/null 2>&1; then
    echo "-- model '$model' is installed"
  else
    echo "!! model '$model' is NOT installed. Semantic recall will fall back to"
    echo "   keyword until you run:  ollama pull $model"
  fi
else
  echo "!! no embedding backend at $base."
  echo "   Semantic recall falls back to keyword until one is running."
  echo "   Default backend is Ollama (https://ollama.com):  ollama pull $model"
fi

cat <<EOF

Done. Next:
  bin/kb index          build the semantic index over your lessons
  bin/kb index --check   confirm it is healthy
  bin/kb-selftest        verify the whole install
EOF
