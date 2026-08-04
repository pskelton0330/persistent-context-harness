# Contributing

## Run the tests

```sh
python3 tests/test_config.py        # config + scope resolution
bash tests/test_parser_parity.sh    # shell/Python parity across 5 shells
bash tests/test_hooks.sh            # hook behaviour, real payloads
./bin/kb-selftest                   # end-to-end install check
```

CI runs these on Linux and macOS, against Python 3.9 and 3.12.

## Things this codebase cares about

**Silence is not success.** Most components here can fail by producing nothing,
which is indistinguishable from working correctly. Assert on exit codes and
stderr, never on "stdout was empty" — an earlier version of the hook tests did
exactly that and scored a hook that crashed on import as five passes.

**Degrade, don't disappear.** Recall must always fall back rather than report
"no relevant lessons" when it actually failed. `lesson_retriever.py` exit **2**
means *"fall back to keyword"*; any new failure mode belongs there, not in a
silent empty result.

**Fail closed on scope.** If it cannot be determined whether a path is in scope,
the answer is no. Retrieving where you shouldn't is worse than not retrieving.

**Two implementations must be tested against each other.** `bin/_common.sh` and
`lib/harness_config.py` parse the same config. Any change to one needs a fixture
in `tests/test_parser_parity.sh`, which runs both under bash, zsh, sh, dash and
ksh. They have silently diverged before.

**Hooks must never block a prompt.** Everything in `hooks/` is stdlib-only and
exits 0 on unexpected failure. A hook that raises breaks the user's turn.

**Never commit generated state.** `KB_STATE_DIR` holds a vector index built from
the user's private lessons. It is gitignored; keep it that way.

## Adding a check to kb-selftest

Prefer a check that can fail. A selftest that only ever passes is worse than
none, because it converts "I don't know" into false confidence.
