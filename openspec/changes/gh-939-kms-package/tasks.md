# Tasks

## 1. Package check (SemForge SDK)

- [ ] 1.1 Read `kms.yaml` (`name`, `version`, `format`) as the descriptor and keep reading `semforge.yaml` and `kmsPackage`; verify `semforge where` and the Project view show the three settings for both descriptor names
- [ ] 1.2 Implement the package check of the contract (descriptor, newer format, roles and their locations, two forms of a role, empty role directory, unparsable document, paths leaving the root, two descriptors); verify with one unit test per scenario of the requirements from "A package is a directory with a descriptor" to "Packages are standalone"
- [ ] 1.3 Implement the member list; verify tests where `model-instance.scorpio.jsonld`, `.semforge/` and `.kms/` are excluded and `README.md` is included
- [ ] 1.4 Report non-conforming names with the conforming one; verify the "Legacy descriptor" scenario, and that `semforge validate` output on a `semforge.yaml` package is unchanged

## 2. Archive

- [ ] 2.1 Implement packing (`SHA256SUMS`, digest, fixed timestamps and order, `<name>-<version>.kms.zip`); verify tests for "Pack twice" (byte-identical), "Same content, different archive" (stored vs deflated) and `sha256sum -c` on an extraction
- [ ] 2.2 Implement archive verification (missing, extra, modified and duplicate entries, unsafe paths, links, encryption, size limit, package check of the tree); verify one test per failure in the three integrity and archive requirements, including that `../evil.ttl` writes nothing outside the extraction directory

## 3. Commands

- [ ] 3.1 Add `semforge pack` and `semforge verify` (text and `--format json`, exit codes 0/2); verify CLI tests for the scenarios of "Pack a package", "Packing refuses what it cannot vouch for" and "Verify a package in either form"
- [ ] 3.2 Let every reading command accept an archive and every writing command refuse one; verify `semforge validate` on `kms/example` and on its archive give identical verdicts and exit codes
- [ ] 3.3 Make `semforge init` and `new` write a conforming package; verify "Fresh package verifies" for the grouped and the flat layout

## 4. Published versions

- [ ] 4.1 Add `semforge publish` and the release record `.kms/releases.yaml`, and fail verification and packing when a published version has changed; verify the scenarios of "Published versions are immutable" and "Publish a version"
- [ ] 4.2 Run the suite and measure coverage in `semforge publish`, refuse below the threshold, and record the results; verify the scenarios of "Only tested versions are published", "The release record holds the test results" and "Publishing runs the tests"
- [ ] 4.3 Implement the coverage measure of the contract (firing as asserted; SHACL-SPARQL counted; rules and the scratchpad not counted; no constraints = 100 %); verify the scenarios of "Coverage counts the constraints that fire"
- [ ] 4.4 Add `semforge verify --tests` (with `--record` for archives) and the `tests.coverage` setting; verify "Re-running an archive against its record", "Re-running an archive alone" and "Default threshold shown"
- [ ] 4.5 Add `semforge version patch|minor|major`; verify "Minor raise", including that comments in `kms.yaml` survive
- [ ] 4.6 Warn once per version on the first change to a published package, with the three next versions, in the editor service; verify "First edit after publishing" and "Draft version" over the editor protocol

## 5. semantic-model/kms

- [ ] 5.1 Move the KMS to `kms/example/`, rename `semforge.yaml` to `kms.yaml` with `name: example`, `version: 1.0.0`, `format: 1`, copy the NGSI-LD vocabulary into `vocabulary/ngsild.ttl`, and add the relative link `kms/default -> example`; verify `semforge verify semantic-model/kms/default` passes and `semforge validate` and `test` give the results they gave before the move
- [ ] 5.2 Point every path into `semantic-model/kms` at `kms/default` (shacl2flink `Makefile` defaults and `ontology2kms`, the SDK test corpus links, the VS Code end-to-end test, the READMEs); verify `git grep` finds no path to the old files, and that shacl2flink's tests and `make` without arguments pass
- [ ] 5.3 Verify and test every package in `semantic-model/kms` in the `Build` workflow, failing on a failed verification (including a changed published version), on a broken example and, for published versions only, on coverage; verify the three scenarios of "Every package in semantic-model/kms is verified and tested in CI" on a scratch branch
- [ ] 5.4 List each package in a directory once, with `default` marked; verify "Listing the packages" and "Opening kms in the editor"
- [ ] 5.5 Describe the package and the directory in `kms/README.md` (including that `default` is a symbolic link) and point `SemForge-SDK/architecture.md` §6 to the contract; verify the links resolve

## 6. Integration check

- [ ] 6.1 Run `openspec validate gh-939-kms-package --strict`, the SDK test suite and shacl2flink's tests; verify all pass, and that `Build` and `K8s tests` pass on the Pull Request
