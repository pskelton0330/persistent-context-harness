---
name: context-kb
description: Use for any project that has a persistent knowledge base — load hot context, recall prior lessons before debugging, capture new lessons after non-trivial fixes, follow runbooks, and reference credential aliases. Shared across Claude, Codex, and other agents.
---

# Persistent Context KB workflow

Use this workflow for engineering sessions on a project wired to the harness.

1. **Prime.** Read the injected hot context. Run `kb context` if you need it
   on demand. For a system you haven't loaded, read `$KB_ROOT/systems/<name>.md`
   and the lessons it links before working.
2. **Recall before debugging.** On any symptom, run `kb recall "<symptom>"` and
   read matching lessons. If one applies, use its Fix instead of re-deriving it.
3. **Capture after.** After a non-trivial fix, surprising root cause, or
   non-obvious decision, run `kb lesson "<title>"` and fill in Symptom / Root
   cause / Fix / Prevention. Propose first; file on approval.
4. **Maintain.** Run `kb health` before larger editorial passes.

## Credentials

Raw credentials belong in the OS keychain, never in prompts, files, or git.

- Store: `secret put <alias>`
- Use: `secret run <alias> <ENV_VAR> -- <command>`, or `secret get <alias>`
- Reference aliases (e.g. `myapp.db.password`) in notes and answers — never the
  raw value. The credential-guard hook blocks raw secrets submitted in prompts.

## Hard rules

- Never write raw secrets into KB pages, hot context, hooks, commits, or answers.
- Keep `$KB_ROOT/hot.md` small and free of anything confidential.
- The KB is a distillation; don't paste in material you wouldn't want shared.
