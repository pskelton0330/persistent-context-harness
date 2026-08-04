You are checking whether an engineering knowledge base is actually capturing
what is being learned.

Knowledge base: __KB_ROOT__
Retrieval statistics (last 30 days): __STATS__

The statistics file records what lesson recall did: how often it fired, what it
surfaced, and which lessons have NEVER been retrieved.

Do this:

1. Read __STATS__.
2. Interpret it honestly:
   - A low hit rate means recall fires but finds nothing — the KB has gaps, or
     lesson titles do not match how problems get described.
   - Lessons that never surface are either badly titled, badly linked, or cover
     something that does not recur. Distinguish these; the fix differs.
   - `degraded` entries mean semantic search was unavailable and keyword was
     used instead. If that number is high, the index or embedding backend needs
     attention and recall quality is worse than it looks.
3. Compare the recent lessons in __KB_ROOT__/lessons/ against the areas where
   recall is missing. What subject matter is being worked on but not captured?

Output format — markdown only:

## What the numbers say
<4-6 lines, concrete, quoting the actual figures>

## Likely capture gaps
<topics that appear to be worked on but under-documented, with reasoning>

## Lessons that never surface
<group by likely cause: bad title / not linked / genuinely rare. Give the
 specific retitle or link that would fix each of the first two groups.>

## One thing to change this week
<a single, specific, high-leverage recommendation>

Write nothing to disk; output the report.
