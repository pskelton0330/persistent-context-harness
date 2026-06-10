#!/usr/bin/env bash
# Core bootstrap for the persistent context harness (macOS or Linux). Idempotent.
# Sets up the CLIs and config only — it does NOT require any agent. Wire the
# agent(s) you actually use afterward with the per-agent installers; any subset
# (just Claude, just Codex, Claude+Codex, all three…) works on its own.
#   bash install/bootstrap.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
case "$(uname -s)" in Darwin) OS=mac ;; Linux) OS=linux ;; *) OS=other ;; esac

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

# 3. Dependency check (core needs only bash + python3; git optional).
echo "== core dependencies =="
for c in bash python3; do command -v "$c" >/dev/null 2>&1 && echo "  ok      $c" || echo "  MISSING $c"; done
[ "$OS" = linux ] && { command -v secret-tool >/dev/null 2>&1 && echo "  ok      secret-tool" || echo "  MISSING secret-tool (libsecret; needed for the secret CLI on Linux)"; }

cat <<EOF

== next steps ==
  1. Add the CLIs to your PATH:
       export PATH="$ROOT/bin:\$PATH"   # add to ~/.bashrc or ~/.zshrc
  2. (optional) Point KB_ROOT at your real notes dir in config/harness.env.
  3. Verify: bin/kb-selftest

  Wire only the agent(s) you use — each is independent:
       bash install/install-claude.sh    # Claude Code
       bash install/install-codex.sh     # Codex / ChatGPT
       bash install/install-hermes.sh    # Hermes (optional/external)
Done.
EOF
