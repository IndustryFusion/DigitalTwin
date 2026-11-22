# Proposal

Issue: #966

## Why

`semforge validate <package> --cross-check sqlite` compares pyshacl's
verdict on a package's model with that of shacl2flink's SQLite build.
Differences the compiler is known to make on purpose, such as a unit or the
inlining of `sh:node`, are listed as *expected* with their reason. Every
other difference is reported as missed or extra, which reads as a possible
compiler bug.

Task 4.2 of #958 ran the cross-check on a package holding every value of
`shacl2flink/tests/jsonld-number-vectors.json`. No number differed, but 8
differences (1 missed, 7 extra) were reported that are known and intended,
and none of them was listed as expected:

- **Strings judged by their text** (#958, design D5): `"80.0"` passes
  `xsd:double` on SQLite and fails in pyshacl; `"80"` and `"0"` pass
  `xsd:integer` on SQLite and fail in pyshacl, also inside an `sh:or` of both.
  shacl2flink's own pyshacl comparison
  (`tests/pyshacl-compare/expected-divergences.txt`) already lists them as
  deliberate.
- **The name of a failing `sh:or`:** `true` on an attribute with
  `sh:or ( [sh:datatype xsd:double] [sh:datatype xsd:integer] )` is rejected
  by both. SQLite reports `DatatypeConstraintComponent` and pyshacl
  `OrConstraintComponent`, so the same verdict is counted as one missed and
  one extra difference.

A reader cannot tell these from real compiler bugs. The run also showed that
the README does not say that the model is cross-checked rather than the
examples, and that the error for a package outside the repository does not
mention `--shacl2flink`.

## What Changes

- The cross-check lists a string that the compiled SQL judges by its text
  as expected, with its reason. This applies when pyshacl rejects a string
  without a type on `sh:datatype` or on an `sh:or` of datatypes, and the
  datatype that the compiled SQL reads its text as is one the constraint
  admits.
- The cross-check lists a datatype alert of the compiled SQL and pyshacl's
  `sh:or` violation on the same entity and attribute as **one** expected
  difference, when the `sh:or` is one of datatypes.
- Every other difference stays missed or extra. This includes differences
  on numbers, on strings whose text the constraint does not admit, and on
  any other constraint type.
- The command reports that the compiled SQL agrees with pyshacl when every
  difference is expected.
- The README says that the cross-check compiles the package's model
  (`model-instance.jsonld`), not its examples, and how to point the check at
  shacl2flink. The error for a missing shacl2flink names `--shacl2flink`.
- CI installs the cross-check's dependencies for the SDK tests, so that the
  test on the probe package runs there.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `semforge-sdk/model-numbers`: the cross-check requirement names the model
  instead of the examples, and the cross-check lists the strings judged by
  their text and the naming of `sh:or` as expected.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the cross-check's
  categorisation (`semforge/target/crosscheck.py`), the value and admitted
  datatypes that a validation result records for it, the output of
  `semforge validate --cross-check sqlite`, the README and the tests.
  Validation verdicts, expectations, coverage and residue digests are
  unchanged.
- CI (`.github/workflows/build.yaml`): the SemForge SDK job installs sqlite3
  with its PCRE extension and `requirements-crosscheck.txt`.
- shacl2flink: unchanged. A test of the SDK reads the text patterns of its
  `sh:datatype` check, so the SDK's copy cannot drift from it.

## Out of Scope

- How `sh:hasValue` compares string constants (#1044) and its divergences;
  this change concerns `sh:datatype` verdicts and the naming of `sh:or`.
- Changing what shacl2flink or pyshacl decide; only how the cross-check
  categorises a difference changes.
- Cross-checking the examples or test cases of a package.
- Other `sh:or` naming differences of shacl2flink's comparison, such as an
  `sh:node` inside an `sh:or`. `sh:node` is already expected as a whole.
