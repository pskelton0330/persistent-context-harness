# Getting started

Setting the harness up on a new machine, from nothing to a working memory loop.
Budget about 15 minutes.

Your knowledge base is **yours**. The harness never sends it anywhere, and two
people using it keep entirely separate notes. Nothing here is shared unless you
deliberately point two installs at the same directory.

## Before you start

Required:
- `git` and Python **3.9+**
- Claude Code and/or Codex

Optional but recommended:
- [Ollama](https://ollama.com) for semantic search — one model, ~274 MB, runs
  locally. Without it recall falls back to keyword matching, which works but is
  noticeably noisier.
- A keychain for the `secret` CLI: built in on macOS; on Linux
  `apt-get install libsecret-tools`. Priming, recall and capture do not need it.

## 1. Install the harness

```sh
git clone https://github.com/pskelton0330/persistent-context-harness
cd persistent-context-harness
bash install/bootstrap.sh
```

For semantic search:

```sh
ollama pull nomic-embed-text
bash install/install-extras.sh
```

The installer probes for a Python that can actually build a working virtualenv,
skipping any that can't, and verifies `sqlite-vec` loads rather than trusting
that pip succeeded.

## 2. Create your knowledge base

Somewhere outside this repo. A private git repo is the right home — lessons are
plain markdown, and history is genuinely useful when you want to know when you
learned something.

```sh
mkdir -p ~/my-kb/{lessons,systems,runbooks,reference}
cd ~/my-kb && git init
```

`hot.md` at the top level is optional: notes you want loaded into *every*
session. Keep it short — it is the scarcest space in the system.

## 3. Point the harness at your KB and your projects

Edit `config/harness.env`:

```sh
KB_ROOT=~/my-kb
KB_WORK_ROOTS=~/code/service-a:~/code/service-b
```

`KB_WORK_ROOTS` is where priming and recall fire. **Be generous** — this is the
most common thing people get wrong. If a project isn't listed, recall never
even attempts to fire there, and you get silence that looks like "no lessons
matched" but is really "never looked".

## 4. Wire your agent

```sh
bash install/install-claude.sh
```

This writes `config/claude-settings.generated.json`. **Merge its `hooks` block
into `~/.claude/settings.json`** — this is the one manual step. If that file
already has a `hooks` section, combine the arrays rather than replacing them.
Five hooks get wired:

| Event | Does |
|---|---|
| `SessionStart` | primes the matching system page + its linked lessons |
| `UserPromptSubmit` | recalls lessons when you describe a problem |
| `UserPromptSubmit` | blocks raw credentials in prompts |
| `PostToolUse` | notes that files were edited |
| `Stop` | asks for a lesson after real work |

For Codex: `bash install/install-codex.sh` (installs automatically, no merge).
Both agents run the *same* hook files, so their recall stays identical.

## 5. Build the index and check the install

```sh
export PATH="$PWD/bin:$PATH"
kb index
kb-selftest
```

`kb-selftest` tells you the truth:

- **OK** — core works and semantic recall is live
- **DEGRADED** — works, but something is missing (it names what)
- **FAILED** — something is actually broken

With an empty KB it will say you have no lessons yet. That's expected.

## 6. Schedule the weekly review

```sh
bash weekly/install-schedule.sh
```

Sundays at 10:00, via launchd or cron. It audits lesson quality, proposes
missing links, and reports what you're *not* capturing — writing drafts and a
report, never editing your notes directly.

## What to expect

**This pays off over weeks, not on day one.** You start with zero lessons, so
recall stays quiet at first. It gets useful as they accumulate — roughly:

- **Week 1** — mostly capture. The Stop hook asks after real fixes; say yes when
  something surprised you.
- **Week 2-3** — recall starts hitting. You describe a problem and the agent
  says "this looks like the lesson from last Tuesday".
- **Week 4+** — the weekly review has enough signal to tell you which lessons
  never surface and what you're failing to capture.

Two habits decide whether this works:

1. **Link every lesson from a system page.** An unlinked lesson is invisible to
   priming. It can only be found by a search you think to run.
2. **Title by symptom, not conclusion.** "Requests time out above 50 concurrent"
   is findable months later. "Fixed the pool bug" is not. Retrieval matches
   against the title and the Symptom section, so write the words you'd actually
   type when the problem recurs.

## When recall goes quiet

```sh
kb index --check                                   # is the index healthy?
python3 lib/retrieval/retrieval_log.py --days 30   # is recall even firing?
```

If attempts are near zero, `KB_WORK_ROOTS` is almost certainly too narrow —
recall isn't firing where you actually work. That is the most common failure,
and it looks exactly like "the knowledge base isn't helping".
