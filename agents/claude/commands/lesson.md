---
description: Capture the current session's fix as a durable KB lesson
---

Capture what we just learned as a lesson in the knowledge base.

1. Identify the lesson: the symptom, the root cause, the fix, and how to prevent
   it next time. If the fix was trivial (typo, rename), say so and stop.
2. Scaffold the file: run `kb lesson "<short kebab-friendly title>"`.
3. Fill in the Symptom / Root cause / Fix / Prevention sections with real
   content — no TODO placeholders. Link related pages with `[[name]]`.
4. If the insight is cross-cutting and safe, promote a one-line pointer to
   `$KB_ROOT/hot.md`.
5. Never include raw secrets — reference credential aliases only.

Show me the proposed lesson before writing unless I've told you to file directly.
