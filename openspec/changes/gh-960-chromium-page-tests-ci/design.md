# Design

## Context

The page tests render a page with Node and load it in headless Chromium (`--headless=new --no-sandbox --disable-gpu --dump-dom`). Each of the four test files looked for the browser itself, in `SEMFORGE_CHROME` and under `~/.cache/ms-playwright`, and skipped without one. The `semforge-sdk` job runs on `ubuntu-24.04`, whose runner image ships Google Chrome on the `PATH`, but nothing pointed the tests at it. Node is preinstalled on the runner too, and the page-rendering tests that need no browser already run there.

Conflict with existing specs or documentation: none. *Components build side by side* and *Tests without a cluster run outside the K8s test* still hold; the new requirement adds which tests the SDK's job must not skip.

## Goals / Non-Goals

**Goals:**
- Every page test runs in `Build`, and a missing browser fails the job instead of skipping the tests.
- Locally nothing changes.

**Non-Goals:**
- A browser of a pinned version: the page tests use only plain DOM and the headless flags above, which any current Chrome supports.

## Decisions

### D1: The runner's Google Chrome

A step before the build resolves `google-chrome` (or `google-chrome-stable`, `chromium`, `chromium-browser`) on the `PATH`, prints its version and writes its path to `SEMFORGE_CHROME` in `$GITHUB_ENV`. It fails the job when none is found. It installs nothing and takes a second.

*Alternatives:*
- `browser-actions/setup-chrome`: a new third-party action for a browser the runner already has, and a download on every run.
- Playwright's Chromium (`npx playwright install chromium`): about 150 MB per run, and an npm dependency the SDK's Python tests don't otherwise need.
- Make the tests also look on the `PATH`: changes local behaviour, which the issue rules out, and still lets a runner without Chrome skip silently.

### D2: Required by a flag, set only in CI

With `SEMFORGE_REQUIRE_CHROME` set to anything other than empty, `0`, `false` or `no`, a page test that finds no browser fails with a message naming the flag and `SEMFORGE_CHROME`. The `semforge-sdk` job sets it for all its steps. The lookup and the flag live in one helper the four test files use, so the rule can't drift between them.

*Alternatives:*
- Fail on any skip in CI (e.g. a skip-count check on pytest's output): the three remaining skips are legitimate and unrelated, and a count would break on every new one.
- Only the D1 step, no flag: a broken `SEMFORGE_CHROME` (a path that went away, a renamed variable) would again turn the tests into skips.

## Risks / Trade-offs

- Chrome on the runner image is updated by GitHub; a release that changes the headless behaviour would fail `Build` for every SDK change. That is the intended signal, and the fix is in the tests or the flags.
- The job takes about 15 seconds longer: the 20 page tests take about 10 seconds locally.
