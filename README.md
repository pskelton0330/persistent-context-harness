# persistent-context-harness

**Give your coding agents a memory that survives the session.** Knowledge you
have already paid for — the root cause you spent an afternoon finding — gets
primed into Claude Code and Codex when a session opens, surfaced again when you
describe a matching symptom, and captured after the next non-trivial fix.

It's the *mechanism*, not your notes: it ships with a tiny example knowledge base
and stays free of your content and secrets by design (see
[docs/security.md](docs/security.md)).

## What it does

- **Primes context** — opening a session inside a project injects that project's
  system page plus every lesson it links to, before you type anything.
- **Recalls lessons** — describing a problem surfaces matching past lessons for
  the agent to read *before* it starts debugging.
- **Captures lessons** — after real edits, a `Stop` hook asks the agent to write
  down symptom / root cause / fix / prevention.
- **Improves itself** — a weekly review audits lesson quality, proposes missing
  links, and reports what is *not* being captured.
- **Handles secrets** — a keychain-backed `secret` CLI plus a credential guard
  keep raw credentials out of prompts, logs, and git.

Claude Code and Codex run the **same hook files**, so their recall cannot drift
apart.

## Quick start

```sh
git clone https://github.com/pskelton0330/persistent-context-harness
cd persistent-context-harness

bash install/bootstrap.sh        # core, no dependencies
bash install/install-extras.sh   # venv + semantic search (recommended)
export PATH="$PWD/bin:$PATH"

kb index                         # build the semantic index
kb-selftest                      # verify the install honestly
```

`kb-selftest` reports **OK** only when semantic recall is actually live. If the
index is missing or the embedding backend is unreachable it reports **DEGRADED**
and says why — a green check that doesn't mean the system works is worse than a
red one.

Then point it at your own notes and projects:

```sh
$EDITOR config/harness.env       # KB_ROOT + KB_WORK_ROOTS
```

Setting this up on a new machine, or handing it to someone else? See
**[docs/getting-started.md](docs/getting-started.md)** for the full walkthrough,
including what to expect in the first few weeks.

## Wiring your agents

Each integration is independent — wire only what you use.

- **Claude Code** — `bash install/install-claude.sh`. It safely merges the
  harness hooks into `~/.claude/settings.json` (preserving your other settings,
  with a backup), using the right interpreter and path form for your OS.
- **Codex / ChatGPT** — `bash install/install-codex.sh`.
- **Hermes** (optional, external) — `bash install/install-hermes.sh`.

Works on macOS, Linux, and Windows. On Windows, run the commands from Git Bash
(bundled with Git for Windows) against native-Windows Claude Code / Codex — WSL
is not required.

## Retrieval

Two retrievers, one command. `kb recall` and the prompt hook try semantic search
first and fall back to keyword automatically.

**Semantic** (recommended) embeds your prompt and runs vector search over a
[sqlite-vec](https://github.com/asg017/sqlite-vec) index. It exists because
keyword scoring false-positives badly on generic technical words — "turn",
"work", "rate" appear in almost every lesson, so an unrelated one surfaces on
almost every problem report. It needs a local embedding backend
([Ollama](https://ollama.com) by default, `ollama pull nomic-embed-text`, ~274 MB).
Your prompts never leave the machine.

**Keyword** needs nothing at all, and is the automatic fallback whenever the
backend is unreachable or the index is unhealthy. Recall degrades; it does not
disappear.

```sh
kb index               # build (or --incremental)
kb index --check       # health, and why recall may be degraded
kb recall "requests time out under load"
```

The index is rebuilt rather than trusted when the embedding model, dimensions,
or lesson set change, so it can never quietly answer with vectors from a
different model.

## Weekly self-improvement

Capture makes a knowledge base grow. This keeps it worth reading — without
curation it fills with duplicates, half-written entries and unlinked lessons,
and recall quality decays even as the lesson count climbs.

```sh
bash weekly/run-weekly.sh              # run now
bash weekly/install-schedule.sh        # Sundays 10:00 (launchd or cron)
```

Deterministic steps run locally: reindex, retrieval statistics, structure check.
The steps needing judgement are handed to an agent CLI (`KB_WEEKLY_AGENT`,
default `claude`) with three focused prompts in `weekly/prompts/`:

| Prompt | Asks |
|---|---|
| `lesson-audit` | Which lessons are weak, duplicated, or orphaned? |
| `crosslinks` | Which lessons are invisible because nothing links to them? |
| `gap-review` | What is being worked on but *not* captured? |

It writes **drafts and a report**, never direct edits to your notes. A job that
rewrites your knowledge base unattended is not something to run on a schedule.

Failure is loud on purpose: every run records its status, and `kb-selftest`
fails if the last run had failed steps, or warns if it hasn't run in two weeks.
A scheduled job that fails quietly is worse than no job, because capture keeps
adding lessons while nothing curates them.

Deliberately not pinned to a specific local model. A model tag that gets renamed
or removed makes the job fail soft and stay broken indefinitely.

## The feedback signal

Recall logs what it did — which lessons surfaced, whether anything was injected,
whether it had degraded to keyword:

```sh
python3 lib/retrieval/retrieval_log.py --days 30
```

This answers questions that are otherwise unanswerable: your hit rate, which
lessons carry their weight, and which have **never** been retrieved (usually
because they're titled by conclusion rather than by symptom, or nothing links to
them).

Prompt **text is never logged** — only its length, the working directory, and
which lessons matched. This file sits next to your knowledge base and grows on
every problem-shaped prompt; a transcript of everything you typed would be a
liability, not a feature.

## Configuration

`config/harness.env` (gitignored, written by the installers).

| Var | Meaning |
|-----|---------|
| `KB_ROOT` | where your knowledge base lives. Point at a **separate private repo** for real notes. |
| `KB_WORK_ROOTS` | colon-separated project dirs where priming and recall fire |
| `KB_EXCLUDED_ROOTS` | extra dirs to stay silent in (`KB_ROOT` is always excluded) |
| `KB_RETRIEVER` | `semantic` or `keyword` |
| `KB_PYTHON` | interpreter with the extras (set by `install-extras.sh`) |
| `KB_EMBED_MODEL` / `KB_EMBED_URL` | embedding backend |
| `KB_WEEKLY_AGENT` | agent CLI for the weekly review |
| `KB_STATE_DIR` | generated state; kept outside `KB_ROOT` so it never enters your notes' git history |
| `KB_SECRET_BACKEND` | `auto` / `macos` / `libsecret` / `windows` |

The file is *read*, not sourced, using one strict grammar shared by the shell and
Python halves — `KEY=value`, `#` comments, values literal apart from a leading
`~/`. Sourcing it previously let the two disagree about quoting and expansion, so
one valid file could give a shell hook different roots than a Python hook.

## Your knowledge base

Plain markdown. A text editor and a terminal are enough:

```sh
$EDITOR "$KB_ROOT/index.md"
kb context                       # exactly what agents get primed with
kb health                        # broken links, missing sections
```

Pages link with `[[wikilink]]` syntax, which the harness resolves itself. **A
lesson nothing links to is effectively invisible** — session priming loads a
system page and the lessons it links to, so an unlinked lesson can only be found
by a search you think to run. `kb health` and the weekly cross-link pass both
check for this.

If you use [Obsidian](https://obsidian.md) you can open `KB_ROOT` as a vault for
backlinks and a graph view, but it's entirely optional.

The only non-markdown component is the semantic index — a generated sqlite file
under `KB_STATE_DIR`, rebuildable at any time with `kb index`, and never a source
of truth.

## Tests

```sh
python3 tests/test_config.py        # config + scope resolution
bash tests/test_parser_parity.sh    # shell/Python parity across 5 shells
bash tests/test_hooks.sh            # hook behaviour, driven with real payloads
```

The hook tests assert on exit codes and stderr, not just empty output. An earlier
version checked only whether stdout was empty and so scored a hook that *crashed
on import* as five consecutive passes — silence and failure are indistinguishable
from stdout alone.

## Security

Raw secrets live only in the OS keychain. The harness ships detection patterns,
never values; the prompt hook drops any prompt that looks like it contains a
credential before it reaches a retriever, a log, or an embedding backend; and
`scripts/scan-secrets.sh` guards your commits. Read
[docs/security.md](docs/security.md) before adding real content.

## Layout

See [docs/architecture.md](docs/architecture.md) for the component map.

## License

MIT — see [LICENSE](LICENSE).
