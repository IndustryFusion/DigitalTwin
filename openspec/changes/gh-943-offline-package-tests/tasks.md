# Tasks

## 1. SERVICE

- [x] 1.1 Before the examples run, every `SERVICE` in the SPARQL of the shapes is found and named by its owner (D1); verify with `tests/unit/test_offline_tests.py` (`test_network_uses_names_targets_and_validators`, `test_services_are_read_from_code_not_from_strings_or_comments`)
  - Constraint as `<shape>/SPARQLConstraintComponent`, rule and target by their shape, validator by its component; `SERVICE` in a string or comment is not one.
- [x] 1.2 `SERVICE` is rejected in constraints, rules and targets, with `--allow-network` too, and no connection is opened (D2); verify with `tests/unit/test_offline_tests.py` ("SERVICE in a constraint", "SERVICE in a rule", "SERVICE with network access allowed")
  - `test_service_in_a_rule_is_refused` and `test_service_in_a_constraint_is_refused`, each with and without the permission: the local listener records no request.
- [x] 1.3 A shapes graph the validator refuses is reported instead of a traceback (D2); verify with `tests/unit/test_offline_tests.py` (`test_shapes_the_validator_refuses_are_reported`)

## 2. No connection

- [x] 2.1 An audit hook refuses every connection, datagram, host name lookup and non-file `urllib` request of the thread running the tests; with `--allow-network` only a context fetch passes (D3); verify with `tests/unit/test_offline_tests.py` (`test_service_that_slips_past_the_scan_is_stopped`)
  - A `SERVICE` query, a `urllib` request and a socket inside the scope fail and the listener sees nothing; with contexts allowed the request and the query still fail; outside the scope the query reaches the listener.

## 3. Contexts

- [x] 3.1 The model keeps its published URL, which resolves from the local file `kms.yaml` declares; a remote context that is neither the package's nor shipped fails, named, and is fetched only with `--allow-network`; a context file outside the package root is refused (D4); verify with `tests/unit/test_offline_tests.py` ("Remote context", "Fetching a remote context")
  - `test_remote_context_is_refused_offline`: exit 2 naming the URL, no request; with `--allow-network` exit 0 and the listener served it. `test_context_file_outside_the_package_is_refused`, `test_the_package_s_own_and_the_pinned_contexts_answer`.
- [x] 3.2 A model naming a context URL that `kms.yaml` does not declare fails with the URL and the line to add (D4); verify with `tests/unit/test_offline_tests.py` ("Own context not declared": `test_an_undeclared_own_context_says_what_to_add`)
- [x] 3.3 The SDK ships the NGSI-LD core context v1.8 byte for byte, checks its SHA-256 on every read, and ships ETSI's licence beside it; both are package data; `Notice.md` lists it (D4); verify with `tests/unit/test_offline_tests.py` ("A changed copy": `test_pinned_contexts_are_checked_against_their_digest`; `test_pinned_contexts_ship_with_etsi_s_licence`) and "A new package offline" (every `semforge init` fixture of the unit suite runs offline)
  - The file is what `https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld` serves (sha256 `4ac48e7d…6cca`); the same JSON, with LF line endings, is `coreContext/ngsi-ld-core-context-v1.8.jsonld` at tag `v1.8.1` (commit db4324df) of `forge.etsi.org/rep/data/ngsi-ld-openapi`, whose `LICENSE` is BSD-3-Clause, "Copyright 2024 ETSI".

## 4. Commands and documentation

- [x] 4.1 `semforge verify --tests` and `semforge publish` take `--allow-network` (contexts only) and report each refusal with exit code 2; `publish` writes and records nothing (D5); verify with `tests/unit/test_offline_tests.py` ("Verifying a package whose rule uses SERVICE", "Publishing a package whose rule uses SERVICE")
  - `test_cli_verify_names_the_rule_and_opens_no_connection` and `test_publish_is_refused`, each with and without the flag: no archive, no `.kms/releases.yaml`, no request.
- [x] 4.2 `semforge verify --help`, `semforge publish --help`, `SemForge-SDK/README.md` and `semantic-model/kms/README.md` describe the offline run, the declared local context, the shipped core context and the rejection of `SERVICE`; verify by reading them

## 5. The packages in semantic-model/kms

- [x] 5.1 `kms/example` passes its tests with every socket connection and lookup failing; verify with `tests/unit/test_offline_tests.py` ("The example package without any network": `test_kms_example_passes_with_no_network_at_all`, no attempt recorded)
  - Also `semforge verify --tests ../kms/example` in a network namespace without any interface (`unshare -rn`): 6 of 6 examples met, exit 0.
- [x] 5.2 Every package in `semantic-model/kms` gives the same result with and without the permission; verify with `tests/unit/test_offline_tests.py` ("Same result with and without the permission": `test_results_are_the_same_with_and_without_the_network`, one test per package)

## 6. Checks

- [x] 6.1 Run the SDK checks the change touches as the `semforge-sdk` Build job does; verify they pass
  - flake8 on `semforge` and `tests` clean; the touched test files (offline, releases, record history, package, review, context, cli, scaffold, corpus validation, rules) 235 passed, coverage of `offline.py` 92 %, `releases.py` 92 %, `context.py` 90 %; the full suite before the rebase onto main passed (2350 passed, 3 skipped, 88.8 %); `bats test/bats-unit/build-workflow.bats` passes.
- [x] 6.2 Run `openspec validate --all --strict`; verify it passes
- [ ] 6.3 Verify that the `semforge-sdk` Build job of this pull request passes, including `make setup` (the shipped context and licence installed as package data) and `kms-check`
