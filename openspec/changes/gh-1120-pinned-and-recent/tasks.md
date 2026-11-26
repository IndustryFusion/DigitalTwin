# Tasks

## 1. SDK

- [x] 1.1 Answer whether what each pin names is in the package, for every kind, in the order asked, and that the package is gone; verify unit tests in `tests/unit/test_pins.py` for "A package that is gone" and each kind there and gone
  - Verified: `test_a_pin_is_there_or_gone` (every kind there and gone), `test_an_entity_of_a_deleted_case_is_gone_and_severity_is_there` and `test_the_server_answers_in_order_and_says_when_the_package_is_gone` pass.

## 2. Extension

- [x] 2.1 Keep pins and recent places in the workspace state and list them, with "Nothing yet", the taking out and the pinning from the list; verify unit tests and the end-to-end test for "Pinned before recent", "Opening a pinned entity", "A recent place pinned from the list" and "No answer"
  - Verified: `test_nothing_pinned_says_how` and `test_the_list_without_a_server_and_a_recent_place_pinned_from_it` pass (no server: nothing gone; the pin button moves a recent entry up, with no empty "recent" left); the end-to-end test lists the pinned before the recent and opens the entity in its case.
- [x] 2.2 Pin from the star of a page, from rows, and from the ⋯ of an attribute and a query, and contribute the entry for an entity's id; verify unit tests on the contributions and the menus, and for "A row", "An id on a test case's page" and "A row that is no such thing"
  - Verified: `test_the_star_and_the_key_are_there` (star, key, rows of all four views, the entry for an id on a page), `test_a_row_is_pinned_and_nothing_else_is`, `test_a_rule_s_menu_opens_it_where_it_is_edited` and the `ofNode` check in `test_the_list_without_a_server_and_a_recent_place_pinned_from_it` and `test_queries_of_one_shape_paths_as_iris_and_model_files` (two queries of one shape, a path written as an IRI, a model file's row, a page that did not render) pass; the end-to-end test pins, unpins and pins the page in front.
- [x] 2.3 Let renames of shapes, cases and suites take pins along; verify tests for "A renamed test case", "An entity in a renamed suite" and a renamed shape
  - Verified: `test_a_rename_takes_the_pins_along` (shape, query keeping its text, case, entities of a renamed case and suite, another package untouched) and `test_a_renamed_shape_tests_exactly_as_before` (the moved suite's folders) pass; the end-to-end test renames a pinned case.
- [x] 2.4 Say what is gone, and search for it or take it out; verify the end-to-end test for "A deleted case"
  - Verified: the end-to-end test deletes a pinned case, finds it listed as not found and takes it out.
- [x] 2.5 Describe it in `vscode/README.md`; verify by reading it
  - `vscode/README.md`, "Pinned and recent": read in the diff.

## 3. End to end and checks

- [x] 3.1 Add an end-to-end test `vscode/test/e2e/suite/30-pins.test.js` that pins the page in front and an entity, checks the star, opens from the list, pins through a rename, and takes out what was deleted, and that no file of the package changes by pinning; verify `make test-e2e` passes it
  - Verified: `SEMFORGE_E2E_GREP="pinned and recent" make test-e2e` with VS Code 1.148.0: 2 passing, including that no file of the package changes. `Build` does not run this suite.
- [x] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass, with the coverage of the new code above 80 %
  - Verified: pytest --cov semforge: 2714 passed, 5 skipped, total coverage 89.42 %, `semforge/editor/search.py` 98 %, `semforge/cooked/rename.py` 97 %; `flake8 semforge tests` clean; `openspec validate --all --strict` passes.
