#!/usr/bin/env bash
# Core bootstrap for the persistent context harness (macOS or Linux). Idempotent.
# Sets up the CLIs and config only — it does NOT require any agent. Wire the
# agent(s) you actually use afterward with the per-agent installers; any subset
# (just Claude, just Codex, Claude+Codex, all three…) works on its own.
#   bash install/bootstrap.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
  *) OS=other ;;
esac

echo "== persistent-context-harness core bootstrap ($OS) =="
echo "   repo: $ROOT"

# 1. Make the CLIs and hooks executable.
chmod +x "$ROOT"/bin/* "$ROOT"/hooks/*.sh "$ROOT"/install/*.sh \
         "$ROOT"/agents/codex/hooks/*.py "$ROOT"/scripts/*.sh 2>/dev/null || true

# 2. Local config from the example (gitignored; safe to edit).
if [ ! -f "$ROOT/config/harness.env" ]; then
  cp "$ROOT/config/harness.env.example" "$ROOT/config/harness.env"
  echo "-- created config/harness.env (edit KB_ROOT / KB_WORK_ROOTS)"
else
  echo "-- config/harness.env already exists"
fi

# 3. Dependency check (core needs only bash + python; git optional).
# The interpreter is `python3` on Unix and `python` on Windows — accept either
# so a Windows box (where there is no `python3`) is not reported as missing it.
echo "== core dependencies =="
command -v bash >/dev/null 2>&1 && echo "  ok      bash" || echo "  MISSING bash"
if command -v python3 >/dev/null 2>&1; then echo "  ok      python3"
elif command -v python >/dev/null 2>&1; then echo "  ok      python (python3 not present — expected on Windows)"
else echo "  MISSING python3/python"; fi
[ "$OS" = linux ] && { command -v secret-tool >/dev/null 2>&1 && echo "  ok      secret-tool" || echo "  MISSING secret-tool (libsecret; needed for the secret CLI on Linux)"; }
[ "$OS" = windows ] && { command -v powershell.exe >/dev/null 2>&1 && echo "  ok      powershell (secret CLI uses DPAPI)" || echo "  MISSING powershell.exe (needed for the secret CLI on Windows)"; }

cat <<EOF

== next steps ==
  1. Add the CLIs to your PATH:
       export PATH="$ROOT/bin:\$PATH"   # add to ~/.bashrc or ~/.zshrc
  2. IMPORTANT — set KB_ROOT to a PRIVATE directory OUTSIDE this repo in
       config/harness.env. The wiki/ here is a fictional example; if you leave
       KB_ROOT unset it defaults to this repo's wiki/, so your real notes would
       land in a clone of a public repo. (.gitignore blocks committing them, but
       keep them out entirely.)  e.g.  KB_ROOT=\$HOME/knowledge-base/wiki
  3. Verify: bin/kb-selftest

  Wire only the agent(s) you use — each is independent:
       bash install/install-claude.sh    # Claude Code
       bash install/install-codex.sh     # Codex / ChatGPT
       bash install/install-hermes.sh    # Hermes (optional/external)
Done.
EOF
