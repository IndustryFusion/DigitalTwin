## 1. Compiler

- [x] 1.1 Compile `CONCAT` and `STR`, nested and in `IF`; verified by the comparison with SPARQL in `tests/test_sparql_semantics.py`, with the result projected, for every scenario
- [x] 1.2 Delimiters, quotes and braces inside texts survive in both dialects; verified by unit tests of the generated SQL for Flink and by the comparison on SQLite
- [x] 1.3 An existing package builds to the same SQL as before; verified by a byte comparison of the `kms/example` build

## 2. Flink

- [x] 2.1 A constraint of `tests/e2e-kms` whose message is a `CONCAT` with `STR`, `IF` and an `OPTIONAL` bound; verified by `test-shacl-flink-scorpio-e2e.bats` reading the alert's text, which fails without the change because the package does not compile

## 3. Documentation and coverage

- [x] 3.1 `docs/supported-features.md` lists both functions and how numbers are written; verified by review
- [x] 3.2 Coverage of the changed code above 80 %, stated in the Pull Request; verified by `pytest --cov`
