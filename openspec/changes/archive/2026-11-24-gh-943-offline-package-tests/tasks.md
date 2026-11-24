# Tasks

## 1. SERVICE

- [x] 1.1 Before the examples run, every `SERVICE` in the SPARQL of the shapes is found and named by its owner, also when written with `\u`/`\U` escapes (D1); verify with `tests/unit/test_offline_tests.py` (`test_network_uses_names_targets_and_validators`, `test_services_are_read_from_code_not_from_strings_or_comments`, "SERVICE written with a code point escape": `test_service_written_with_an_escape_is_found`, `test_an_invalid_escape_does_not_parse`)
  - Constraint as `<shape>/SPARQLConstraintComponent`, rule and target by their shape, validator by its component; `SERVICE` in a string or comment is not one; `SERVICE`, `\U00000053ERVICE` and `SERVICE` are refused with `--allow-network` and the listener sees no connection.
- [x] 1.2 `SERVICE` is rejected in constraints, rules and targets, with `--allow-network` too, and no connection is opened (D2); verify with `tests/unit/test_offline_tests.py` ("SERVICE in a constraint", "SERVICE in a rule", "SERVICE with network access allowed")
  - `test_service_in_a_rule_is_refused` and `test_service_in_a_constraint_is_refused`, each with and without the permission: the local listener records no request.
- [x] 1.3 A shapes graph the validator refuses is reported instead of a traceback (D2); verify with `tests/unit/test_offline_tests.py` (`test_shapes_the_validator_refuses_are_reported`)

- [x] 1.4 `SERVICE` is looked for in rdflib's parse tree of each text as the SHACL engine runs it, a text that does not parse is refused, rdflib's evaluation of `SERVICE` is replaced during the run, and a swallowed refusal fails the run (D1); verify with `tests/unit/test_offline_tests.py` ("SERVICE without a space after the keyword": `test_service_in_any_spelling`; "Syntax error in a rule": `test_sparql_that_does_not_parse_is_refused`; `test_declared_prefixes_are_part_of_what_is_parsed`, `test_a_path_in_a_constraint_is_parsed_as_run`, `test_a_swallowed_refusal_fails_the_run`, and the seeded comparison with rdflib's algebra `test_services_agree_with_the_algebra`)

## 2. No connection

- [x] 2.1 An audit hook refuses every connection, datagram, host name lookup and non-file `urllib` request of the thread running the tests; with `--allow-network` only an http(s) context or vocabulary fetch passes, by a flag set around that fetch alone (D3); verify with `tests/unit/test_offline_tests.py` (`test_service_that_slips_past_the_scan_is_stopped`, `test_another_scheme_is_never_read`)
  - A `SERVICE` query, a `urllib` request and a socket inside the scope fail and the listener sees nothing; with fetching allowed the request and the query still fail; `ftp:` and `gopher:` contexts open no TCP connection to the listener, with and without the flag (on 445a3bed the `ftp` case connects and hangs).

## 3. Contexts

- [x] 3.1 The model keeps its published URL, which resolves from the local file `kms.yaml` declares; a remote context that is neither the package's nor shipped fails, named, and is fetched only with `--allow-network`; a context file outside the package root is refused (D4); verify with `tests/unit/test_offline_tests.py` ("Remote context", "Fetching a remote context")
  - `test_remote_context_is_refused_offline`: exit 2 naming the URL, no request; with `--allow-network` exit 0 and the listener served it. `test_context_file_outside_the_package_is_refused`, `test_the_package_s_own_and_the_pinned_contexts_answer`.
- [x] 3.2 The scheme and host are compared in lower case; only http(s) and file inside the package are read; any other scheme is refused, with `--allow-network` too (D4); verify with `tests/unit/test_offline_tests.py` ("Scheme in another spelling", "Another scheme")
  - `test_an_upper_case_scheme_is_still_offline` (`HTTP://…` refused, no connection; `HTTPS://` answered by the shipped copy), `test_a_file_context_outside_the_package_in_any_case` (`FILE:`, `File:`, another host, a plain path outside), `test_another_scheme_is_never_read`.
- [x] 3.3 With `--allow-network` the user's context cache is not read (D4); verify with `tests/unit/test_offline_tests.py` (`test_allow_network_does_not_read_the_user_s_cache`: a cached context is fetched again)
- [x] 3.4 A model naming a context URL that `kms.yaml` does not declare fails with the URL and the line to add (D4); verify with `tests/unit/test_offline_tests.py` ("Own context not declared": `test_an_undeclared_own_context_says_what_to_add`)
- [x] 3.5 The SDK ships the NGSI-LD core context v1.8 byte for byte, reads and hashes it on every read, and ships ETSI's licence beside it; both are package data; `Notice.md` lists it (D4); verify with `tests/unit/test_offline_tests.py` ("A changed copy": `test_pinned_contexts_are_checked_on_every_read`; `test_pinned_contexts_ship_with_etsi_s_licence`) and "A new package offline" (every `semforge init` fixture of the unit suite runs offline)
  - The file is what `https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld` serves (sha256 `4ac48e7d…6cca`); the same JSON, with LF line endings, is `coreContext/ngsi-ld-core-context-v1.8.jsonld` at tag `v1.8.1` (commit db4324df) of `forge.etsi.org/rep/data/ngsi-ld-openapi`, whose `LICENSE` is BSD-3-Clause, "Copyright 2024 ETSI". `Notice.md` differs from main only by its 13-line "Vendored Files" section, line endings unchanged.

- [x] 3.6 rdflib opens no context in a test run: the SDK resolves, checks and reads a file context itself, wherever it is named (D4); verify with `tests/unit/test_offline_tests.py` ("A file context that leaves the package": `test_every_place_a_context_is_named_is_checked`, `test_a_context_file_names_another_context`, `test_a_link_or_a_pipe_is_not_a_context_file`, `test_the_reviewed_spelling_of_a_path`, and 600 seeded spellings in `test_no_spelling_of_a_path_reads_outside`, which watches every file Python opens and a TCP listener)
- [x] 3.7 An allowed fetch is the SDK's own, http(s) at every hop, without `Link` (D4); verify with `tests/unit/test_offline_tests.py` ("Redirect to another scheme": `test_a_redirect_away_from_http_is_not_followed`, contexts and vocabularies; `test_a_redirect_to_http_is_followed_and_a_loop_is_not`; "Link header": `test_a_link_header_is_not_followed`; `test_an_answer_without_end_is_cut_off`)

## 4. The NGSI-LD vocabulary

- [x] 4.1 In a test run the official vocabulary resolves from the shipped copy, hashed on every read; another remote one is fetched only with `--allow-network`, outside the package's cache; a vocabulary that does not load fails the run naming its source (D6); verify with `tests/unit/test_offline_tests.py` ("The official vocabulary offline", "A remote vocabulary that is not shipped", "A package naming the official vocabulary")
  - `test_the_official_vocabulary_is_shipped` (no connection or lookup attempted), `test_a_vocabulary_that_does_not_load_fails_the_run` (verify and publish exit 2 naming the URL, no connection; with `--allow-network` fetched, no `.semforge/cache/deps`), `test_a_shipped_vocabulary_that_fails_its_hash_fails_the_run`; `tests/unit/test_ngsild_source.py` (`test_the_sdk_ships_only_the_pinned_official_vocabulary`). An archive of a fresh `semforge init` package (official vocabulary, pinned) verified with `--tests` under `unshare -rn`: 2 of 2 examples met.
- [x] 4.2 Results with the shipped vocabulary equal a networked run (D6); verify with `tests/unit/test_offline_tests.py` (`test_the_shipped_vocabulary_gives_the_networked_result`, fetching the official URL for real; skipped only without network) and 5.2 for every package in `semantic-model/kms`

- [x] 4.3 A fetched vocabulary is parsed from the verified bytes and written nowhere, a local one is inside the package, and `SEMFORGE_NGSILD` is ignored in a test run (D6); verify with `tests/unit/test_offline_tests.py` (`test_a_fetched_vocabulary_is_not_written_anywhere`, `test_a_vocabulary_file_outside_the_package_is_refused`, "The environment names a vocabulary": `test_the_environment_does_not_choose_the_vocabulary`)

## 5. Commands, examples and documentation

- [x] 5.1 `semforge verify --tests` and `semforge publish` take `--allow-network` (contexts and vocabulary only) and report each refusal with exit code 2; `publish` writes and records nothing (D5); verify with `tests/unit/test_offline_tests.py` ("Verifying a package whose rule uses SERVICE", "Publishing a package whose rule uses SERVICE")
  - `test_cli_verify_names_the_rule_and_opens_no_connection` and `test_publish_is_refused`, each with and without the flag: no archive, no `.kms/releases.yaml`, no request.
- [x] 5.2 `semforge publish` reports tests that cannot run as "tests do not run" and exits 2 without writing (D5); verify with `tests/unit/test_offline_tests.py` ("Publishing a package whose tests cannot run": `test_publish_reports_a_shipped_copy_that_fails_its_hash`, `test_publish_reports_shapes_the_validator_refuses`)
  - Any exception is reported, for `verify --tests` too ("Verifying a package whose tests cannot run": `test_a_context_that_is_none_is_reported`, `test_a_context_url_that_is_none_is_reported`, `test_what_is_not_the_tests_fault_is_not_swallowed`: a KeyboardInterrupt still ends the run).
- [x] 5.3 An example or include outside the package root fails the test run (D7); verify with `tests/unit/test_offline_tests.py` ("Example outside the package": `test_examples_outside_the_package_are_refused`, `..` and absolute)
- [x] 5.4 `semforge verify --help`, `semforge publish --help`, `SemForge-SDK/README.md` and `semantic-model/kms/README.md` describe the offline run, the declared local context, the shipped core context and vocabulary, the schemes read and the rejection of `SERVICE`; verify by reading them

## 6. The packages in semantic-model/kms

- [x] 6.1 `kms/example` passes its tests with every socket connection and lookup failing; verify with `tests/unit/test_offline_tests.py` ("The example package without any network": `test_kms_example_passes_with_no_network_at_all`, no attempt recorded)
  - Also `semforge verify --tests ../kms/example` in a network namespace without any interface (`unshare -rn`): 6 of 6 examples met, exit 0.
- [x] 6.2 Every package in `semantic-model/kms` gives the same result with and without the permission; verify with `tests/unit/test_offline_tests.py` ("Same result with and without the permission": `test_results_are_the_same_with_and_without_the_network`, one test per package)

## 7. Checks

- [x] 7.1 Run the SDK checks the change touches as the `semforge-sdk` Build job does; verify they pass
  - flake8 on `semforge` and `tests` clean; the full SDK suite 2570 passed, 5 skipped, coverage 89.2 % (`offline.py` 94 %, `releases.py` 93 %, `context.py` 94 %); the tests of the two reviews were run against the reviewed commits, and each reviewed case fails or hangs there; the tests that pass there too guard what already held.
- [x] 7.2 Run `openspec validate --all --strict`; verify it passes
- [x] 7.3 Verify that the `semforge-sdk` Build job of this pull request passes, including `make setup` (the shipped context, licence and vocabulary installed as package data) and `kms-check`
  - Build run 45397894532 (head df1629fa), job `semforge-sdk`: `2570 passed, 5 skipped`; `kms-check` verified `kms/example`, `examples 6 of 6 meet their expectations`.
