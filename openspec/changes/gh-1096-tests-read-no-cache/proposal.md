Issue: #1096

## Why

`semforge verify --tests` on a package directory takes the triples of `shacl.ttl` and `knowledge.ttl` from `.semforge/cache/graphs/` when an entry is named after the file's content. Nothing ties what the entry holds to that content, so a directory that comes from elsewhere, such as a pull request on which `Build` runs `kms-check`, can bring an entry that decides the result: an entry without triples for `shacl.ttl` gives a package without constraints. The statement index in `.semforge/cache/index/` is read as well, and a changed entry keeps the tests from running.

## What Changes

- Running a package's tests reads and writes no cache. Its Turtle files are parsed and indexed from their content.
- The caches of fetched contexts and dependencies, which a test run already ignores, and the editor's kept verdicts fall under the same rule.
- Everywhere else (the editor, `semforge validate`, `semforge test`, `semforge check`) the caches work as before.

## Capabilities

### New Capabilities

### Modified Capabilities
- `contracts/kms-package`: new requirement **The tests use nothing kept from earlier**.

## Out of Scope

- Checking cache entries outside test runs: the editor and the other commands keep trusting the caches of the machine they run on.
- Files a package names itself (in the descriptor, an expectation or a context) and that are not members: what they may be is settled by the requirements on members and standalone packages.
- The format of the caches.

## Impact

- Components: SemForge SDK (how a test run reads a package's Turtle files), `semantic-model/kms/README.md`.
- Contract: `contracts/kms-package` gains a requirement on how a package's tests run; the package format and the release record do not change. No result of an unchanged package changes.
- A repeated `semforge verify --tests` on a large package directory parses its files again: on the OPC UA pumps (12.8 MB of Turtle) loading takes about 7.4 s instead of 3 s. `kms-check` in CI starts without a cache and `semforge publish` tests a freshly extracted archive, so neither gets slower.
