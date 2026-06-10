# Persistent Context — project guidelines

This project uses a persistent knowledge base so the agent never has to learn the
same lesson twice. Durable knowledge (systems, lessons, decisions, runbooks)
lives in the KB; consult it before re-reading source, and add to it when you
learn something worth keeping.

> Always-loaded context is injected by the SessionStart hook. The full KB lives
> at `$KB_ROOT` (defaults to this harness's `wiki/`).

## Three-layer model

| Layer    | Where                         | Who writes it          | Rule                          |
|----------|-------------------------------|------------------------|-------------------------------|
| raw      | your own drop zone            | you                    | the agent never modifies it   |
| wiki     | `$KB_ROOT/`                   | the agent, on request  | the distilled, durable layer  |
| hot      | `$KB_ROOT/hot.md`             | promoted from lessons  | small, always loaded, no secrets |
| secrets  | OS keychain (via `secret`)    | you                    | raw values never in files/git |

## Folder map (`$KB_ROOT/`)

```
hot.md        always-loaded context — keep it small, never put secrets here
index.md      map of content
systems/      one page per system you work on
components/   reusable pieces
lessons/      symptom / root cause / fix / prevention
decisions/    ADR-style: why X over Y
runbooks/     step-by-step procedures
reference/    indexes, credential ALIASES (never raw values)
```

## Session etiquette

1. Read the injected hot context first; for a system you haven't loaded, read
   `$KB_ROOT/systems/<name>.md` and the lessons it links before working.
2. Before debugging, check for a prior lesson: `kb recall "<symptom>"`. Treat
   matches as load-bearing — apply the known fix instead of re-deriving it.
3. After a non-trivial fix, surprising root cause, or non-obvious decision,
   propose a lesson: `kb lesson "<title>"`, then fill in the sections. File only
   on the user's approval unless the user has opted into autonomous capture.
4. **Never** put raw credentials, tokens, or private keys in KB pages, hot
   context, hooks, commits, or answers. Store them with `secret put <alias>` and
   reference the alias. The credential-guard hook blocks raw secrets in prompts.
5. Keep `$KB_ROOT` content free of anything you wouldn't want shared — the KB is
   a distillation, not a dumping ground for confidential material.

## Wikilinks

Use `[[page-name]]` (lowercase kebab-case filename, no extension). Add a page
for anything referenced from two or more places.
