# Tasks

## 1. SDK

- [ ] 1.1 Fail an invalid example without asserts in the example runner; verify unit tests for "A violation nobody asserted", "A violation as asserted" and "A valid example", and that every example of `semantic-model/kms` still meets its expectations (`make kms-check`)
- [ ] 1.2 Reduce New test… to the purposes `valid` and `invalid` and remove the per-constraint code; verify unit tests for "An attribute with a list", "Written and failing", "Broken but without a reason" and "Finished"
- [ ] 1.3 Take a valid value from the `sh:in` list, as the term it is; verify unit tests for "Lists of each kind"
- [ ] 1.4 Offer the items of `sh:in` in the value picker; verify a unit test for "Picked from the list" over lists of texts, numbers, doubles and booleans
- [ ] 1.5 Answer what a case can assert, and which cases are about an attribute, from the validation results; verify unit tests for "A reason named before it fires", "Already asserted" and "A failing test in the list"
- [ ] 1.6 Keep every generated and edited value of an `xsd:double` attribute declared; verify unit tests for "Generated valid case" and "Generated case that breaks a range"

## 2. Extension

- [ ] 2.1 Ask the two kinds in New test…; verify an extension unit test
- [ ] 2.2 Case page: the missing reason, adding an assert, removing any assert, and the Clone, Rename and Delete buttons; verify extension unit tests for "No reason yet" and "The last assert removed"
- [ ] 2.3 Attribute editor: the list of tests, opening and deleting, following a validation run; type and shape page: Delete on each case; verify extension unit tests for "Deleted from the attribute editor" and "Deleted from the type page"
- [ ] 2.4 Describe it in the SemForge README; verify by reading it

## 3. End to end and checks

- [ ] 3.1 Add an end-to-end test in VS Code that writes a failing test, breaks its data, asserts what fires, removes the assert and deletes the case from the attribute editor; verify it passes
- [ ] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass and that more than 80 % of the changed code is covered
