You are auditing a personal engineering knowledge base for quality. Be blunt and
specific — this report is read by one engineer who wants to fix real problems,
not receive encouragement.

The knowledge base is at: __KB_ROOT__
Lessons are markdown files in __KB_ROOT__/lessons/
A structural check has already run; its output is at: __STRUCTURE__

A good lesson has: frontmatter, a concrete Symptom, a Root cause that explains
WHY (not just what was changed), a Fix, and a Prevention that is actionable.
It is linked from at least one systems/ page, or it will never be surfaced by
session priming.

Do this:

1. Read __STRUCTURE__ first — do not re-derive what it already found.
2. Sample up to 25 lessons, weighted toward the most recently modified. Read
   them properly; do not skim filenames.
3. Identify, with file paths:
   - lessons missing a Root cause or Prevention, or whose Root cause restates
     the symptom
   - probable DUPLICATES or near-duplicates (give both paths, say which to keep)
   - ORPHANS: lessons no systems/ page links to
   - lessons whose title would not match how someone would describe the symptom
     months later (this is the single biggest cause of recall failure)
4. Propose at most 5 concrete promotions to always-hot context (__KB_ROOT__/hot.md):
   only lessons that are TRULY cross-cutting. Resist promoting; hot context is
   loaded into every session and is the scarcest space in the system.

Output format — a markdown report only, no preamble:

## Summary
<3-5 lines: overall health, the single most valuable fix>

## Fix these first
<numbered, each with: path, what is wrong, the concrete edit to make>

## Duplicates
<pairs, with a recommendation>

## Orphans
<paths, and which systems/ page each should link from>

## Hot-context promotions
<at most 5, each with a one-line justification, or "none — nothing qualifies">

Write nothing to disk. Output the report as your response.
