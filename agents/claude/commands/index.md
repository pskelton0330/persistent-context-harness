---
description: Rebuild the semantic lesson index so new lessons are retrievable
---

Rebuild the knowledge-base semantic index.

Run: `!bash -c 'cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" && kb index --incremental'`

Then report the result of `kb index --check`.

Run this after adding or editing lessons. Until the index is rebuilt a new
lesson is invisible to semantic recall — and a freshly captured lesson is the
one most likely to come up again soon.
