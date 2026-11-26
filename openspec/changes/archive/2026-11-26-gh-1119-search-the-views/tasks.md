# Tasks

## 1. SDK

- [x] 1.1 Prune a view's answer to the rows that fit a search and the rows above them, in summary and full form; verify unit tests in `tests/unit/test_search.py` for "An attribute in all four views", "Words in any order and case", "A fitting row without fitting rows" and "Nothing fits", and that an answer without a search is unchanged
  - Verified: `test_only_what_fits_and_what_it_is_under`, `test_an_attribute_is_found_in_all_four_areas[summary|full]` and `test_without_a_search_nothing_changes` pass.
- [x] 1.2 Let a row fit by its statement, its case's description and asserts, and say what was found; verify unit tests for "A value a shape lists", "What a case asserts", "A count" and "An entity's type"
  - Verified: `test_a_listed_value_finds_the_shape_that_lists_it`, `test_a_case_is_found_by_what_it_asserts`, `test_a_count_is_nothing_a_row_says` and `test_an_entity_is_of_its_type_its_attributes_are_not` pass.
- [x] 1.3 Name the hidden rows under a partly hidden row; verify a unit test that they are named with what edits need, and only then
  - Verified: `test_hidden_rows_are_still_named_for_the_edits` passes: hidden rows are named in `all` with what the edits read, and nothing is added when no row is hidden.
- [x] 1.4 Answer which page a line of a file is about, for the text as shown; verify unit tests for "A line of a shape", "A term of the knowledge", "An entity", "A file that cases include", "A declaration of a case", "A file with unsaved lines", "A line without a page" and "A file outside any package"
  - Verified: `test_a_line_of_the_shapes_is_its_shapes_page`, `test_a_line_of_the_knowledge_is_the_page_of_its_term`, `test_a_line_of_the_data_is_its_entity`, `test_an_unsaved_line_is_one_of_the_text_shown` and `test_a_line_about_nothing_with_a_page_is_searched_for` pass; the unsaved case lands elsewhere when the text is not sent.

## 2. Extension

- [x] 2.1 Add Search…, its key and buttons, Clear the search, the count above the rows and the rows opened down to what fits; verify unit tests on the contributions and by the end-to-end test
  - Verified: `test_every_view_offers_the_search_and_every_file_the_way_back` and `test_a_view_says_how_many_fit_and_opens_down_to_them` (count, an answer to an older text, rows opened, ids per search) pass, and the end-to-end test.
- [x] 2.2 Decide the taken instances, a type's own shape and the file an entity is added to by the hidden rows too; verify an extension unit test for "An attribute whose row is hidden"
  - Verified: `test_an_attribute_whose_row_is_hidden_is_still_taken` passes: the default instance is offered as another observation and its time is asked for.
- [x] 2.3 Add Open in SemForge to the title bar and context menu of the three kinds of files; verify unit tests on the contributions and on the message without a file
  - Verified: `test_every_view_offers_the_search_and_every_file_the_way_back` (menus) and `test_open_in_semforge_needs_a_file` pass.
- [x] 2.4 Describe search and Open in SemForge in `vscode/README.md`; verify by reading it
  - `vscode/README.md`, "Search, and the way back from a file": read in the diff.

## 3. End to end and checks

- [x] 3.1 Add an end-to-end test `vscode/test/e2e/suite/28-search.test.js`: Search… filters all four views, shows SemForge Details, says the count, is kept on Enter, put back on Escape and cleared, a found row opens its page, and Open in SemForge opens a shape's page, also with unsaved lines above; verify `make test-e2e` passes it
  - Verified: `SEMFORGE_E2E_GREP="search in the views" make test-e2e` with VS Code 1.148.0: 4 passing. `Build` does not run this suite.
- [x] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass, with the coverage of the new module above 80 %
  - Verified: pytest --cov semforge: 2703 passed, 5 skipped, total coverage 89.40 %, `semforge/editor/search.py` 98 %; `flake8 semforge tests` clean; `openspec validate --all --strict` passes.
