# Delta for KMS Package

## ADDED Requirements

### Requirement: The release record is append-only
An entry of a release record, once published, SHALL be neither removed nor changed: a later record SHALL list every earlier entry under its version with every field present, absent and valued as before, type included, and each version once. Entries MAY be appended. As the record is not a member, this SHALL be checked against its history in version control. Removing a whole package from its directory of packages is not covered by this rule.

#### Scenario: Removed entry
- **WHEN** the record on the base branch lists `1.0.0` and a pull request removes that entry
- **THEN** the check fails and names `1.0.0`

#### Scenario: Changed entry
- **WHEN** a pull request changes the digest of the entry `1.0.0` that the base branch lists
- **THEN** the check fails and names `1.0.0` and the digest, with its value before and after

#### Scenario: Changed type
- **WHEN** a pull request changes `met: 80` of the entry `1.0.0` to `met: "80"`
- **THEN** the check fails and names `1.0.0`, `met` and both values with their types

#### Scenario: Appended entry
- **WHEN** a pull request raises the version to `1.0.1` and publishes it, which appends an entry
- **THEN** the check passes

#### Scenario: Package new in the pull request
- **WHEN** a pull request adds a package under a name the base branch does not have and publishes its first version
- **THEN** the check passes, because the base branch has no record for it

#### Scenario: Package removed in the pull request
- **WHEN** a pull request deletes `kms/example` together with its record
- **THEN** no package is left to compare, and the deletion is for the pull request's review to judge

### Requirement: The release record has a history to compare with
The release record and its `.kms` directory SHALL be plain files and directories, never symbolic links, in the package and in the earlier state; otherwise the record could change without its history showing it. An earlier record that does not parse SHALL fail the comparison. A package without history, such as an archive or an uncommitted package, has no earlier record, and its record SHALL be taken as it is.

#### Scenario: Linked record
- **WHEN** a pull request replaces `.kms/releases.yaml` with a link to another file
- **THEN** the check fails and says that the record is a link

#### Scenario: Linked record on the base branch
- **WHEN** the base branch holds `.kms/releases.yaml`, or `.kms`, as a link and a pull request changes the file behind it
- **THEN** the check fails and says that the record at the base branch is a link

#### Scenario: Broken record on the base branch
- **WHEN** the record on the base branch does not parse
- **THEN** the check fails and says so

#### Scenario: Package without history
- **WHEN** an archive is verified together with a release record
- **THEN** the record is taken as it is, because nothing earlier can be compared with it

### Requirement: A package is identified by its name
A package SHALL be identified by the name in its descriptor. Its earlier records SHALL be the record at its path and the record of every package that declares its name in the same directory of packages in the earlier state. Two packages in one directory of packages SHALL NOT declare the same name. A package whose name the earlier state does not have is new, also when it was renamed and moved at once.

#### Scenario: Moved with a rewritten record
- **WHEN** a pull request moves `kms/example`, whose `1.0.0` is published, to `kms/machine-cell` and changes the digest of `1.0.0` in its record
- **THEN** the check fails and names `1.0.0`, the digest and `kms/example`

#### Scenario: Moved with its record intact
- **WHEN** a pull request moves `kms/example` to `kms/machine-cell` and keeps its record
- **THEN** the check passes and says that it compared with the record of `kms/example`

#### Scenario: Taking a published name
- **WHEN** the base branch holds `kms/example` with `1.0.0` published and `kms/other` with an empty record, and a pull request renames `kms/other` to `example` with an entry `1.0.0` of another digest
- **THEN** the check fails, names the two packages that declare `example`, and names `1.0.0`, the digest and `kms/example`

#### Scenario: Moved onto a removed package's path
- **WHEN** a pull request deletes `kms/other` and moves `kms/example` there, changing the digest of `1.0.0`
- **THEN** the check fails and names `1.0.0`, the digest and `kms/example`

#### Scenario: Renamed and moved
- **WHEN** a pull request moves `kms/example` to `kms/machine-cell` and changes its name to `machine-cell`
- **THEN** it is a new package, and the check passes whatever its record lists

#### Scenario: Default link
- **WHEN** the base branch holds `kms/default`, a link to `kms/example`, and the pull request moves `kms/example`
- **THEN** the link is not taken for a second package named `example`, and the moved package is compared with the record of `kms/example`

#### Scenario: Directory name outside ASCII
- **WHEN** the package of the same name lies at `kms/exämple` on the base branch
- **THEN** it is found and compared like any other

## MODIFIED Requirements

### Requirement: Every package in semantic-model/kms is verified and tested in CI
The `Build` workflow SHALL verify every package in `semantic-model/kms` and run its tests. A package that fails verification, including a published version whose content has changed, SHALL fail the build, and so SHALL an example that does not meet its expectations. Coverage below the threshold SHALL fail the build only for a package whose current version is published. On a pull request, the build SHALL also compare each package's release record with the one on the pull request's base branch and fail when an entry there was removed or changed.

#### Scenario: Broken example on a pull request
- **WHEN** a pull request changes a shape so that an example of `kms/example` no longer meets its expectations
- **THEN** `Build` fails and names the example

#### Scenario: Changed published version on a pull request
- **WHEN** a pull request changes `shacl.ttl` of a package whose version `1.0.0` is published, without raising the version
- **THEN** `Build` fails and reports that `1.0.0` is published and its version must be raised

#### Scenario: Draft with low coverage on a pull request
- **WHEN** a pull request changes `kms/example`, whose version is not published, and its coverage is 5 %
- **THEN** `Build` reports the coverage and does not fail on it

#### Scenario: Rewritten release record on a pull request
- **WHEN** a pull request changes `shacl.ttl` of a package whose version `1.0.0` is published and rewrites the digest of `1.0.0` in its release record to match
- **THEN** `Build` fails and names `1.0.0` and the digest
