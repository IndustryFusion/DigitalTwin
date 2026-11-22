# Tasks

## 1. The page tests find their browser in one place

- [ ] 1.1 One helper finds the browser (`SEMFORGE_CHROME`, then Playwright's Chromium), skips without one, and fails without one when `SEMFORGE_REQUIRE_CHROME` is set (D2); the four page-test files use it; verify with `tests/unit/test_headless_chromium.py` ("No browser locally", "No browser in CI")
- [ ] 1.2 Without a browser and without the flag, the page tests still skip with their reason; with the flag they fail; verify by running `test_entity_graph.py`, `test_violation_navigation.py`, `test_first_click.py` and `test_valueforms.py` with Playwright's Chromium hidden, once with and once without `SEMFORGE_REQUIRE_CHROME=1` ("No browser locally", "No browser in CI")

## 2. Build provides the browser and requires it

- [ ] 2.1 The `semforge-sdk` job sets `SEMFORGE_REQUIRE_CHROME=1` and, before the build, writes the runner's Chrome to `SEMFORGE_CHROME`, failing without one (D1); verify with `test/bats-unit/build-workflow.bats`, which also runs the step against a fake Chrome and an empty `PATH` ("No browser in CI")
- [ ] 2.2 The SDK README says how the page tests find a browser, locally and in CI; verify by reading it

## 3. Checks

- [ ] 3.1 Run the SDK's lint and unit suite with a local Chromium and `SEMFORGE_REQUIRE_CHROME=1`, `bats test/bats-unit`, shellcheck of the bats suites and `openspec validate --all --strict`; verify all pass
- [ ] 3.2 In this pull request's `Build`, the SemForge SDK step prints the Chrome version and its test summary shows 20 fewer skips than on `main`, none in the four page-test files ("A page regression" is then covered by the tests running in CI)
