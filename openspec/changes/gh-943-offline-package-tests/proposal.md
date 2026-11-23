Issue: #943

## Why

A KMS package's tests run when it is published (`semforge publish`), when it is verified with `semforge verify --tests`, and in the `kms-check` step of the `Build` workflow. Running them is not offline: rdflib evaluates a SPARQL `SERVICE` clause as an outbound HTTP request, and a JSON-LD `@context` that is not resolved locally is fetched, or read from whatever this machine fetched before. Running the tests of an untrusted archive can therefore contact arbitrary hosts, and a test result can depend on what a remote service answers that day. Today this is only documented (review of #940).

## What Changes

- Running a package's tests is offline by default, in `semforge verify --tests` and `semforge publish`, and so in `kms-check`. Nothing is fetched over the network.
- The model keeps its published context URL. The package's own context resolves from the local file `kms.yaml` declares for that URL. A model naming a context URL that `kms.yaml` does not declare fails, and the message names the URL and the line to add.
- The SDK ships the NGSI-LD core context v1.8 byte for byte, checked by its hash, with ETSI's copyright and the BSD-3-Clause licence under which ETSI publishes its JSON-LD context files; `Notice.md` lists it.
- Any other remote context makes the tests fail, naming the URL. Only `http(s)` URLs and files inside the package are read, whatever the spelling of the scheme.
- The NGSI-LD vocabulary resolves from the package, or for the official URL `semforge init` pins from a copy the SDK ships; any other remote vocabulary is fetched only with `--allow-network`. A vocabulary that does not load fails the run, naming its source; today the tests silently run without it.
- `--allow-network` lets the tests fetch such contexts and vocabularies, and nothing else.
- `SERVICE` is rejected in every SPARQL of a package (constraints, rules and targets), with `--allow-network` too, before any example runs and naming where it is. SHACL does not allow it in constraints, the platform's validation cannot run it, and a package's results must not depend on a remote endpoint. Today a constraint with `SERVICE` ends the run in a traceback, and a rule or target with `SERVICE` queries the service.
- Anything else in the test run that tries to open a connection or resolve a host name fails instead, and examples are read only from inside the package.
- `semforge publish` reports tests that cannot run ("tests do not run: …") and writes nothing, instead of a traceback.

## Capabilities

### New Capabilities

### Modified Capabilities
- `contracts/kms-package`: new requirements **SERVICE in a package's SPARQL**, **A package's tests run offline**, **Contexts of a test run resolve from the package**, **The NGSI-LD vocabulary of a test run** and **The tests read only the package's examples**.
- `semforge-sdk/package-tools`: new requirements **Tests run offline unless fetching is allowed**, **The SDK ships the NGSI-LD core context** and **The SDK ships the official NGSI-LD vocabulary**.

## Out of Scope

- Sandboxing anything beyond network access, such as the file system or resource limits.
- The append-only release record (#942).
- `semforge test`, the editor and the other commands that evaluate a package: they keep resolving contexts as today. Only the tests a version is published and verified with are offline.
- shacl2flink: its SPARQL compiler has no translation for `SERVICE` and fails the build of such a constraint, so `SERVICE` cannot reach Flink; it is not changed here.
- Rejecting `SERVICE` when a package is checked without `--tests`: the rejection is part of running its tests, which `kms-check` does for every package.

## Impact

- Components: SemForge SDK (`semforge verify --tests`, `semforge publish`, how the SDK resolves JSON-LD contexts during a test run, the SPARQL in a package's shapes, the NGSI-LD vocabulary during a test run, the shipped core context with its licence and the shipped official vocabulary), `semantic-model/kms/README.md`, `Notice.md`.
- Contract: `contracts/kms-package` gains a requirement on how a package's tests run; the package format and the release record do not change. A package whose SPARQL uses `SERVICE` can no longer be published; none in `semantic-model/kms` does. A package naming another remote context or vocabulary is published and verified with `--allow-network`.
