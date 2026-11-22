# Tasks

## 1. Tests first

- [x] 1.1 Add `tests/unit/test_crosscheck_expected.py` with the probe package of #958's task 4.2, built from `shacl2flink/tests/jsonld-number-vectors.json` (one Filter per row, on an `xsd:double`, an `xsd:integer` and an `sh:or` attribute). Assert that the cross-check reports no missed or extra difference on it and lists exactly the strings and `true` on the `sh:or` attribute as expected, each with its reason. Verify that it fails before the change (1 missed and 7 extra) and is not skipped where the cross-check's dependencies are installed.
  - `test_the_probe_package_cross_checks_with_only_expected_differences`: before the change the probe gave 1 missed and 7 extra, and the test failed; after it, the test passes with 7 expected entries. It ran rather than skipped, with `SEMFORGE_CROSSCHECK_PYTHON` set to an interpreter that has shacl2flink's dependencies.
- [x] 1.2 In the same file, add unit tests of the comparison for the scenarios: the `sh:or` merge (one to one, same entity and attribute, only for an `sh:or` of datatypes), strings read as an admitted datatype, and differences that must stay unexpected (numbers, a string whose text is not admitted, text that is no number, other constraint types, a datatype alert pyshacl does not raise). Verify that they fail before the change where they test a new expected entry, and pass after it.
  - The merge tests (`test_a_failing_sh_or_named_after_its_datatype_check_is_one_expected_difference`, `test_the_merge_pairs_one_to_one`), the six cases of `test_a_string_the_compiled_sql_reads_as_an_admitted_number_is_expected` and `test_only_the_surplus_of_a_key_is_classified` failed with main's `crosscheck.py`. `test_a_real_difference_stays_unexpected` (8 cases), `test_an_sh_or_that_is_not_of_datatypes_is_not_merged`, `test_the_merge_needs_the_same_entity_and_attribute` and `test_a_difference_the_compiled_sql_reports_alone_stays_missed` pass on both sides, as they should. All pass after the change.
  - Added in review:
    - `test_a_string_s_sh_or_is_no_partner_for_another_value_s_datatype_alert`
    - `test_a_surplus_the_counts_cannot_attribute_stays_a_difference`
    - `test_a_bounded_branch_keeps_its_violation_a_difference`
    - `test_a_declared_string_is_recorded_as_declared`
    - new cases of `test_a_real_difference_stays_unexpected`: a declared `xsd:string`, Arabic-Indic digits, a trailing newline
  - Each of these fails against the reviewed implementation or against a mutant of the fix: no `re.ASCII`/`fullmatch`, no check of branch constraints, no ambiguity rule. All of them pass with the fix.
- [x] 1.3 Add tests that the command prints the agreement line when every difference is expected and omits it otherwise, that a missing shacl2flink names `--shacl2flink <path>`, and that a relative `--shacl2flink` resolves where it was given. Verify by running the file.
  - `test_the_command_says_the_sql_agrees_when_every_difference_is_expected`, `test_the_command_does_not_say_so_with_a_real_difference`, `test_a_missing_compiler_names_the_option_that_finds_it` and `test_a_relative_compiler_path_is_taken_from_where_it_was_given` pass. The first, third and fourth failed before the change.
- [x] 1.4 Add a test to `tests/unit/test_profile_drift.py` that reads the text patterns of shacl2flink's `sh:datatype` check and compares them with the cross-check's copy. Verify that it fails when either pattern is changed.
  - `test_strings_are_read_by_the_compiler_s_patterns` reads `undeclared_double` and the `xsd:integer` pattern from `lib/shacl_properties_to_sql.py`. It failed without the SDK's copy and passes with it.

## 2. SemForge SDK

- [x] 2.1 Record the rejected value, its datatype and the admitted datatypes on a pyshacl result, outside its identity and equality, and keep them through the editor's verdict cache (D1). Verify the adapter test of task 1.1 and `tests/unit/test_verdicts.py` pass.
  - The three fields are declared with `compare=False`. `test_pyshacl_reports_the_value_and_what_the_constraint_admits`, `test_what_a_result_records_of_a_value_and_its_constraint` and `tests/unit/test_verdicts.py` pass.
- [x] 2.2 Categorise the two divergences as expected in the cross-check, with their reasons, and print the agreement line when every difference is expected (D2 to D4). Verify that tasks 1.1 to 1.4 pass.
  - All tests of `test_crosscheck_expected.py` and `test_profile_drift.py` pass. `test_target.py` and `test_export_contract.py` still pass, and the kms corpus still agrees.
- [x] 2.3 Name `--shacl2flink <path>` in the message for a missing shacl2flink, and resolve the path before the build changes directory. Verify task 1.3.
  - Verified by the tests of task 1.3.
- [x] 2.4 State in the README that the cross-check compiles the model, not the examples, what it lists as expected, and how to point it at shacl2flink. Verify by reading the `--cross-check sqlite` row against the documentation requirement.
  - The README row names `model-instance.jsonld` and states that `examples/` is not compiled. It lists the three kinds of expected difference with their reasons, points to `expected-divergences.txt` and names `--shacl2flink <path>`. The command example shows the option.

## 3. CI and verification

- [x] 3.1 Install sqlite3 with its PCRE extension and `requirements-crosscheck.txt` in the SemForge SDK job of `.github/workflows/build.yaml`. Verify in the Pull Request's Build run that the probe test of task 1.1 runs and passes rather than skipping.
  - Build run 45047939737 (head 7776ffa1), job `semforge-sdk`: `install-sqlite-pcre.sh` built `pcre2.so` from the pinned commit, and `tests/unit/test_crosscheck_expected.py` ran with every test passing, none skipped.
- [x] 3.2 Run `make lint test` of the SDK and `openspec validate --all --strict`. Verify that both pass, and report per scenario of the delta specification which test covers it in the Pull Request.
  - flake8 on `semforge` and `tests` is clean, and `openspec validate --all --strict` passes 19 of 19.
  - On the full suite, coverage was 88.76 %. All failures were environmental: subprocesses could not import `semforge` from the worktree. The 10 affected files then passed 216 of 216 with `PYTHONPATH` set to the SDK.
  - Scenarios and the tests that cover them, for the Pull Request:
    - A string read as a double, and A string read as an integer inside an sh:or: the string-expected cases and the probe test.
    - A failing sh:or named twice: the merge tests.
    - A string whose text the constraint does not admit, and A difference on a number: `test_a_real_difference_stays_unexpected`.
    - The probe of every number: the probe test.
    - Package outside the repository: `test_a_missing_compiler_names_the_option_that_finds_it`.
    - Cross-check on numbers: the probe test, where no number differs.
