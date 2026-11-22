# Tasks

## 1. The page tests find their browser in one place

- [x] 1.1 One helper finds the browser (`SEMFORGE_CHROME`, then Playwright's Chromium), skips without one, and fails without one when `SEMFORGE_REQUIRE_CHROME` is set (D2); the four page-test files use it; verify with `tests/unit/test_headless_chromium.py` ("No browser locally", "No browser in CI")
  - `tests/unit/headless_chromium.py`, used by `test_entity_graph.py` (and through it `test_violation_navigation.py`), `test_first_click.py` and `test_valueforms.py`; `test_headless_chromium.py`: 11 passed (skip without a browser; fail with the flag `1`/`true`/`yes`; skip with ``/`0`/`false`/`no`; fail on a missing `SEMFORGE_CHROME` with the flag; `SEMFORGE_CHROME` first, then Playwright's).
- [x] 1.2 Without a browser and without the flag, the page tests still skip with their reason; with the flag they fail; verify by running `test_entity_graph.py`, `test_violation_navigation.py`, `test_first_click.py` and `test_valueforms.py` with Playwright's Chromium hidden, once with and once without `SEMFORGE_REQUIRE_CHROME=1` ("No browser locally", "No browser in CI")
  - Without the flag: 27 passed, 20 skipped with `no headless Chromium (set SEMFORGE_CHROME)`; with `SEMFORGE_REQUIRE_CHROME=1`: 20 failed (`no headless Chromium, and SEMFORGE_REQUIRE_CHROME is set`), 27 passed; with Chromium and the flag: 47 passed.

## 2. Build provides the browser and requires it

- [x] 2.1 The `semforge-sdk` job sets `SEMFORGE_REQUIRE_CHROME=1` and, before the build, writes the runner's Chrome to `SEMFORGE_CHROME`, failing without one (D1); verify with `test/bats-unit/build-workflow.bats`, which also runs the step against a fake Chrome and an empty `PATH` ("No browser in CI")
  - *the SemForge SDK job requires the browser for its page tests*, *… sets the browser before it runs the tests*, *the browser step hands the runner's Chrome to the page tests*, *the browser step fails when the runner has no Chrome*: all pass, and all four fail against the workflow of `main`.
- [x] 2.2 The SDK README says how the page tests find a browser, locally and in CI; verify by reading it
  - `semantic-model/SemForge-SDK/README.md`, after Quick start: `SEMFORGE_CHROME`, Playwright's Chromium, the skip reason, `SEMFORGE_REQUIRE_CHROME`, and what `Build` sets.

## 3. Checks

- [x] 3.1 Run the SDK's lint and unit suite with a local Chromium and `SEMFORGE_REQUIRE_CHROME=1`, `bats test/bats-unit`, shellcheck of the bats suites and `openspec validate --all --strict`; verify all pass
  - `flake8 semforge tests` clean; SDK suite with Playwright's Chromium and the flag: 2346 passed, 3 skipped (VS Code e2e, vsix packaging, OPC UA timing), coverage 88.72 %; `bats test/bats-unit`: 86 ok; shellcheck of `build-workflow.bats` clean; `openspec validate --all --strict`: 19 passed.
- [x] 3.2 In this pull request's `Build`, the SemForge SDK step prints the Chrome version and its test summary shows 20 fewer skips than on `main`, none in the four page-test files ("A page regression" is then covered by the tests running in CI)
  - Build run 45039077040 (head 69ee4366), job `semforge-sdk`: "Google Chrome 157.0.8103.78"; `2345 passed, 5 skipped`, against `2314 passed, 25 skipped` in the same job of the latest green `Build` on `main`.
