# Delta for Pull Request Tests

## ADDED Requirements

### Requirement: Build runs the SemForge page tests
The SemForge SDK job of `Build` SHALL run the SDK's tests that execute the editor pages' scripts in a headless browser, and SHALL fail when one of them fails or finds no browser. Outside CI these tests SHALL still be skipped, with their reason, when no browser is found.

#### Scenario: A page regression
- **WHEN** a pull request breaks the behaviour of an editor page's script, such as the count of entities shown
- **THEN** the SemForge SDK job of `Build` fails

#### Scenario: No browser in CI
- **WHEN** the SemForge SDK job of `Build` runs where no headless browser is found
- **THEN** the job fails, and no page test is reported as skipped

#### Scenario: No browser locally
- **WHEN** a developer runs the SDK's tests without a headless browser and without asking for one to be required
- **THEN** the page tests are skipped with the reason `no headless Chromium (set SEMFORGE_CHROME)`, and the other tests run
