---
description: Search the KB for lessons matching a symptom before debugging
---

Before debugging, check whether we've hit this before.

1. Run `kb recall "$ARGUMENTS"` (or infer the symptom from the conversation).
2. Read each matching lesson. If one's Root cause matches the current symptom,
   apply its Fix instead of re-deriving it.
3. If no match applies, say so explicitly and proceed with fresh debugging.
