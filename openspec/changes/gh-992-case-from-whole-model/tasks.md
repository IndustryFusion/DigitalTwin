# Tasks

## 1. SDK

- [ ] 1.1 Add the start `whole-model` to the test-case writer: every document of every main-model file in load order, written into the case; refused without a main model; verify unit tests in `tests/unit/test_add_test_case.py` for "A model of several files", "The case is a snapshot" and "A package without a main model"
- [ ] 1.2 Name the main model's files in the test-case options and report the start in a written case's result; verify a unit test that the options of the kms corpus name `model-instance.jsonld`
- [ ] 1.3 Declare and run the case as the other starts, and set its description from the run unless one is given; verify unit tests for "A good case from a conforming model", "A bad case from a conforming model", "A good case from a violating model" and "A description given"

## 2. Extension

- [ ] 2.1 Offer "The whole main model" in New test case…'s start list when the options name model files, with the file or the number of files, and ask only for the name after it; verify extension unit tests in `tests/unit/test_tree_clicks.py` for "A package with a main model" and the hidden start without one
- [ ] 2.2 Say "It still violates, as the main model does" for a good case from a violating model; verify an extension unit test on the message
- [ ] 2.3 Describe the start in the SemForge README; verify by reading the rendered README

## 3. End to end and checks

- [ ] 3.1 Add an end-to-end test (`vscode/test/e2e/suite/26-whole-model-case.test.js`) that starts a bad case from the whole main model in a new suite and checks the file, the declaration, the description, the case page and that the model is untouched; verify it passes with `SEMFORGE_E2E_GREP="whole main model" make test-e2e`
- [ ] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass
