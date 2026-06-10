# Security & privacy model

This project is the **harness** — the mechanism that primes context, recalls and
captures lessons, and manages credentials. It is designed so that using it does
**not** leak your secrets or private content. The rules:

## 1. Secrets never touch files or git
Raw credential values live only in the OS keychain (macOS Keychain or Linux
libsecret), accessed through the `secret` CLI:

```
secret put example.db.password          # prompted, not echoed, not written to disk
secret run example.db.password DB_PW -- ./migrate.sh
```

Everywhere else — notes, prompts, commits, answers — you reference the **alias**
(`example.db.password`), never the value.

## 2. The credential-guard blocks raw secrets in prompts
`bin/credential-guard` is wired as a `UserPromptSubmit` hook for both Claude Code
and Codex. If a prompt contains something that looks like a private key, cloud
key, token, or `password=...`, the turn is blocked with a reminder to use the
keychain. It ships detection *patterns*, never values.

## 3. Content vs. harness
This repo ships only the harness plus a fictional `wiki/` example skeleton. Your
real knowledge base is **content** and is yours to keep private:

- Point `KB_ROOT` at a directory **outside this repo** for real notes, or
- Keep notes in a separate private repo.

`.gitignore` already excludes `private/`, `local/`, `*.private.md`, `.env`,
key files, and `config/harness.env`.

## 4. Pre-commit secret scan
Wire the scanner so a stray secret can't be committed:

```
ln -s ../../scripts/scan-secrets.sh .git/hooks/pre-commit
```

It scans staged files for secret-shaped values and fails the commit if any are
found. Run `scripts/scan-secrets.sh --all` to sweep the whole tree.

## 5. Keep `hot.md` clean
The always-loaded `hot.md` is the easiest place to accidentally leak something.
Keep it to durable, shareable gotchas — no hostnames, no credentials, nothing
you wouldn't want a teammate (or the public) to read.
