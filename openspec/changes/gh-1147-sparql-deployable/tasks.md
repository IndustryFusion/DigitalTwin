# Tasks

## 1. The check

- [x] 1.1 Find shacl2flink (`SEMFORGE_SHACL2FLINK`, beside the package, beside SemForge), load its check of SPARQL expressions in process with its modules kept apart, and ask it for a package and for a draft query; verify unit tests for "Named", "Beside the package", "No checkout", "A checkout that cannot be loaded" and that every query of the kms corpus can be deployed ("Every query can be deployed")
  - Verified: `tests/unit/test_deploy.py`: `test_the_named_checkout_is_used`, `test_a_checkout_beside_the_package_is_used`, `test_else_the_checkout_beside_semforge_is_used`, `test_without_a_compiler_nothing_is_said` (editor, capability check and `semforge check`), `test_a_compiler_that_cannot_be_loaded_is_none`, `test_a_named_directory_without_the_check_is_none`, `test_every_query_of_the_corpus_can_be_deployed`.
- [x] 1.2 Mark a refused query in the editor at the line of the compiler's pattern, only when it has no other error, never failing the diagnostics; verify unit tests for "A variable as predicate", "The line of the pattern", "A rule", "Two target classes", "Parts the compiler refuses", "Forms that compile", "A query that does not parse" and "The check fails"
  - Verified: `test_it_is_said_at_the_line_that_is_the_reason`, `test_a_projection_that_repeats_the_pattern_is_not_the_mark`, `test_a_template_that_repeats_the_pattern_is_not_the_mark`, `test_a_function_is_found_in_any_case` and `test_an_iri_counts_as_a_name` ("The line of the pattern"), `test_a_rule_is_checked_as_a_rule`, `test_each_target_class_is_asked` (refusing class sorted first and last) and `test_two_target_classes_in_the_editor`, `test_the_reason_is_said` (UNION, unitCode, REGEX), `test_what_can_be_deployed_is_left_alone`, `test_a_query_that_does_not_parse_has_one_error_not_two`, `test_the_compiler_does_not_fail_the_editor` (the `variable-node` warning stays).
- [x] 1.3 Report each refused query of a package as `SF-CAP-006` and as a `not-deployable` row of `semforge check`; verify unit tests for "In the Problems panel", "A rule in the Problems panel", "In the terminal", "Export" and "Every query can be deployed"
  - Verified: `test_the_problems_panel_and_the_terminal_name_the_constraint` (one `SF-CAP-006`; the `not-deployable` row points at the line where the query starts; exit 1), `test_a_rule_in_the_problems_panel_is_called_a_rule` (also its `semforge check` row), `test_a_problem_refused_alike_for_several_classes_is_named_once`, `test_a_package_check_that_fails_says_nothing`, `test_export_refuses_what_cannot_be_deployed` (exit 2, nothing written), `test_every_query_of_the_corpus_can_be_deployed`.

## 2. What goes

- [x] 2.1 Remove the findings `explicit-node`, `path` and `not-compiled`, their quick fixes, the hover line, the command `semforge.nestForFlink` (its registration, its menu entry and its tests), and the claim on shacl2flink of `variable-node`; verify unit tests for "A named instance and a path", "An attribute no shape nests a payload for" and "The attribute instance read instead of its value", and that the extension's command list no longer has the command
  - Verified: `test_sparql_ngsild.py`: the named instance, the path and a variable predicate are in `test_the_right_forms_are_left_alone`; `test_hover_says_the_form_and_what_flink_knows` (no shacl2flink in the hover of `hasJSON`, which no shape nests); `test_the_attribute_instance_is_said_without_a_word_on_flink`; `test_extension_activates.py` and `test_extension_commands.py` no longer list `semforge.nestForFlink`; its page tests removed with it.
- [x] 2.2 Describe it in the SemForge README; verify by reading it
  - Verified: `vscode/README.md`, "A query that cannot be deployed" and the table of the SPARQL editor; read in the diff.

## 3. End to end and checks

- [x] 3.1 Add an end-to-end test in VS Code that writes a query with `$this ?attribute ?value .`, sees the mark at that line with its reason, and sees it go when the query reads the value ("A variable as predicate", "Fixed while written"); verify it passes
  - Verified: `vscode/test/e2e/suite/06-sparql-editor.test.js`, "what cannot be deployed is said while it is written, and goes when it can", passes with VS Code 1.148.0 (`SEMFORGE_E2E_GREP='the SPARQL editor'`, 12 passing). CI does not run this suite.
- [x] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass and that more than 80 % of the changed code is covered
  - Verified: 2926 passed, 3 skipped; coverage 89.9 %; changed Python code 97.5 % (115 of 118 lines); flake8 clean; `openspec validate --all --strict` passes.
