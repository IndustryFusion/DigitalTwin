# Delta for Package Tools

## ADDED Requirements

### Requirement: Verify the release record against its history
`semforge verify --against REF DIRECTORY` SHALL also compare the package's `.kms/releases.yaml` with its earlier records at the git ref `REF`. It SHALL exit 2, naming version, field and both values, when the record breaks the contract's rules on it; pass when entries were only appended or there is no earlier record, and say which; and exit 2 for an archive, a directory outside git or an unknown `REF`.

#### Scenario: Unchanged record
- **WHEN** `semforge verify --against origin/main semantic-model/kms/example` is run and the record equals the one on `origin/main`
- **THEN** it succeeds and says how many entries it kept and that none were appended

#### Scenario: Changed date
- **WHEN** the date of the entry `1.0.0` was changed from `2026-11-07` to `2026-11-08`
- **THEN** it exits 2 with a report that names `1.0.0`, the date, `2026-11-07` and `2026-11-08`

#### Scenario: Moved package
- **WHEN** the package was moved since `REF` and `REF` has no record at its path
- **THEN** it compares with the record of the package of the same name at `REF`, and a report names that package's path at `REF`

#### Scenario: No record at the ref
- **WHEN** `REF` has no `.kms/releases.yaml` at the package's path and no package of its name with one
- **THEN** it succeeds and says that there is nothing to keep

#### Scenario: Record at the ref that cannot be read
- **WHEN** `REF` lists the record at the package's path, but reading it fails
- **THEN** it exits 2 and says that the record at `REF` cannot be read, instead of taking the record as absent

#### Scenario: Archive
- **WHEN** `semforge verify --against origin/main example-1.0.0.kms.zip` is run
- **THEN** it exits 2 and says that an archive has no history

#### Scenario: Unknown ref
- **WHEN** `REF` names no commit, as in a shallow clone that has not fetched it
- **THEN** it exits 2 and says that `REF` is not a commit
