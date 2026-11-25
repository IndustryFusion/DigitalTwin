# Tasks

## 1. Test runs

- [ ] 1.1 A test run reads no parsed graph and no statement index, from disk or from an earlier read of it (D1, D3); verify with `tests/unit/test_run_without_caches.py` ("Changed parsed triples in a package directory": `test_emptied_triples_do_not_decide`; "Cached triples that would hide a violation": `test_a_violated_example_is_not_hidden`; "Changed index of a file": `test_a_changed_statement_index_does_not_decide`, `test_an_index_kept_in_memory_does_not_decide`), which fail without the change except for the index of `shacl.ttl`, which a test run does not read
- [ ] 1.2 No other cache is read: dependencies, contexts, the user's contexts and the editor's verdicts; verify with `test_no_other_cache_decides` and `test_a_test_run_touches_no_cache`, which watches every path Python opens
- [ ] 1.3 A test run writes no cache (D2); verify with `test_a_test_run_touches_no_cache` ("Nothing kept") and `test_a_linked_cache_directory_is_not_written_through`

## 2. Elsewhere

- [ ] 2.1 Outside test runs the caches are read and written as before, with no more work per file; verify with `test_elsewhere_the_cache_is_read_before_and_after_a_test_run` and the existing `tests/unit/test_graphcache.py`

## 3. Documentation and checks

- [ ] 3.1 `semforge verify --help`, `SemForge-SDK/architecture.md` and `semantic-model/kms/README.md` say that a test run uses no cache; verify by reading them
- [ ] 3.2 Run flake8 and the full SDK test suite as the `semforge-sdk` Build job does; verify they pass
- [ ] 3.3 Run `openspec validate --all --strict`, and the archive in a throwaway copy; verify they pass
