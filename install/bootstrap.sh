#!/usr/bin/env bash
# Bootstrap the persistent context harness (macOS or Linux). Idempotent.
#   bash install/bootstrap.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
case "$(uname -s)" in Darwin) OS=mac ;; Linux) OS=linux ;; *) OS=other ;; esac

echo "== persistent-context-harness bootstrap ($OS) =="
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

# 3. Generate a ready-to-merge Claude Code settings snippet with paths filled in.
gen="$ROOT/config/claude-settings.generated.json"
sed "s#PCH_DIR#$ROOT#g" "$ROOT/agents/claude/settings.json.example" > "$gen"
echo "-- wrote $gen (merge its \"hooks\" into your ~/.claude/settings.json)"

# 4. Dependency check.
echo "== dependencies =="
deps="bash git python3"
[ "$OS" = linux ] && deps="$deps secret-tool"
for c in $deps; do command -v "$c" >/dev/null 2>&1 && echo "  ok      $c" || echo "  MISSING $c"; done

cat <<EOF

== next steps ==
  1. Add the CLIs to your PATH:
       export PATH="$ROOT/bin:\$PATH"   # add to ~/.bashrc or ~/.zshrc
  2. Point KB_ROOT at your real (private) notes dir in config/harness.env,
     or leave it to use this repo's example wiki/.
  3. Claude Code: merge config/claude-settings.generated.json into ~/.claude/settings.json
  4. Codex/ChatGPT (optional): bash install/install-codex.sh
  5. Store a secret to test: secret put example.api.key   (then: secret list)
Done.
EOF
