# Architecture

The harness gives coding agents a **persistent memory** across sessions: durable
engineering knowledge is primed into context automatically, prior lessons are
recalled before debugging, and new lessons are captured after non-trivial fixes —
so the same problem is never solved twice.

## Components

```
bin/kb               context | recall | lesson | health   (the KB CLI)
bin/secret           put | get | run | list                (keychain-backed)
bin/credential-guard blocks raw secrets in prompts
bin/hermes-context   launch Hermes with the context-kb skill (optional)
bin/kb-selftest      verify core + report which agents are wired
hooks/               session-start, symptom-retriever, post-tool-use, lesson-capture (shared)
agents/claude/       CLAUDE.md guidelines, settings.json, slash commands
agents/codex/        hooks.json + a shim that reuses the shared shell hooks
agents/shared-skill/ the context-kb skill (Claude + Codex + Hermes)
wiki/                example KB skeleton (your real content can live elsewhere)
install/             bootstrap.sh + install-claude.sh / install-codex.sh / install-hermes.sh
```

## Independent, optional agents

Every integration is self-contained: Claude Code reads its hooks from
`~/.claude/settings.json`, Codex reads `~/.codex/hooks.json`, and Hermes loads
the `~/.agents/skills/context-kb` skill. None of them import or require the
others, so any subset is a valid install. The per-agent installers each tolerate
their agent being absent (they install config for when you add it). The four
hook events (SessionStart, UserPromptSubmit, PostToolUse, Stop) are wired
identically for Claude Code and Codex via the shared `hooks/` scripts.

## How priming works

1. An agent session opens inside a configured work root (`KB_WORK_ROOTS`).
2. The `SessionStart` hook runs `kb context`, which prints `hot.md` plus the
   detected `systems/<name>.md` page and its linked lessons.
3. The host (Claude Code / Codex) injects that output as session context.

## How recall works

On a problem-shaped prompt, the `UserPromptSubmit` hook runs `kb recall`, which
keyword-scores `lessons/*.md` against the symptom and injects the best matches —
so the agent reads the known fix before re-deriving it.

## How capture works

After a turn with edits, the `Stop` hook nudges for a lesson. `kb lesson "<title>"`
scaffolds a dated file with the Symptom / Root cause / Fix / Prevention schema.

## One skill, many agents

The `context-kb` skill is the single source of workflow truth. Claude Code loads
it via its guidelines + hooks; Codex loads it via `~/.agents/skills`; the shell
hooks under `hooks/` are shared so behavior stays identical across hosts.

## Configuration

Everything resolves from the script location plus `config/harness.env` (copied
from `harness.env.example`). There are **no hardcoded user paths** — set
`KB_ROOT`, `KB_WORK_ROOTS`, `KB_RETRIEVER`, and the secret backend there.
