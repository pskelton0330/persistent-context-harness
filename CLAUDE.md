# persistent-context-harness

Gives coding agents a memory across sessions: primes knowledge when a session
opens, recalls past lessons when a problem is described, captures new ones after
fixes, and curates the collection weekly.

---

# If the user asks you to set this up

Follow this exactly. It is designed so the human answers **two questions** and
does nothing else.

## Step 0 — Ask first, then work

Ask these two things together, in one message, and wait:

1. **Where should their knowledge base live?** Suggest `~/knowledge-base`.
   It must be OUTSIDE this repo. Offer to `git init` it — lessons are markdown,
   and history is genuinely useful.
2. **Which project directories should this watch?** Ask for the folders where
   they actually do their work. Push for MORE rather than fewer, and say why:
   recall only fires inside these paths, so a missing project produces silence
   that reads as "no lessons matched" when it is really "never looked". This is
   the single most common way this system underdelivers.

Do not guess either answer. Do not proceed until they reply.

While waiting, you may run `bash install/bootstrap.sh` — it is safe and
prerequisite-free.

## Step 1 — Check prerequisites

```sh
python3 --version          # need 3.9+   (on Windows: python --version)
command -v claude codex    # which agents to wire
command -v ollama          # optional, enables semantic search
```

**On Windows:** run every command in this guide from **Git Bash** (bundled with
Git for Windows; Claude Code already requires it). The interpreter is `python`,
not `python3` — the installers and hooks detect this for you, so you do not
substitute it by hand. WSL is not required; this runs against native-Windows
Claude Code / Codex.

If `ollama` is missing, tell them semantic search needs it (~274 MB model,
runs locally, prompts never leave the machine) and ask whether to continue
without it. Keyword recall works fine and is the automatic fallback — do not
treat its absence as a failure.

If ollama IS present, run `ollama pull nomic-embed-text` before Step 3.

## Step 2 — Install

```sh
bash install/bootstrap.sh
bash install/install-extras.sh     # skip only if they declined semantic search
```

`install-extras.sh` probes for a Python that can build a working virtualenv;
if it reports skipping one, that is expected, not an error.

## Step 3 — Configure

Create their KB and write `config/harness.env`. Use the answers from Step 0.

```sh
mkdir -p <their-kb>/{lessons,systems,runbooks,reference}
```

Append to `config/harness.env` (do not delete what `install-extras.sh` wrote
there — it set `KB_PYTHON`):

```
KB_ROOT=<their-kb>
KB_WORK_ROOTS=<dir1>:<dir2>:<dir3>     # separator is ':' on macOS/Linux, ';' on Windows
KB_RETRIEVER=semantic                 # or keyword if they declined
```

Grammar is strict: `KEY=value`, no quotes needed, no shell expansion except a
leading `~/`. Use absolute paths. On Windows, use forward slashes and the ';'
separator, e.g. `KB_WORK_ROOTS=C:/code/api;C:/code/web`.

## Step 4 — Wire the agents

```sh
bash install/install-claude.sh      # shows the dry-run, then merges (OS-aware)
```

That wrapper fills in the right interpreter (`python3`/`python`) and path form
for the OS, then runs the merge. To preview or drive it directly:

```sh
python3 install/merge-claude-settings.py --dry-run   # on Windows: python ...
python3 install/merge-claude-settings.py
```

Never hand-edit `~/.claude/settings.json`. The script preserves every other
setting, keeps hooks belonging to anything else, is idempotent, and writes a
timestamped backup. Show them the `--dry-run` output first.

If `codex` is installed, **ask before running `install/install-codex.sh`**.
Codex has no merge format for `~/.codex/hooks.json`, so installing REPLACES it.
If the user already has a Codex integration, that integration stops working.
The installer backs the file up and says so, but the user should choose. This
is the only step that can break something they already rely on.

## Step 5 — Build and verify

```sh
export PATH="$PWD/bin:$PATH"
kb index
kb-selftest
```

Interpret `kb-selftest` honestly for them:

- **OK** — done, everything live.
- **DEGRADED** — works, but something named is missing. Read the warnings and
  fix what is fixable. If they declined ollama, `semantic` degradation is
  expected — say so rather than implying the install failed.
- **FAILED** — something is genuinely broken. Diagnose before continuing.

"No lessons yet" is the correct state on a fresh install, not a problem.

## Step 6 — Schedule the weekly review

```sh
bash weekly/install-schedule.sh
```

## Step 7 — Tell them what to expect

Be honest that this pays off over weeks, not immediately:

- Week 1 is mostly capture. When the Stop hook asks after a real fix, say yes if
  something was surprising.
- Recall starts hitting around week 2–3, once there are lessons to find.
- The weekly review needs about a month of signal to say anything useful.

Then give them the two habits that decide whether it works at all:

1. **Link every lesson from a system page** with `[[wikilink]]` syntax. Priming
   loads a system page and the lessons it links to, so an unlinked lesson is
   invisible.
2. **Title by symptom, not conclusion.** "Requests time out above 50 concurrent"
   is findable months later; "fixed the pool bug" is not. Retrieval matches the
   title and Symptom section, so write the words they would actually type when
   the problem recurs.

Finally: they must **restart Claude Code** for the hooks to load.

## Rules while doing this

- Ask before touching anything in `$HOME` outside this repo. This includes
  `~/.codex/` and `~/.agents/`, not just `~/.claude/`. If the user sandboxed one
  path, assume they want the others sandboxed too, and ask — even if they said
  to proceed without questions.
- Never write their knowledge base for them. It starts empty on purpose.
- If a step fails, stop and diagnose. Do not continue past a failure and report
  success at the end.
- Report what actually happened, including anything you skipped.

---

# If the user asks you to work ON this repo

Read `CONTRIBUTING.md` first — it documents invariants that are easy to break
without noticing. In particular: silence is not success, so assert on exit codes
and stderr rather than on empty output. Run `tests/` before proposing changes.
