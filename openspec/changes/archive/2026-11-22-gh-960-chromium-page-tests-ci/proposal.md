Issue: #960

## Why

The SemForge SDK tests the scripts of its editor pages (the entity graph, the violation list, the first click, the attribute panel) by running them in headless Chromium. Without a browser these tests skip themselves, and the `Build` job of the SDK provides none, so 20 of them never run in CI: on #951 the suite reported `2229 passed, 25 skipped` in CI against `2250 passed, 3 skipped` locally. A regression in the pages' behaviour, such as the "N of M shown" counting bug fixed in #951, would pass `Build` unnoticed. The review of #951 asked for this follow-up.

## What Changes

- The `semforge-sdk` job of `Build` hands the runner's preinstalled Google Chrome to the page tests (`SEMFORGE_CHROME`), and fails before the tests when the runner has no Chrome or Chromium.
- The job sets `SEMFORGE_REQUIRE_CHROME=1`. With it, a page test that finds no browser fails instead of skipping. Without it (locally) nothing changes: the tests still skip with the reason `no headless Chromium (set SEMFORGE_CHROME)`.
- The four page-test files share one way of finding the browser.
- The SDK README says how the page tests find a browser, locally and in CI.

## Capabilities

### New Capabilities

### Modified Capabilities
- `ci/pull-request-tests`: new requirement **Build runs the SemForge page tests**.

## Out of Scope

- Running the VS Code end-to-end suite (`vscode/test/e2e`) in CI.
- Changing what the page tests check.
- Looking for a browser on the `PATH` locally: that would start running the page tests on machines where they are skipped today.

## Impact

- Components: the `semforge-sdk` job of `.github/workflows/build.yaml` and its tests in `test/bats-unit/build-workflow.bats`; the SemForge SDK's unit tests (`tests/unit`) and README.
- No contract between components changes.
