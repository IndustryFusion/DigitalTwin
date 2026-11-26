# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/test_value_type.py`,
end-to-end tests ("e2e:") in `vscode/test/e2e/suite/`, run with `make test-e2e`.

## 1. SDK

- [ ] 1.1 Say the type of a value as JSON-LD reads it; verify "One spelling, four types", "A whole number with a point", "A very large plain number" and "A text that looks like one"
- [ ] 1.2 Change the type of one value in its file, in the forms of the contract, with its digits; verify "Each type" (by validating the case), "True or false", "A vocabulary term", "A long number", "An integer of 10^21", "Too many digits", and the contract's "A very large integer", "Another integer type", "An integer where the shape asks for a double", "A double where the shape asks for an integer" and "Edited afterwards"
- [ ] 1.3 As the shape says; verify "Back to a double", "A text of digits", "A term without a datatype", and of the integer types "An integer type" and "Out of the range of its type"
- [ ] 1.4 Refuse what cannot be, and keep the file; verify "A fraction as an integer", "A word as a number" and "A structure", "A text with a language", and another member than `value`
- [ ] 1.5 Add the language server request; verify a unit test of its answers, errors included

## 2. Extension

- [ ] 2.1 The type beside the value and in the row menu, the command and its choice; verify "Chosen on the page", "A type none of the choices is", "Not picked", "Offered in the menu", "A structure is not offered" and "An earlier observation" with unit tests of the extension, the click itself in headless Chromium, `test_extension_activates.py` and `test_extension_commands.py` (not in the palette), and that a file other cases include is asked about
- [ ] 2.2 End to end in VS Code against the real server: the type said, made another, back to what the shape says, and a refusal; verify with a new e2e test
- [ ] 2.3 Describe it in the extension's README; verify by reading it

## 3. Checks

- [ ] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
