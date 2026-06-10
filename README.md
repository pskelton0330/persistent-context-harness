# persistent-context-harness

**Give your coding agents a persistent memory.** This harness primes durable
engineering knowledge into Claude Code, Codex/ChatGPT, and other agents at the
start of every session, recalls past lessons before you debug, and captures new
ones after non-trivial fixes — so the same problem is never solved twice.

It's the *mechanism*, not your notes: it ships with an example knowledge base and
stays free of any of your content or secrets by design (see
[docs/security.md](docs/security.md)).

## What it does

- **Primes context** — a `SessionStart` hook injects always-loaded gotchas plus
  the relevant system page when you open a session in a project.
- **Recalls lessons** — when you describe a problem, matching past lessons are
  surfaced before the agent starts debugging.
- **Captures lessons** — after a fix, a `Stop` hook nudges you to record the
  symptom / root cause / fix / prevention.
- **Manages secrets safely** — a keychain-backed `secret` CLI plus a
  `credential-guard` hook keep raw credentials out of prompts, files, and git.

## Quick start

```sh
git clone <your-fork-url> persistent-context-harness
cd persistent-context-harness
bash install/bootstrap.sh        # core only — no agent required
export PATH="$PWD/bin:$PATH"

kb-selftest                      # verify it works + see which agents are wired
kb context                       # see what would be primed
kb recall "timeout"              # find matching lessons
kb lesson "my first lesson"
secret put example.api.key && secret list
```

## Use one, two, or all three agents

Each agent integration is **independent** — wire only the ones you use. Claude
Code alone, Codex alone, Claude + Codex, or all three are all valid setups;
nothing depends on the others being installed.

- **Claude Code** — `bash install/install-claude.sh`, then merge the generated
  `config/claude-settings.generated.json` `"hooks"` into `~/.claude/settings.json`
  and use `agents/claude/CLAUDE.md` + `agents/claude/commands/`.
- **Codex / ChatGPT** — `bash install/install-codex.sh`.
- **Hermes** (optional/external) — `bash install/install-hermes.sh`, launch with
  `bin/hermes-context`.

Run `kb-selftest` any time to confirm the core works and see each agent's status
(`WIRED` / `READY` / `absent (skipped)`).

## Configuration

Copy and edit the config (gitignored):

```sh
cp config/harness.env.example config/harness.env
```

| Var | Meaning |
|-----|---------|
| `KB_ROOT` | where the knowledge base lives (default: this repo's `wiki/`). Point it at a **separate private dir** for real notes. |
| `KB_WORK_ROOTS` | colon-separated project dirs where priming should fire |
| `KB_RETRIEVER` | `keyword` (default) or `semantic` (bring your own backend) |
| `KB_SECRET_BACKEND` | `auto` / `macos` / `libsecret` |

## Layout

See [docs/architecture.md](docs/architecture.md) for the full component map and
how priming / recall / capture work.

## Security

Raw secrets live only in the OS keychain; the harness ships detection patterns,
never values; a pre-commit scanner (`scripts/scan-secrets.sh`) guards your
commits. Read [docs/security.md](docs/security.md) before adding real content.

## License

MIT — see [LICENSE](LICENSE).
