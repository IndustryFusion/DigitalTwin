# Tasks

## 1. SDK

- [x] 1.1 Fail an invalid example without asserts in the example runner; verify unit tests for "A violation nobody asserted", "A violation as asserted" and "A valid example", and that every example of `semantic-model/kms` still meets its expectations (`make kms-check`)
  - Verified: `test_a_violation_is_not_a_reason`, `test_a_list_is_proven_both_ways`; `make kms-check`: 6 of 6 examples of `kms/example` meet their expectations.
- [x] 1.2 Reduce New test… to the purposes `valid` and `invalid` and remove the per-constraint code; verify unit tests for "An attribute with a list", "Written and failing", "Broken but without a reason" and "Finished"
  - Verified: `test_attribute_tests.py`, `test_a_list_is_proven_both_ways`, `test_a_test_it_cannot_write_is_refused`.
- [x] 1.3 Take a valid value from the `sh:in` list, as the term it is; verify unit tests for "Lists of each kind"
  - Verified: `test_a_list_is_proven_both_ways` (texts, integers, doubles, texts that read as other types, booleans; with and without a datatype), `test_a_list_of_terms_is_written_as_terms`.
- [x] 1.4 Offer the items of `sh:in` in the value picker; verify a unit test for "Picked from the list" over lists of texts, numbers, doubles and booleans
  - Verified: `test_a_list_is_proven_both_ways` sets every offered item and sees no violation.
- [x] 1.5 Answer what a case can assert, and which cases are about an attribute, from the validation results; verify unit tests for "A reason named before it fires", "Already asserted" and "A failing test in the list"
  - Verified: `test_a_reason_may_be_named_before_it_fires`, `test_a_list_is_proven_both_ways`, `test_the_tests_about_an_attribute`, `test_the_server_answers_both`.
- [x] 1.6 Keep every generated and edited value of an `xsd:double` attribute declared; verify unit tests for "Generated valid case" and "Generated case that breaks a range"
  - Verified: `test_a_valid_case_declares_its_double`, `test_a_range_broken_by_hand_keeps_its_declared_double_and_breaks_only_the_range`.

## 2. Extension

- [x] 2.1 Ask the two kinds in New test…; verify an extension unit test
  - Verified: `test_new_test_offers_two_things_and_asserts_nothing`, `test_new_test_asks_what_to_show_and_writes_it`.
- [x] 2.2 Case page: the missing reason, adding an assert, removing any assert, and the Clone, Rename and Delete buttons; verify extension unit tests for "No reason yet" and "The last assert removed"
  - Verified: `test_the_case_page_says_what_is_missing_and_offers_everything`, `test_an_assert_is_chosen_from_what_judges_the_case`, `test_any_assert_can_be_removed`.
- [x] 2.3 Attribute editor: the list of tests, opening and deleting, following a validation run; type and shape page: Delete on each case; verify extension unit tests for "Deleted from the attribute editor" and "Deleted from the type page"
  - Verified: `test_the_attribute_editor_lists_its_tests`; deleting also in the end-to-end test.
- [x] 2.4 Describe it in the SemForge README; verify by reading it
  - Verified: `vscode/README.md`, "New test…" and "The test case page"; read in the diff.

## 3. End to end and checks

- [x] 3.1 Add an end-to-end test in VS Code that writes a failing test, breaks its data, asserts what fires, removes the assert and deletes the case from the attribute editor; verify it passes
  - Verified: `vscode/test/e2e/suite/27-fail-case.test.js` passes with VS Code 1.147.0. CI does not run this suite.
- [x] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass and that more than 80 % of the changed code is covered
  - Verified: 2463 passed, 5 skipped, coverage 89 %; changed Python code 92 %; flake8 clean; `openspec validate --all --strict` passes.
