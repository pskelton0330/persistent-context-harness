# Hot context (always loaded)

> This file is injected at session start. Keep it small (a screenful), keep it
> current, and **never put raw secrets here**. Promote only durable, broadly
> useful gotchas from `lessons/`. This is example content — replace it.

- Knowledge base lives at `$KB_ROOT`; start from `systems/<name>.md` + linked lessons.
- Before debugging a symptom, run `kb recall "<symptom>"`.
- Store credentials with `secret put <alias>`; reference aliases, never raw values.
- Example gotcha: the dev database resets nightly at 02:00 UTC — don't trust data
  written just before then. See `lessons/2024-01-01-example-lesson.md`.
