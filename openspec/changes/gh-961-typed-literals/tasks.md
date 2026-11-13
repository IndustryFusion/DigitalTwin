# Tasks

## 1. Tests first

- [ ] 1.1 Add unit tests for the OPC UA instance tool: a Double, a Float, a Decimal and a Duration variable with a whole value, a fractional value, an integer literal and no value; a Number variable with a whole, a fractional and no value; an integer, a boolean and a string variable; verify they fail before the change exactly for the double-like variables and the Number default
- [ ] 1.2 Add SemForge unit tests for a valid case, a range-break case and a count-break case generated for an `xsd:double` attribute, for an `xsd:integer` attribute and for an `sh:or` of both; for a value set on an example page (`80`, `80.5`, a typed value object); and for a new package's example; verify they fail before the change exactly for the `xsd:double` attribute
- [ ] 1.3 Add a SemForge test that exports a package holding a declared double and finds the same value in the export; verify it passes before and after the change

## 2. OPC UA instance tool

- [ ] 2.1 Write Double, Float, Decimal and Duration values and defaults as `{"@value": <float>, "@type": "http://www.w3.org/2001/XMLSchema#double"}`, and Number values plain with whole values as integers (D2, D3); verify task 1.1 passes and `make lint test` passes in `semantic-model/opcua`
- [ ] 2.2 Build the OPC UA KMS packages as the *Build* workflow does; verify the packages build and `semforge verify --tests` passes on each

## 3. SemForge SDK

- [ ] 3.1 Declare the values the test-case generator writes for an `xsd:double` attribute, valid and break values alike, and write integer-attribute values as integers (D1, D3); verify task 1.2 passes for generated cases
- [ ] 3.2 Declare the value of an `xsd:double` attribute in the scaffold's example and in the example editor, keeping a value object the modeller typed (D4); verify task 1.2 passes for the scaffold and the editor
- [ ] 3.3 Run the SemForge unit suite and `make kms-check`; verify both pass
- [ ] 3.4 Rebase PR #959 onto this change and run the SemForge unit suite there; verify the eight tests that failed on #959 pass (`test_add_test_case`, `test_attribute_tests`, `test_dataset_instances`, three of `test_opcua_pumps`, two of `test_timestamps`), and report the result on #959

## 4. Pass-through

- [ ] 4.1 Reuse the Scorpio round trip of #959 (task 3.1) for the scenario "Through Scorpio and the bridge"; verify the measurement is quoted in this Pull Request with the Scorpio image it was made with

## 5. Documentation

- [ ] 5.1 State the rule in the README of the OPC UA tools and of the SemForge SDK, with the reason and an example; verify by reading both against the scenario "Reading the documentation"
