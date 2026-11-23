# Delta for Package Tools

## ADDED Requirements

### Requirement: Tests run offline unless fetching is allowed
`semforge verify --tests` and `semforge publish` SHALL run a package's tests offline, as the KMS package contract defines it. With `--allow-network` they SHALL fetch remote JSON-LD contexts and the NGSI-LD vocabulary that neither the package nor the SDK holds, and allow nothing else. When the tests use `SERVICE` or cannot run, both SHALL say why, naming what is concerned, and exit with code 2; `semforge publish` SHALL then write and record nothing.

#### Scenario: Verifying a package whose rule uses SERVICE
- **WHEN** `semforge verify --tests` is run, with or without `--allow-network`, on a package whose SPARQL rule of shape `ex:RemoteRuleShape` uses `SERVICE`
- **THEN** it names `ex:RemoteRuleShape` and the service, opens no connection and exits with code 2

#### Scenario: Publishing a package whose rule uses SERVICE
- **WHEN** `semforge publish` is run, with or without `--allow-network`, on that package
- **THEN** no archive is written, `.kms/releases.yaml` is unchanged, the rule is named, no connection is opened and the exit code is 2

#### Scenario: Publishing a package whose tests cannot run
- **WHEN** `semforge publish` is run on a package whose tests cannot run, for instance because the validator refuses its shapes
- **THEN** it reports "not published; nothing written" and that the tests do not run, with the reason, writes nothing and exits with code 2

#### Scenario: Verifying a package whose tests cannot run
- **WHEN** `semforge verify --tests` is run on a package whose tests cannot run, for instance because a context answers 404, is not JSON, names no file or is not a valid URL
- **THEN** it reports that the tests do not run, with the reason, and exits with code 2

#### Scenario: Fetching a remote context
- **WHEN** `semforge verify --tests --allow-network` is run on a package whose model also names a remote context that is not pinned
- **THEN** the context is fetched, this machine's cache of fetched contexts is not read, and it exits with code 0 when the examples meet their expectations

### Requirement: The SDK ships the NGSI-LD core context
The SDK SHALL ship, byte for byte and checked by its hash on every read, the NGSI-LD core context that the packages it creates name, together with the copyright and licence under which ETSI publishes it, so that a package's tests need no network to resolve it.

#### Scenario: A new package offline
- **WHEN** a package created by `semforge init` is verified with `--tests` on a machine without network access
- **THEN** its context, which names the NGSI-LD core context, resolves, and the tests run

#### Scenario: A changed copy
- **WHEN** the shipped copy of the core context differs from the hash the SDK pins
- **THEN** the tests do not run, and the report names the copy

### Requirement: The SDK ships the official NGSI-LD vocabulary
The SDK SHALL ship, byte for byte and checked by its hash on every read, the official NGSI-LD vocabulary that `semforge init` pins by default, so that a package naming it needs no network to run its tests.

#### Scenario: A package naming the official vocabulary
- **WHEN** a package whose `ngsild:` names the official vocabulary URL with its `sha256` is verified with `--tests` on a machine without network access
- **THEN** the vocabulary resolves from the shipped copy, and the tests run
