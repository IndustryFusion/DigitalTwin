# Tasks

## 1. Tests first

- [x] 1.1 Add unit tests for the OPC UA instance tool: a Double, a Float, a Decimal and a Duration variable with a whole value, a fractional value, an integer literal and no value; a Number variable with a whole, a fractional and no value; an integer, a boolean and a string variable; verify they fail before the change exactly for the double-like variables and the Number default
  - `semantic-model/opcua/tests/test_typed_literals.py`, 13 tests.
  - Float, Double, Decimal and Duration all map to one datatype list, `[xsd:double]`, so they are one case for the writer.
  - Before the change: 7 failed, exactly the declared doubles, the default, and Number's whole value and default.
- [x] 1.2 Add SemForge unit tests for a valid case, a range-break case and a count-break case generated for an `xsd:double` attribute, for an `xsd:integer` attribute and for an `sh:or` of both; for a value set on an example page (`80`, `80.5`, a typed value object); and for a new package's example; verify they fail before the change exactly for the `xsd:double` attribute
  - `semantic-model/SemForge-SDK/tests/unit/test_typed_literals.py`, 13 tests, including the OPC UA value-or-list shape (scenario "A choice between a value and a list") and an added observation.
  - Count breaks copy the valid value; they are covered by `test_dataset_instances`.
  - Before the change: 9 failed, the `xsd:double` cases, the double-or-integer case (it wrote `50.0`, not `50`) and the scaffold. The integer case, a typed value object and an unrelated attribute already passed.
- [x] 1.3 Add a SemForge test that exports a package holding a declared double and finds the same value in the export; verify it passes before and after the change
  - `test_an_export_keeps_the_declared_value`. It passes after the change. Before it, main's scaffold writes no declared value, so there is nothing to export and it fails for that reason.

## 2. OPC UA instance tool

- [x] 2.1 Write Double, Float, Decimal and Duration values and defaults as `{"@value": <float>, "@type": "http://www.w3.org/2001/XMLSchema#double"}`, and Number values plain with whole values as integers (D2, D3); verify task 1.1 passes and `make lint test` passes in `semantic-model/opcua`
  - `lib/jsonld.py`, `JsonLd.typed_number`, applied to scalar values and defaults; lists stay plain.
  - Unit suite: 299 passed. `test_kms_package.py` was not run locally: this environment lacks PyYAML for it.
  - `tests/owl2instances`: all 20 fixtures pass. Two expected files changed, both for the same Float Variable `MyVariable10`, whose nodeset value is the integer literal `1`: the instance now holds a declared `1.0` instead of a plain `1`, and the expected pyshacl report loses the violation that plain `1` caused (`test_variable_arrays`, `test_variable_arrays_vrs`; the latter's instances file is a symlink to the former).
  - Two unit tests that pinned the plain double changed in `test_libjsonld.py`.
  - `nodeset2owl` and `extractIffBindings` pass. `nodeset-dump`, `validation`, `owl2vt` and `check_consistency` could not run locally (`asyncua` and `owlready2` are not installed here); CI runs them.
  - Lint of the changed files passes.
- [x] 2.2 Build the OPC UA KMS packages as the *Build* workflow does; verify the packages build and `semforge verify --tests` passes on each
  - `make kms-packages` into a scratch folder: pumps, laser and simple build; `semforge verify --tests` passes on all three.
  - The pump model holds 22 declared doubles.

## 3. SemForge SDK

- [x] 3.1 Declare the values the test-case generator writes for an `xsd:double` attribute, valid and break values alike, and write integer-attribute values as integers (D1, D3); verify task 1.2 passes for generated cases
  - `expect/attributecase.py`: `declared_type` reads every branch of the one-value form (`_form_datatypes`), not only the first, so `sh:or ( double integer )` stays plain while OPC UA's value-or-list `sh:or` is a double.
  - The tree and case pages render a declared value as its value (`examples.py`, `casepage.py`), so the tree still reads `1.0 · Property · default`.
- [x] 3.2 Declare the value of an `xsd:double` attribute in the scaffold's example and in the example editor, keeping a value object the modeller typed (D4); verify task 1.2 passes for the scaffold and the editor
  - `package/scaffold.py`; `cooked/examples.py`: `set_value`, `add_observation`, `add_attribute`.
  - `ngsild/build.py` now accepts a value object as a Property value; it refused anything but `{"@id": …}`.
- [x] 3.3 Run the SemForge unit suite and `make kms-check`; verify both pass
  - Unit suite: 2264 passed, 2 skipped. `kms-check`: `kms/example` verifies with `--tests`. Lint of the changed files passes.
- [x] 3.4 Rebase PR #959 onto this change and run the SemForge unit suite there; verify the eight tests that failed on #959 pass (`test_add_test_case`, `test_attribute_tests`, `test_dataset_instances`, three of `test_opcua_pumps`, two of `test_timestamps`), and report the result on #959
  - Run on #959's SemForge with this change's files applied (the two touch different files): all eight pass, with this change's tests (21 passed).
  - It needed two more things:
    - `test_timestamps` writes its temperatures by hand, now declared;
    - the committed OPC UA corpus model (`tests/corpus/opcua-pumps/model-instance.jsonld`), written by the instance tool before this change, now has its 22 double values declared, exactly as the new tool writes them. A freshly generated pump package holds the same 22. Only those 22 value lines changed. Re-slicing the corpus from a new package was not done: the pipeline has changed far more than the values since the slice was made.
  - The full suite on the combination and the report on #959: see the Pull Request.

## 4. Pass-through

- [x] 4.1 Reuse the Scorpio round trip of #959 (task 3.1) for the scenario "Through Scorpio and the bridge"; verify the measurement is quoted in this Pull Request with the Scorpio image it was made with

## 5. Documentation

- [x] 5.1 State the rule in the README of the OPC UA tools and of the SemForge SDK, with the reason and an example; verify by reading both against the scenario "Reading the documentation"
