# Tasks

## 1. SDK

- [x] 1.1 Add the start `whole-model` to the test-case writer: every document of every main-model file in load order, written into the case; refused without a main model; verify unit tests in `tests/unit/test_add_test_case.py` for "A model of several files", "The case is a snapshot" and "A package without a main model"
  - Verified: `test_documents_of_every_model_file_are_written_in`, `test_the_case_is_a_snapshot_of_the_model` and `test_no_main_model_no_whole_model_case` pass, and fail without the change.
- [x] 1.2 Name the main model's files in the test-case options and report the start in a written case's result; verify a unit test that the options of the kms corpus name `model-instance.jsonld`
  - Verified: `test_the_options_name_the_main_model_s_files` passes, and fails without the change.
- [x] 1.3 Declare and run the case as the other starts, and set its description from the run unless one is given; verify unit tests for "A good case from a conforming model", "A bad case from a conforming model", "A good case from a violating model" and "A description given"
  - Verified: `test_the_whole_model_is_written_in_and_passes_as_a_good_case`, `test_a_bad_case_from_a_conforming_model_fails_until_edited_and_says_so`, `test_a_violating_model_says_so_in_either_case` and `test_a_description_given_is_kept` pass.
- [x] 1.4 Rewrite a relative `@context` (string or list entry) to name the same file from the case's folder, keeping URLs, absolute paths and objects; verify unit tests for "A model with a relative context" (after `retarget_model(..., 'context.jsonld')` on a corpus copy) and the kinds of context kept
  - Verified: `test_a_relative_context_still_names_the_package_s_context` (fails without the rewrite: "does not load: …/examples/test_StateOnCutterShape/good/context.jsonld") and `test_only_relative_contexts_are_moved` pass.
- [x] 1.5 Declare with the neutral placeholder before the run, and report ids that more than one model file defines; verify unit tests for "A good case that fails for another reason" (the placeholder kept) and "Model files that share an id"
  - Verified: `test_a_run_that_cannot_load_keeps_the_neutral_description` and `test_ids_two_model_files_share_are_reported` pass.
- [x] 1.6 Write the case file through a temporary file and rename, and remove the file and its declaration when anything fails before the outcome is returned; verify unit tests for "A failure after declaring", in an existing and a new suite
  - Verified: `test_a_failure_after_declaring_leaves_nothing_behind[good|bad]` and `test_a_failure_in_a_new_suite_leaves_no_expectations` pass.

## 2. Extension

- [x] 2.1 Offer "The whole main model" in New test case…'s start list when the options name model files, with the file or the number of files, and ask only for the name after it; verify extension unit tests in `tests/unit/test_tree_clicks.py` for "A package with a main model" and the hidden start without one
  - Verified: `test_the_whole_main_model_is_a_start`, `test_several_model_files_are_counted` and `test_no_main_model_no_whole_model_start` pass; the first two fail without the change.
- [x] 2.2 Say "It still violates, as the main model does" for a good case from a violating model; verify an extension unit test on the message
  - Verified: `test_a_good_case_from_a_violating_model_says_why_it_fails` passes, and fails without the change.
- [x] 2.3 Describe the start in the SemForge README; verify by reading the rendered README
  - `vscode/README.md`, "where it starts": the whole main model is listed between a copy of a case and an entity from the model, as a snapshot written into the new file, with the bad-case description; read in the diff.
- [x] 2.4 Say "as the main model does" only when the case has violations, else list its failures; name ids shared by model files in the message; verify extension unit tests
  - Verified: `test_a_good_whole_model_case_failing_otherwise_says_its_failures` and `test_ids_shared_by_model_files_are_said` pass.
- [x] 2.5 Suggest a free name (`whole-model`, `whole-model-2`, …) for the target folder; verify an extension unit test for "The suggested name is free"
  - Verified: `test_the_suggested_name_is_free` passes.

## 3. End to end and checks

- [x] 3.1 Add an end-to-end test (`vscode/test/e2e/suite/26-whole-model-case.test.js`) that starts a bad case from the whole main model in a new suite and checks the file, the declaration, the description, the case page and that the model is untouched; verify it passes with `SEMFORGE_E2E_GREP="whole main model" make test-e2e`
  - Verified: run on its own locally with VS Code 1.147.0, passing. It also passed within a full local run, where 97 passed and 1 failed: the unrelated `23-pages-first.test.js`, which passes on its own. CI does not run this suite.
- [x] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass
  - Verified: `pytest --cov semforge --cov-fail-under=80` 2348 passed, 3 skipped, coverage 88.74%; `flake8 semforge tests` clean; `openspec validate --all --strict` 19/19 passed.
