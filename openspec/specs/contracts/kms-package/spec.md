# contracts/kms-package Specification

## Purpose
Defines the KMS package, the unit in which knowledge (ontology), shapes (SHACL
constraints and rules) and a model (NGSI-LD instances) are authored, handed
between components and deployed. It fixes the package's directory form, its
archive form with an intrinsic integrity check, the package digest that
identifies its content, the immutability of published versions, the tests a
version must pass before it is published, and how `semantic-model/kms` holds
packages.

## Requirements

### Requirement: A package is a directory with a descriptor
A KMS package SHALL be a directory, the package root, holding the descriptor file `kms.yaml`. The descriptor SHALL declare `name` (letters, digits, `.`, `_` and `-`, starting with a letter or digit), `version` (a semantic version `MAJOR.MINOR.PATCH`) and `format`, the integer version of this format, which is `1`.

#### Scenario: Complete descriptor
- **WHEN** a directory holds the three roles and a `kms.yaml` declaring `name: example`, `version: 1.0.0` and `format: 1`
- **THEN** it is a valid KMS package named `example` at version `1.0.0`

#### Scenario: Descriptor without a version
- **WHEN** `kms.yaml` declares `name` and `format` but no `version`
- **THEN** the package is invalid and the report names the missing `version`

### Requirement: A newer format is refused
A consumer SHALL refuse a package whose `format` is greater than the version it implements, and SHALL say so rather than reading it as an older version.

#### Scenario: Newer format
- **WHEN** a consumer implementing format 1 is handed a package declaring `format: 2`
- **THEN** it refuses the package and reports that format 2 is not supported

### Requirement: Three roles, each one file or one directory
A package SHALL hold three roles, each either as one file or as one directory of documents:

| Role | File | Directory | Documents |
|---|---|---|---|
| knowledge | `knowledge.ttl` | `knowledge/` | `*.ttl` |
| shacl | `shacl.ttl` | `shacl/` | `*.ttl` |
| model-instance | `model-instance.jsonld` | `model-instance/` | `*.jsonld` |

The content of a role SHALL be the union of the graphs of its documents.

#### Scenario: Shapes split over several files
- **WHEN** a package holds `shacl/base.ttl` and `shacl/filter.ttl` instead of `shacl.ttl`
- **THEN** every consumer sees the same shapes graph as for a single `shacl.ttl` holding the union of both files

### Requirement: Where the roles are located
The knowledge and shacl roles SHALL be located at the package root. The model-instance role SHALL be located either at the package root or inside a directory `model/` at the root.

#### Scenario: Model grouped under model/
- **WHEN** a package holds `knowledge.ttl`, `shacl.ttl` and `model/model-instance.jsonld`
- **THEN** all three roles are present

### Requirement: Role directories are read flat and in order
A role directory SHALL be read non-recursively, in byte order of the file names, ignoring names that begin with `.` and files without the role's suffix.

#### Scenario: Nested directory in a role directory
- **WHEN** `model-instance/` holds `plant.jsonld` and a subdirectory `drafts/` with further `.jsonld` files
- **THEN** only `plant.jsonld` is part of the model-instance role

### Requirement: Ambiguous or incomplete packages are invalid
A package SHALL be invalid when a role is missing, when a role is present both as a file and as a directory or at both locations, when a role directory holds no document, when a document of a role does not parse, or when the root holds both `kms.yaml` and another descriptor. The report SHALL name the paths concerned.

#### Scenario: File and directory for one role
- **WHEN** a package holds both `knowledge.ttl` and `knowledge/`
- **THEN** the package is invalid and the report names both paths

#### Scenario: Missing role
- **WHEN** a directory holds a descriptor, knowledge and shacl but no model-instance in either location
- **THEN** the package is invalid and the report names the missing role

#### Scenario: Unparsable document
- **WHEN** `knowledge/extra.ttl` is not valid Turtle
- **THEN** the package is invalid and the report names `knowledge/extra.ttl`

### Requirement: Examples are a suite beside the model, never part of it
A package MAY hold an examples suite in `examples/` at the root or in `model/examples/`, but not both. The suite MAY be organised in arbitrary subdirectories. Documents of the suite SHALL NOT be part of the model-instance role.

#### Scenario: Grouped layout
- **WHEN** a package holds `model/model-instance.jsonld` and `model/examples/test_FilterShape/bad/without-cartridge.jsonld`
- **THEN** the model-instance role holds only the entities of `model/model-instance.jsonld`, and the examples suite holds the case

### Requirement: Packages are standalone
Every file a package needs in order to be read SHALL be inside the package root. A path the descriptor declares (the local context, the NGSI-LD vocabulary, and any later path setting) SHALL be relative and SHALL NOT leave the package root. A URL in the descriptor names where something is published; checking a package SHALL NOT require fetching it.

#### Scenario: Vocabulary outside the package
- **WHEN** the descriptor declares the NGSI-LD vocabulary as `../ontology/ngsild.ttl`
- **THEN** the package is invalid and the report says the path leaves the package root

#### Scenario: Offline verification
- **WHEN** a package or an archive is verified on a machine without network access
- **THEN** verification gives the same result as with network access

### Requirement: The members of a package are defined
The members of a package SHALL be exactly: the descriptor; the local context file, when declared or present as `context.jsonld`; the documents of the three roles; the files of the examples suite; the local NGSI-LD vocabulary file, when declared; and `README.md` and `LICENSE` at the root, when present. No file or directory whose name begins with `.` SHALL be a member. Every other file SHALL NOT be a member, whether or not a version control system tracks it.

#### Scenario: Derived file beside the roles
- **WHEN** the package root holds `model-instance.scorpio.jsonld` next to `model-instance.jsonld`
- **THEN** `model-instance.scorpio.jsonld` is not a member

#### Scenario: Tool state
- **WHEN** the package root holds `.semforge/cache/` and `.kms/releases.yaml`
- **THEN** nothing under `.semforge/` or `.kms/` is a member

### Requirement: The archive form
A packed package SHALL be a zip archive named `<name>-<version>.kms.zip` by default, whose entries are the members, each at its path relative to the package root with `/` as separator and no enclosing directory, plus one entry `SHA256SUMS` at the root. The archive SHALL hold no other entries, and every entry SHALL be a regular file.

#### Scenario: Name of the file
- **WHEN** the package named `example` at version `1.0.0` is packed without an explicit output name
- **THEN** the archive is named `example-1.0.0.kms.zip`

### Requirement: SHA256SUMS lists every other entry
`SHA256SUMS` SHALL hold one line per other entry, of the form `<sha256 in 64 lowercase hex digits><two spaces><path>` followed by a line feed, sorted by path in byte order, listing every other entry exactly once.

#### Scenario: Checking with standard tools
- **WHEN** a packed package is extracted with a standard unzip tool and `sha256sum -c SHA256SUMS` is run in the extraction directory
- **THEN** every listed file is reported as OK

### Requirement: The package digest identifies the content
The package digest SHALL be `sha256:` followed by the SHA-256, in lowercase hex, of the bytes of `SHA256SUMS`, which for a directory are the bytes its archive would hold. Archives with the same members and contents SHALL have the same digest, whatever their compression, timestamps or entry order. Any change to a member's path or content SHALL change the digest.

#### Scenario: Same content, different archive
- **WHEN** the same package is packed once with compression and once without
- **THEN** both archives have the same package digest

#### Scenario: One changed byte
- **WHEN** one byte of `shacl.ttl` changes and the package is packed again
- **THEN** the package digest differs

### Requirement: Packing is deterministic
Packing the same package twice with the same packer SHALL produce byte-identical archives: `SHA256SUMS` first, then the members in byte order of their paths, every entry timestamped 1980-01-01 00:00:00, no archive comment and no attributes beyond a regular-file mode.

#### Scenario: Pack twice
- **WHEN** a package is packed, then packed again without any change
- **THEN** the two archives are byte-identical

### Requirement: An archive is verified before any of it is used
A consumer SHALL verify an archive before using any of its content, and SHALL use none of it if verification fails. Verification SHALL consist of the integrity check followed by the package check of the extracted tree.

#### Scenario: Valid archive
- **WHEN** an archive passes verification
- **THEN** the consumer reports its name, version and package digest, and reads the same roles and graphs as from the directory it was packed from

### Requirement: The integrity check rejects inconsistent archives
The integrity check SHALL fail, naming the offending entry, when `SHA256SUMS` is missing or malformed, an entry is not listed, a listed path has no entry, an entry's SHA-256 differs from its listed value, or two entries have the same path.

#### Scenario: Modified member
- **WHEN** one byte of `knowledge.ttl` inside the archive is changed without updating `SHA256SUMS`
- **THEN** verification fails and names `knowledge.ttl`

#### Scenario: Added file
- **WHEN** an entry `extra.ttl` that `SHA256SUMS` does not list is added to the archive
- **THEN** verification fails and names `extra.ttl`

### Requirement: The integrity check rejects unsafe archives
The integrity check SHALL fail, naming the offending entry and writing nothing outside the extraction directory, when a path is absolute, contains a `..` segment or `\`, or is empty; when an entry is a link, encrypted, or a directory carrying data; or when the total uncompressed size exceeds the consumer's limit, which SHALL default to 512 MiB.

#### Scenario: Path escaping the package
- **WHEN** the archive holds an entry `../evil.ttl`, even one listed in `SHA256SUMS`
- **THEN** verification fails before anything is written outside the extraction directory

#### Scenario: Oversized archive
- **WHEN** the entries of an archive add up to more than 512 MiB uncompressed and no other limit is configured
- **THEN** verification fails without extracting the archive

### Requirement: An archive must hold a valid package
After the integrity check passes, the extracted tree SHALL be checked as a package, and the archive SHALL be rejected if the tree is not a valid package.

#### Scenario: Consistent but invalid package
- **WHEN** `SHA256SUMS` matches every entry but the archive holds both `shacl.ttl` and `shacl/base.ttl`
- **THEN** verification fails because the tree is not a valid package

### Requirement: Published versions are immutable
A package MAY carry a release record `.kms/releases.yaml` listing each published version with its package digest and date. The same name and version SHALL always mean the same digest. A package whose current version is listed in its release record with a digest other than its current digest SHALL fail verification, and the report SHALL name the version and say that it must be raised.

#### Scenario: Changed after publishing
- **WHEN** version `1.0.0` of `example` is listed as published and `shacl.ttl` is changed afterwards
- **THEN** verification fails with a report that `example 1.0.0` is published and its version must be raised

#### Scenario: Raised after a change
- **WHEN** the version of that package is then raised to `1.0.1`, which the record does not list
- **THEN** verification passes, and the package is a draft until `1.0.1` is published

### Requirement: Only tested versions are published
A version SHALL be published only when every example of the package's suite meets its expectations and the package's coverage is at least its threshold. The threshold SHALL be `tests.coverage` in `kms.yaml`, a percentage from 0 to 100, and SHALL default to 80. Packing, verifying and deploying a version that is not published SHALL NOT depend on its tests or coverage.

#### Scenario: Failing example
- **WHEN** one example of the suite does not meet its expectations
- **THEN** the version is not published, and the report names the example

#### Scenario: Coverage below the threshold
- **WHEN** 70 of 100 constraints are covered and the package declares no threshold
- **THEN** the version is not published, and the report gives the coverage of 70 % against 80 % and lists the constraints that are not covered

#### Scenario: Declared lower threshold
- **WHEN** a package declares `tests.coverage: 60`, all examples meet their expectations and 70 of 100 constraints are covered
- **THEN** the version is published, and its release record shows the threshold of 60

#### Scenario: Draft below the threshold
- **WHEN** a package that is not published has a coverage of 5 %
- **THEN** it can still be packed, verified and deployed

### Requirement: Coverage counts the constraints that fire
Coverage SHALL be the share, in percent, of the package's constraints for which at least one example of the suite asserts that the constraint fires, and it does. A constraint SHALL be identified by its shape, its path and its constraint component; SHACL-SPARQL constraints SHALL count like any other. Inference rules and the model-instance role SHALL NOT count. A package without constraints SHALL have a coverage of 100 %.

#### Scenario: Satisfied but never fired
- **WHEN** a `sh:maxInclusive` constraint holds in every good example and no bad example asserts it
- **THEN** it is not covered

#### Scenario: Fired as asserted
- **WHEN** a bad example asserts that the `sh:maxInclusive` constraint fires, and it fires on that example
- **THEN** it is covered

#### Scenario: Scratchpad
- **WHEN** an entity in `model-instance.jsonld` violates a constraint that no example asserts
- **THEN** the constraint is not covered

### Requirement: The release record holds the test results
For each published version, the release record SHALL list, beside its digest and date, the number of examples, the number that met their expectations, the coverage and the threshold that applied. The release record is not a member and is not inside the archive; the examples are, so the tests of an archive can be run again anywhere and compared with the record of the package it was published from.

#### Scenario: Evidence of a release
- **WHEN** `example` 1.0.0 is published with 80 examples, all met, and 83 % coverage under the default threshold
- **THEN** its entry in `.kms/releases.yaml` lists the digest, the date, 80 examples, 80 met, 83 % and 80 %

### Requirement: Every package in semantic-model/kms is verified and tested in CI
The `Build` workflow SHALL verify every package in `semantic-model/kms` and run its tests. A package that fails verification, including a published version whose content has changed, SHALL fail the build, and so SHALL an example that does not meet its expectations. Coverage below the threshold SHALL fail the build only for a package whose current version is published.

#### Scenario: Broken example on a pull request
- **WHEN** a pull request changes a shape so that an example of `kms/example` no longer meets its expectations
- **THEN** `Build` fails and names the example

#### Scenario: Changed published version on a pull request
- **WHEN** a pull request changes `shacl.ttl` of a package whose version `1.0.0` is published, without raising the version
- **THEN** `Build` fails and reports that `1.0.0` is published and its version must be raised

#### Scenario: Draft with low coverage on a pull request
- **WHEN** a pull request changes `kms/example`, whose version is not published, and its coverage is 5 %
- **THEN** `Build` reports the coverage and does not fail on it

### Requirement: Pull requests compare release records with the base branch
On a pull request, the build SHALL also compare each package's release record with the one on the pull request's base branch and fail when an entry there was removed or changed.

#### Scenario: Rewritten release record on a pull request
- **WHEN** a pull request changes `shacl.ttl` of a package whose version `1.0.0` is published and rewrites the digest of `1.0.0` in its release record to match
- **THEN** `Build` fails and names `1.0.0` and the digest

### Requirement: semantic-model/kms is a directory of packages
`semantic-model/kms` SHALL hold KMS packages, one per subdirectory named after the package, and `default`, a relative symbolic link to one of them. A component that needs a KMS and is given none SHALL use `kms/default`. A subdirectory that is not a package SHALL be ignored, and a link to a package SHALL NOT be counted as a second package.

#### Scenario: Default package
- **WHEN** shacl2flink's build is run without naming a KMS
- **THEN** it reads the package that `kms/default` links to, which is `kms/example`

#### Scenario: Directory of examples
- **WHEN** `kms/SchweissenUndSchneiden/` holds Turtle and JSON-LD files but no `kms.yaml`
- **THEN** no tool treats it as a package

#### Scenario: Listing the packages
- **WHEN** a tool lists the packages in `semantic-model/kms`
- **THEN** `example` appears once and is marked as the default

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

### Requirement: SERVICE in a package's SPARQL
A SPARQL constraint, rule or target of a package that uses `SERVICE`, however the keyword is written, SHALL make the package's tests fail before any example runs, naming the constraint, rule or target and the service, whether or not the caller allows network access, and no connection to the service SHALL be opened.

#### Scenario: SERVICE in a constraint
- **WHEN** a package's tests are run and a SPARQL constraint of shape `ex:RemoteShape` uses `SERVICE <http://127.0.0.1:8890/sparql>`
- **THEN** the tests fail naming `ex:RemoteShape/SPARQLConstraintComponent` and the service, and no connection to the service is opened

#### Scenario: SERVICE in a rule
- **WHEN** a package's tests are run and a SPARQL rule of shape `ex:RemoteRuleShape` uses `SERVICE <http://127.0.0.1:8890/sparql>`
- **THEN** the tests fail before any example runs, naming `ex:RemoteRuleShape` and the service, and no connection to the service is opened

#### Scenario: SERVICE with network access allowed
- **WHEN** the same tests are run with network access allowed
- **THEN** they fail the same way, and no connection to the service is opened

#### Scenario: SERVICE written with a code point escape
- **WHEN** a SPARQL rule writes the keyword as `\u0053ERVICE` or `\U00000053ERVICE`
- **THEN** the tests fail the same way

#### Scenario: SERVICE without a space after the keyword
- **WHEN** a SPARQL rule uses `SERVICE:sparql { … }` or `FILTER(?b<2).SERVICE?u { … }`
- **THEN** the tests fail the same way

### Requirement: SPARQL that does not parse fails the tests
A SPARQL constraint, rule or target that does not parse, with the prefixes declared for it, SHALL make the package's tests fail before any example runs, naming the constraint, rule or target.

#### Scenario: Syntax error in a rule
- **WHEN** a package's tests are run and the SPARQL rule of shape `ex:BrokenShape` has a syntax error
- **THEN** the tests fail naming `ex:BrokenShape`, and no example runs

### Requirement: A package's tests run offline
Running a package's tests SHALL open no network connection and resolve no host name, except to fetch a JSON-LD context or the NGSI-LD vocabulary when the caller explicitly allows it. When the tests need nothing remote, their result SHALL be the same with and without that permission.

#### Scenario: The example package without any network
- **WHEN** the tests of `kms/example` are run on a machine without network access
- **THEN** every example meets its expectations, and no connection or host name lookup is attempted

#### Scenario: Same result with and without the permission
- **WHEN** the tests of any package in `semantic-model/kms` are run once without and once with fetching allowed
- **THEN** both runs report the same examples, the same examples met, and the same covered constraints

### Requirement: Contexts of a test run resolve from the package
While a package's tests run, the model SHALL keep naming its published context URL, which SHALL resolve from the local context file the descriptor declares for it. Other contexts SHALL resolve only from a file inside the package or from a copy the consumer ships, pinned by its content. Unless fetching is allowed, any other context SHALL fail the tests, naming its URL and, for an undeclared own context, what to declare.

#### Scenario: Remote context
- **WHEN** a model of the package names, beside its published context, a remote context that is not pinned, and the tests are run without fetching allowed
- **THEN** the tests fail naming the context's URL, and nothing is fetched

#### Scenario: Own context not declared
- **WHEN** the model names `https://example.org/ctx.jsonld` as its context and `kms.yaml` declares no published context of that URL
- **THEN** the tests fail naming the URL and saying to add `published: https://example.org/ctx.jsonld` under `context:` in `kms.yaml`, and nothing is fetched

#### Scenario: Scheme in another spelling
- **WHEN** a context is named `HTTP://127.0.0.1:8890/ctx.jsonld`, or a file outside the package as `FILE:///…`
- **THEN** it is treated like its lower-case spelling: the tests fail naming it, and nothing is fetched or read

#### Scenario: Another scheme
- **WHEN** a context is named by a URL whose scheme is neither http, https nor file, such as `ftp://127.0.0.1:8890/ctx.jsonld`
- **THEN** the tests fail naming it, with fetching allowed too, and no connection is opened

#### Scenario: A file context that leaves the package
- **WHEN** a context, at any place a context can be named, is a file name that leads outside the package root, through `..`, percent-encoding, a `#` or `?` in it, or a symbolic link
- **THEN** the tests fail naming it, with fetching allowed too, and the file is not opened

### Requirement: An allowed fetch stays on http and https
When fetching is allowed, a context or vocabulary SHALL be fetched over http or https only, at every redirect, and only the document at the URL SHALL be read: no alternate a server names, and no file. A fetch that fails, takes too long or returns too much SHALL fail the tests, naming the URL.

#### Scenario: Redirect to another scheme
- **WHEN** fetching is allowed and the server of a context or vocabulary redirects to an `ftp:` or `file:` URL
- **THEN** the tests fail, no connection is opened to the new address and no file is read

#### Scenario: Link header
- **WHEN** fetching is allowed and the server of a context answers with a `Link` header naming a file as its alternate
- **THEN** the file is not read

### Requirement: The NGSI-LD vocabulary of a test run
While a package's tests run, its NGSI-LD vocabulary SHALL resolve from a file inside the package or from a copy the consumer ships, pinned by its content; it SHALL be fetched only when the caller allows it. A package that names none SHALL use the official vocabulary, whatever the environment names. A vocabulary that does not load SHALL fail the tests, naming its source.

#### Scenario: The official vocabulary offline
- **WHEN** a package names the official NGSI-LD vocabulary URL, pinned, and its tests are run without network access
- **THEN** the vocabulary resolves from the shipped copy and the tests run

#### Scenario: A remote vocabulary that is not shipped
- **WHEN** a package names another remote vocabulary and its tests are run without fetching allowed
- **THEN** the tests fail naming the vocabulary's source, and nothing is fetched

#### Scenario: The environment names a vocabulary
- **WHEN** a package names no vocabulary and the environment names a default one for such packages
- **THEN** its tests run with the official vocabulary

### Requirement: The tests read only the package's examples
While a package's tests run, an example or an include that resolves outside the package root SHALL fail the tests, naming it.

#### Scenario: Example outside the package
- **WHEN** an expectations entry names `../../../../outside.jsonld` or an absolute path
- **THEN** the tests fail naming the entry, and the file is not read
