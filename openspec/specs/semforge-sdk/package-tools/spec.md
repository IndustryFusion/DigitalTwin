# semforge-sdk/package-tools Specification

## Purpose
Defines how the SemForge SDK, which authors and manages KMS packages, creates
packages that conform to the KMS package contract, packs and verifies them,
tests and publishes them, versions them, warns when a published package is
changed, and works on a packed package.

## Requirements

### Requirement: Pack a package
The SDK SHALL provide `semforge pack [PATH] [--output FILE]`. It SHALL resolve the package that applies at `PATH`, check that it is a valid KMS package, and write its archive to `FILE` or to `<name>-<version>.kms.zip` in the current directory. It SHALL print the archive path and the package digest, and list every file under the root it left out because it is not a member.

#### Scenario: Packing the example package
- **WHEN** `semforge pack semantic-model/kms/default` is run
- **THEN** `example-<version>.kms.zip` is written, the digest is printed, `model-instance.scorpio.jsonld` is listed as left out, and the exit code is 0

### Requirement: Packing refuses what it cannot vouch for
`semforge pack` SHALL write nothing and exit with code 2 when the package is not valid, or when its version is published with a different digest.

#### Scenario: Packing an invalid package
- **WHEN** `semforge pack` is run on a package whose descriptor has no `version`
- **THEN** no archive is written, the missing `version` is reported and the exit code is 2

#### Scenario: Packing a changed published version
- **WHEN** `semforge pack` is run on a package whose published version `1.0.0` has since changed
- **THEN** no archive is written and the report says that version `1.0.0` must be raised

### Requirement: Verify a package in either form
The SDK SHALL provide `semforge verify TARGET`, where `TARGET` is a package directory or an archive. It SHALL apply the checks of the KMS package contract, print the name, version and package digest on success and exit 0, and print each failure with the path it concerns and exit 2 otherwise. With `--format json` it SHALL print the same result as one JSON object.

#### Scenario: Directory and archive agree
- **WHEN** `semforge verify` is run on a package directory and on the archive packed from it
- **THEN** both succeed and print the same package digest

#### Scenario: Tampered archive
- **WHEN** `semforge verify` is run on an archive in which one member was modified
- **THEN** it exits 2 and names that member

### Requirement: Publish a version
The SDK SHALL provide `semforge publish [PATH] [--output FILE]`. It SHALL pack the package as `semforge pack` does and record its version, package digest and the date in `.kms/releases.yaml`. Publishing a version that is already recorded with the same digest SHALL change nothing and succeed; with a different digest it SHALL fail as packing does.

#### Scenario: First publication
- **WHEN** `semforge publish` is run on `example` at version `1.0.0`, which is not recorded
- **THEN** `example-1.0.0.kms.zip` is written and `.kms/releases.yaml` lists `1.0.0` with the printed digest

#### Scenario: Publishing again unchanged
- **WHEN** `semforge publish` is run again without any change
- **THEN** the record is unchanged and the archive is byte-identical to the first

### Requirement: Publishing runs the tests
`semforge publish` SHALL run every example of the suite and measure the coverage before it packs. When an example does not meet its expectations or the coverage is below the threshold, it SHALL write and record nothing, exit with code 2, and report the failing examples and the constraints that are not covered. Otherwise it SHALL record the test results with the version.

#### Scenario: Publishing an undertested package
- **WHEN** `semforge publish` is run on a package with a coverage of 5 % and no declared threshold
- **THEN** no archive is written, `.kms/releases.yaml` is unchanged, the report gives 5 % against 80 % with the uncovered constraints, and the exit code is 2

#### Scenario: Publishing a tested package
- **WHEN** `semforge publish` is run on a package whose examples all meet their expectations and whose coverage is 85 %
- **THEN** the archive is written and the release record lists the examples, 85 % and the threshold of 80 %

### Requirement: Verification can run the tests again
`semforge verify --tests TARGET` SHALL also run the tests of the package or archive, report the examples and the coverage, and fail when an example does not meet its expectations. It SHALL compare the result with a release record when one is available: a directory's own `.kms/releases.yaml`, or for an archive the record given with `--record FILE`. For a published version, a result that differs from its record SHALL fail.

#### Scenario: Re-running an archive against its record
- **WHEN** `semforge verify --tests example-1.0.0.kms.zip --record semantic-model/kms/example/.kms/releases.yaml` is run on an untampered archive
- **THEN** it succeeds and prints the same number of examples and the same coverage as the record lists for `1.0.0`

#### Scenario: Re-running an archive alone
- **WHEN** `semforge verify --tests example-1.0.0.kms.zip` is run without a record
- **THEN** it runs the tests, prints the examples and the coverage, and says that no release record was compared

### Requirement: The coverage threshold is a package setting
`tests.coverage` SHALL be shown with the other package settings, together with the default of 80 when it is not declared, and SHALL be editable where the other settings are.

#### Scenario: Default threshold shown
- **WHEN** a package does not declare `tests.coverage`
- **THEN** `semforge where` and the editor's project view show the threshold as 80, marked as the default

### Requirement: Raise the version
The SDK SHALL provide `semforge version patch|minor|major [PATH]`, which raises the corresponding part of `version` in `kms.yaml`, resets the parts after it to 0, and changes nothing else in the file.

#### Scenario: Minor raise
- **WHEN** `semforge version minor` is run on a package at version `1.2.3`
- **THEN** `kms.yaml` declares `version: 1.3.0` and its other lines, comments included, are unchanged

### Requirement: The editor warns when a published package changes
When an edit made through the SDK or the editor changes the content of a package whose current version is published, the SDK SHALL warn once per version that the version must be raised and offer the next patch, minor and major version. It SHALL NOT block the edit.

#### Scenario: First edit after publishing
- **WHEN** a constraint is edited in a package whose version `1.0.0` is published
- **THEN** the edit is made, a warning says that `1.0.0` is published, and `1.0.1`, `1.1.0` and `2.0.0` are offered

#### Scenario: Draft version
- **WHEN** the same edit is made after the version was raised to `1.0.1`, which is not published
- **THEN** no warning is shown

### Requirement: Commands accept an archive
Every command that reads a package (`validate`, `test`, `check`, `export`, `where`, `diff`, `explain`, `observe`) SHALL also accept the path of an archive. The archive SHALL be verified before it is read, and the command SHALL give the same results as on the directory it was packed from. Commands that change a package SHALL refuse an archive and say that it is read-only.

#### Scenario: Validate an archive
- **WHEN** `semforge validate example-1.0.0.kms.zip` is run
- **THEN** it reports the same violations and exit code as `semforge validate semantic-model/kms/example`

#### Scenario: Edit an archive
- **WHEN** a command that writes to the package is given an archive
- **THEN** it changes nothing and reports that a packed package is read-only

### Requirement: Names outside the contract keep loading and are reported
The SDK SHALL keep loading packages that use names the contract does not allow (`semforge.yaml` as descriptor, `kmsPackage`, `main.jsonld`, `model.jsonld`, `shapes/`, a role present in two forms), so that existing packages keep working. `semforge verify` SHALL report each such name with the conforming one and fail, and `semforge pack` and `publish` SHALL refuse such a package.

#### Scenario: Legacy descriptor
- **WHEN** a package has `semforge.yaml` and no `kms.yaml`
- **THEN** `semforge validate` works as before, and `semforge verify` fails naming `semforge.yaml` and the conforming name `kms.yaml`

### Requirement: New packages conform
`semforge init` and `semforge new` SHALL create a package that passes `semforge verify`: a `kms.yaml` declaring `name`, `version: 0.1.0` and `format: 1`, the model-instance role named `model-instance.jsonld`, and a local NGSI-LD vocabulary copied into the package rather than referred to outside it.

#### Scenario: Fresh package verifies
- **WHEN** `semforge init` is run in an empty directory and then `semforge verify` on it
- **THEN** verification succeeds

### Requirement: A directory of packages lists each package once
When the SDK or the editor looks for packages below a directory such as `semantic-model/kms`, it SHALL list each package once, identify a symbolic link to a package as that package, and mark the package that `default` links to as the default.

#### Scenario: Opening kms in the editor
- **WHEN** `semantic-model/kms` is opened in the editor
- **THEN** the editor offers `example` once, marked as the default, and does not offer `default` as a second package
