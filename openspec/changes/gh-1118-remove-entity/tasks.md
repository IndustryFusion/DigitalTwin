# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/test_remove_entity.py`,
end-to-end tests in `vscode/test/e2e/suite/05e-remove-entity.test.js` ("e2e:"),
both with the test's name. What an end-to-end run cannot do is said.

## 1. SDK

- [x] 1.1 Remove one document, whole or not at all; verify "From a row" (`test_it_goes_and_the_others_stay`, e2e: "from its row, and not when the question is dismissed"), "A link" (`test_a_linked_file_stays_a_link`; no e2e: the workspace has no links), "A write that fails" (`test_a_failed_write_leaves_the_file_as_it_was`; no e2e: a failing disk)
- [x] 1.2 Carry place and content digest on entity rows and cards and check them; verify "One of two" (`test_one_of_two_with_the_same_id`, e2e: "of two with the same id, the one the row stands for"), "Not said which" (`test_one_of_two_with_the_same_id`; no e2e: the editor always says which), "Changed since it was shown" (`test_a_file_changed_since_it_was_read`, e2e: "a file changed since the row was read is refused"), and `test_the_rows_and_cards_say_which_document_they_are`
- [x] 1.3 Say what it touches; verify "Something points at it" (`test_who_uses_the_file`, e2e: "from its row…"), "A file several cases use" (`test_who_uses_the_file`, `test_two_cases_of_one_file`, e2e: "says which cases use the file, and refuses unsaved edits"), "Asserted" (`test_the_asserts_are_said_and_stay`, e2e: "from its card…"), "In the main model" (`test_the_whole_main_model_may_go`, e2e: "from its row…")
- [x] 1.4 Find references in the graph; verify "A prefix and a whole IRI" (`test_what_points_at_it_however_it_is_spelled`), "Asserted by its IRI" (`test_an_assert_names_the_iri_of_an_id_with_a_prefix`), "Written again in another way" (`test_an_id_written_again_in_another_way_remains`, "Named, not pointed at" (`test_only_relationships_point_at_it`), `test_written_inside_another_is_no_definition_that_remains`, `test_without_a_context_a_second_definition_still_remains`, `test_the_file_is_read_once`, `test_the_published_context_is_the_package_s_own_and_what_is_written_keeps_it`), "No context" (`test_a_file_whose_context_is_not_to_be_had`); no e2e of their own: the same request and question as in 1.3, with other data
- [x] 1.5 Refuse what changed during the question; verify "Changed during the question" (`test_changed_since_the_question`, `test_an_assert_changed_during_the_question`, `test_a_graph_that_could_be_built_only_once_does_not_refuse`, "Changed while it is written" (`test_a_file_changed_while_it_is_written_is_left_as_it_was`; no e2e: the window is too short to hit), `test_it_is_asked_first` for the handed-back fingerprint; no e2e: the stubbed question is answered at once)
- [x] 1.6 Leave an empty list; verify "The last entity" (`test_the_last_one_leaves_an_empty_list`, `test_a_file_of_one_object`, `test_what_is_no_entity_does_not_count_as_one`, e2e: "from its card: the case is left empty, its asserts stay, and the page shows it")
- [x] 1.7 Refuse other files; verify "Inside a graph" (`test_entities_inside_a_graph_are_refused`), "Another file" (`test_only_files_of_the_package`, `test_a_file_on_another_drive_is_refused_as_another_file`), `test_a_file_that_is_not_json_is_named`; no e2e: the editor shows the refusal as in 1.2
- [x] 1.8 Add the language server request; verify `test_the_server_removes_it`

## 2. Extension

- [x] 2.1 Add the command and its menu entry; verify "From a row" (e2e: "from its row…"), "Not an entity" (`test_the_menu_is_on_entities_and_not_in_the_palette`, `test_a_row_that_is_no_entity_asks_nothing`, `test_extension_activates.py`, `test_extension_commands.py`; no e2e: VS Code's menus are not readable from a test)
- [x] 2.2 Add the card's button; verify "From a card" (`test_the_button_in_the_page_itself`, in headless Chromium, `test_a_card_removes_the_one_it_shows`, e2e: "from its card…"), "An older page" and "Another card at that place" (`test_a_card_removes_the_one_it_shows`, `test_a_page_marks_the_card_it_removes_from_as_busy`, `test_a_card_click_refused_shows_page_and_view_anew`, e2e: "a click from an older page removes nothing")
- [x] 2.3 Ask with what it touches; verify "Dismissed" (`test_it_is_asked_first`, e2e: "from its row…") and `test_the_question_says_what_it_touches`
- [x] 2.4 Refuse unsaved edits, and show anew after a refusal; verify "Unsaved edits" (`test_unsaved_edits_are_found_behind_links`, `test_unsaved_edits_are_found_by_the_name_the_editor_has`, `test_on_windows_a_name_is_the_same_in_any_case`, `test_edits_made_while_it_asked_are_not_lost`, e2e: "says which cases use the file, and refuses unsaved edits"), `test_after_a_refusal_the_view_is_shown_anew`, `test_a_request_that_fails_is_said`, `test_a_refusal_is_said`
- [x] 2.5 Describe it in the extension's README; verify by reading the rendered README

## 3. Checks

- [x] 3.1 Run the end-to-end suite file with `SEMFORGE_E2E_GREP="Remove entity" make test-e2e`; verify all pass
- [x] 3.2 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
