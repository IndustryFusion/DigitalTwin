# Compile CONCAT and STR

Issue: #1111

## Why

SPARQL constraints build their own message with `BIND(CONCAT(…, STR(?value), …) AS ?text)` and `sh:message "{?text}"`. shacl2flink supports neither function, so such a constraint cannot be compiled, although SHACL tools run it.

## What Changes

- `CONCAT` and `STR` compile, nested in each other and in `IF`, for constraints and rules, on SQLite and on Flink.
- A text keeps every character it has.
- An unbound argument leaves the result unbound.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `shacl2flink/sparql-expressions`: adds the functions on texts. The capability is introduced by gh-1107-sparql-compilation, which has to be archived before this change.

## Impact

- `semantic-model/shacl2flink`: the compiler, the list of supported forms, tests.
- No contract between components changes. No query which compiles today is compiled differently.

## Out of Scope

- Other functions on texts (`STRLEN`, `SUBSTR`, `REPLACE`, `REGEX`, …), language tags.
