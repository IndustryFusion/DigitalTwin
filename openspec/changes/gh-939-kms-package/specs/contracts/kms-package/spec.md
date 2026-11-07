# Delta for KMS Package

## Purpose

Defines the KMS package, the unit in which knowledge (ontology), shapes (SHACL
constraints and rules) and a model (NGSI-LD instances) are authored, handed
between components and deployed. It fixes the package's directory form, its
archive form with an intrinsic integrity check, the package digest that
identifies its content, the immutability of published versions, and how
`semantic-model/kms` holds packages.

## ADDED Requirements

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
