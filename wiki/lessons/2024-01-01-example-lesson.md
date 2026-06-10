---
type: lesson
date: 2024-01-01
severity: medium
systems: [example-service]
---

# Stale data near the nightly dev DB reset

## Symptom
Integration tests intermittently failed when run just before 02:00 UTC, reading
rows that vanished moments later.

## Root cause
The dev database resets nightly at 02:00 UTC. Data written in the minutes before
the reset is wiped, so assertions against it flake.

## Fix
Seed each test's own fixtures at the start of the run instead of relying on data
written by an earlier step that may straddle the reset window.

## Prevention
Treat the dev DB as ephemeral. Never assert on data you didn't create in the
same test. See [[example-service]].

## References
- This is an example lesson — replace it with real ones via `kb lesson "..."`.
