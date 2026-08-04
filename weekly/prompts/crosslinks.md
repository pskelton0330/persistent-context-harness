You are improving the link structure of an engineering knowledge base.

Knowledge base: __KB_ROOT__
Lessons: __KB_ROOT__/lessons/    Systems: __KB_ROOT__/systems/

Links are not decoration. Session priming loads a systems/ page and every lesson
that page links to via [[wikilink]]. A lesson nothing links to is effectively
invisible: it can only ever be found by a keyword search someone thinks to run.

Do this:

1. List the systems/ pages and the lessons each already links to.
2. Find lessons that are NOT linked from any systems/ page.
3. For each, identify the systems/ page it belongs to, based on what the lesson
   is actually about. If none fits, say so — a missing systems page is itself a
   finding worth reporting.
4. Also propose lesson-to-lesson links where one lesson's Prevention is another
   lesson's Root cause. These chains are what stop the same class of mistake
   recurring in a new guise.

Output format — markdown only:

## Proposed links
For each, give EXACTLY:
- **file**: <path of the file to edit>
- **anchor**: <the existing line to insert after, quoted verbatim>
- **insert**: <the exact markdown line to add, including the [[wikilink]]>
- **why**: <one line>

## Missing system pages
<topics that have lessons but no systems/ page, or "none">

Be conservative: propose a link only where the connection is real. A wrong link
is worse than a missing one, because it teaches priming to load irrelevant
context. Write nothing to disk; output the report.
