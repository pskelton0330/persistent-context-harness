# Architecture

The harness gives coding agents a memory that survives the session: knowledge is
primed when a session opens, recalled when you describe a matching symptom,
captured after the next fix, and curated weekly so the collection stays worth
reading.

## Components

```
bin/kb                  context | recall | index | lesson | health
bin/kb-selftest         honest install check (reports DEGRADED, not just OK)
bin/secret              put | get | run | list  (OS keychain)
bin/credential-guard    blocks raw secrets in prompts
bin/_common.sh          shell half of the config layer

lib/harness_config.py   Python half of the config layer — every path resolves here
lib/retrieval/
  index_lessons.py      builds the sqlite-vec index
  lesson_retriever.py   semantic query + health gate
  indexmeta.py          index provenance, fingerprint, row integrity
  vectors.py            one vector validator, shared by writer and reader
  retrieval_log.py      the feedback signal

hooks/
  session_start.py      priming
  prompt_submit.py      recall  (shared by Claude Code AND Codex)
  lesson_capture.py     capture
  post-tool-use-hook.sh edit marker

weekly/
  run-weekly.sh         the self-improvement pass
  prompts/              lesson-audit | crosslinks | gap-review
  install-schedule.sh   launchd (macOS) or cron (Linux)

agents/                 per-agent wiring (Claude Code, Codex, Hermes)
install/                bootstrap | extras | per-agent installers
tests/                  config, shell/Python parity, hook behaviour
wiki/                   example KB skeleton (real content lives elsewhere)
```

## The config layer

Every path in the system resolves through one place, with the same precedence
everywhere: **environment > `config/harness.env` > derived default**. There are
no hardcoded user paths.

There are two implementations — `bin/_common.sh` for shell, `lib/harness_config.py`
for Python — because both shell and Python components need the same answers. They
parse the config with **one strict grammar** and are held together by a
differential test (`tests/test_parser_parity.sh`) that runs the same fixtures
through both under bash, zsh, sh, dash and ksh.

The config file is *read*, never sourced. Sourcing it let the two implementations
disagree about quoting, escapes and expansion, so a single valid file could give
a shell hook different roots than a Python hook — a split-brain with no error.

Two invariants worth knowing:

- **`KB_STATE_DIR` lives outside `KB_ROOT`.** Generated state (the vector index,
  the retrieval log, weekly drafts) is machine state, not knowledge, and must
  never enter your notes' git history.
- **`KB_ROOT` is always self-excluded from retrieval**, without configuration.
  Recalling KB context into a session that is editing the KB is a feedback loop.
  Path comparison uses filesystem identity, not spelling, because on a
  case-insensitive filesystem `/a/KB` and `/a/kb` are the same directory but
  compare unequal.

## Priming

1. A session opens inside a configured work root.
2. `hooks/session_start.py` walks **up** from the session directory, matching each
   directory name against `systems/<slug>.md`, so a session opened deep inside a
   repo still finds its system page.
3. It injects that page plus every lesson the page links to via `[[wikilink]]`.
4. If nothing matches, it falls back to `hot.md` — otherwise the sessions most
   likely to lack context would get none.

## Recall

`hooks/prompt_submit.py` is invoked by Claude Code and Codex from the **same
file**, so their recall cannot drift apart. Gates run in this order:

1. **Scope** — silent outside work roots, and inside the KB itself.
2. **Noise** — synthetic agent plumbing (`<task-notification>` and similar) is
   not a user symptom.
3. **Credentials** — a prompt that looks like it contains a secret is dropped
   before it reaches a retriever, a log, or an embedding backend.
4. **Symptom shape** — only problem-shaped prompts, biased toward over-firing: a
   spurious lesson costs a few tokens, a missed one costs the point of the system.
5. **Retrieve** — semantic first, keyword as fallback.

### Why semantic

Keyword scoring false-positives badly on generic technical words — "turn",
"work", "rate" appear in almost every lesson, so an unrelated one surfaces on
almost any problem report. Semantic search matches meaning instead.

### The exit-2 contract

`lesson_retriever.py` exits **2** to mean *"semantic is unavailable or the index
is not trustworthy — fall back."* Callers must treat that as fallback, not as
"no lessons found". The distinction matters because an unhealthy index does not
error; it silently returns nothing, which is indistinguishable from a genuine
miss.

Exit 2 is returned for: unreachable backend, missing extras, missing index,
model or dimension mismatch, an index built against a different KB, a partial
index (row-id sets compared both ways, not just counts), a stale index, or a
malformed vector.

**Recall degrades, never disappears, and never lies.**

### Index provenance

The index records the embedding model, dimensions, KB root, schema version, and
a fingerprint of the lesson set it was built from. Freshness uses that
fingerprint — captured *before* the lessons are read — rather than a wall-clock
timestamp, which was racy in both directions: a lesson edited mid-build looked
fresh, and a sub-second rebuild looked stale.

A build **aborts rather than publishes** if any lesson cannot be read, and
enumeration fails closed, so a permissions error cannot replace a good index
with an empty one.

## Capture

`hooks/lesson_capture.py` fires at most once per session, only after real edits
in a managed project, and never for KB-only edits (writing notes is not the work
a lesson is about). It asks the agent to judge whether something durable was
learned, then to write it, link it from a system page, and reindex so it is
retrievable immediately.

Bias is toward capturing: a weak lesson is one `git revert` away; a lesson never
written is lost.

## The feedback signal

`lib/retrieval/retrieval_log.py` records what recall did — which lessons
surfaced, whether anything was injected, whether it had degraded to keyword.
This is what makes improvement possible rather than guesswork: hit rate, which
lessons carry their weight, and which have never been retrieved.

**Prompt text is never logged** — only its length, the working directory, and
the matches. A file accumulating everything a user typed, sitting next to their
knowledge base, would be a liability.

## Weekly self-improvement

Capture makes the KB grow; the weekly pass keeps it worth reading. Deterministic
steps run locally (reindex, retrieval statistics, structure check). Steps needing
judgement go to an agent CLI (`KB_WEEKLY_AGENT`) with focused prompts.

It emits **drafts and a report, never direct edits** — a job that rewrites your
notes unattended is not something to run on a schedule.

It is deliberately not pinned to a specific local model: a model tag that gets
renamed or removed makes the job fail soft and stay broken indefinitely.

Every run writes a status file that `kb-selftest` reads, failing on failed steps
and warning when the job has not run in two weeks. A scheduled job that fails
quietly is worse than no job, because capture keeps adding lessons while nothing
curates them.

## Agents

Each integration is self-contained — Claude Code reads `~/.claude/settings.json`,
Codex reads `~/.codex/hooks.json`, Hermes loads a skill — so any subset is a
valid install, and each installer tolerates its agent being absent. Claude Code
and Codex execute the **same hook files**; the Codex shim only translates the
output envelope.

## Testing

- `tests/test_config.py` — config parsing and scope resolution
- `tests/test_parser_parity.sh` — shell/Python equivalence across five shells,
  plus strict-mode sourcing and a CLI smoke test
- `tests/test_hooks.sh` — hook behaviour, driven with real payloads

Hook assertions check exit codes and stderr, not just whether stdout was empty.
An earlier version checked only for empty output and therefore scored a hook that
*crashed on import* as five consecutive passes — silence and failure are
indistinguishable from stdout alone.
