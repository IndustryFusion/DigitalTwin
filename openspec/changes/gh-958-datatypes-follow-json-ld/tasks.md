# Tasks

## 1. Tests first

- [x] 1.1 Add the table of test vectors (D3): every value of both delta specifications -- plain numbers, declared types, strings, `0.0`, `1e18`, `1e21` -- with its expected RDF type and text; verify it reproduces the JSON-LD 1.1 column of the design's table, row by row
  - `semantic-model/shacl2flink/tests/jsonld-number-vectors.json`, 21 rows. `1e18` instead of `1e20`: rdflib reads JSON integers beyond 64 bits as doubles (design, D2).
- [x] 1.2 Add a kms-constraints fixture with an `xsd:double` shape and an `xsd:integer` shape, and models with every value of the shacl2flink scenarios; verify that `tests/sql-tests/tests.sh` fails on it before the change
  - `kms-constraints/test24`, one entity per scenario plus `1.5e-7` and `"2.5E-3"`; the expected result is written from the specification.
  - Measured before the change, SQLite got these wrong: plain `80.0` and `0.0` on the double shape (no alert), plain `80.0` on the integer shape (alert), and the strings `"80.0"` on double and `"80"` on integer (alert; the store typed them `xsd:string`).
  - The declared double `80` and the string `"0"` were already right on SQLite; they were wrong on Flink (task 1.4).
- [x] 1.3 Add unit tests for shacl2flink's reading of plain numbers against the table of 1.1, in properties, sub-properties and lists, with and without `@type`; verify they fail before the change
  - `tests/test_jsonld_numbers.py`. Before the change the module does not exist and collection fails.
- [x] 1.4 Add unit tests for the generated `sh:datatype` check that run it on SQLite with rows as each side fills them (the design's table); verify they fail before the change
  - `tests/test_datatype_check.py`, 19 cases, each with a Flink row and a SQLite row.
  - Against the old check they fail for `0.0` and the string `"0"` (the exception for `0`), `1.5e-7` and `"2.5E-3"` (the old pattern had no decimal point together with an exponent), and the declared double `80` (the Flink row).

## 2. shacl2flink

- [x] 2.1 Accept any number as text when the type is `xsd:double` (D4), drop the exception for `0` from the pattern for a missing type (D6), leave `xsd:integer`, `xsd:boolean` and `xsd:string` unchanged; verify tasks 1.2 and 1.4 pass, and `make test` and `make lint` pass
  - The pattern for a missing type also accepts a decimal point together with an exponent (`1.5e-7`), which JavaScript writes for small doubles.
  - The declared branch compares the type through `IFNULL`: without it, `NULL = '…'` made the whole condition `NULL` and the string `"80"` was never reported (caught by test24).
  - `make lint` passes; `make test`: 321 passed, coverage 85.2 %.
- [x] 2.2 Read plain numbers as D2 says before the model is turned into RDF for the SQLite checks; verify tasks 1.3 and 1.2 pass
  - `lib/jsonld_numbers.py`, applied in `utils.load_graph` to every JSON-LD file.
  - `create_ngsild_models.py` treats a string's implicit `xsd:string` as no declared type, as the bridge does (design, context).
- [x] 2.3 Run all sql-tests; verify they pass, and list in the Pull Request every existing expected result that had to change
  - 127 model runs pass (main: 126, plus test24).
  - No expected result changed. Five values in `kms-constraints/test9` were rewritten to keep each fixture's intent: the all-valid `urn:filter:1` writes its `hasDouble` as a declared `{"@value": 1.0, "@type": xsd:double}` (model1, model2, model6), and the all-invalid `urn:filter:2` writes its `hasInteger` as `1.5` instead of `1.0`, which is now an integer (model2, model6).
  - `sh:in`, `sh:hasValue` and list fixtures needed no change.

## 3. Flink

- [x] 3.1 On the light Scorpio stack (Scorpio, Postgres, Kafka in Docker), upsert `{"@value": 80, "@type": "xsd:double"}`, `{"@value": 0.0, "@type": "xsd:double"}` and a plain `80.0`, read back the stored entities and run them through the debezium bridge's parser; verify the typed values come out with `valueType` `xsd:double` and the plain one without, and report the result in the Pull Request before 3.2
  - Measured with `ibn40/scorpio-all-in-one-runner:v0.10` (image `sha256:3885af89…`), `postgis/postgis:14-3.4` and `apache/kafka-native:3.9.0`.
  - Scorpio stores `@type` and the notation unchanged (`80.0` stays `80.0`). The bridge gives `valueType` `xsd:double` and the value `80` for both declared forms, and `0` for the declared zero. A plain `80.0` comes out as `80` without a type, the string `"80.0"` as `"80.0"`.
- [x] 3.2 Add the values of the shacl2flink scenarios to the e2e kms package (`tests/e2e-kms`) with the alerts they must and must not raise; verify `make test-flink-e2e` passes in the K8s tests workflow, which writes the model to Scorpio and reads the alerts from Flink
  - Added: `E2ENumberMachineShape` and the test "numbers are typed as JSON-LD types them, through scorpio and the bridge" (16 entities). The package compiles.
  - The K8s tests workflow passed on this Pull Request (run 43530726210, on top of #962): `ok 20 numbers are typed as JSON-LD types them, through scorpio and the bridge`; 189 e2e tests ok, none failed.

## 4. SemForge, pyshacl, documentation

- [x] 4.1 Read plain numbers as D2 says in SemForge's one function in front of rdflib; test it against the table of 1.1, read from shacl2flink's tests; verify the SemForge unit suite passes and the scenarios of `semforge-sdk/model-numbers` hold for an example package
  - `semforge/rdfio/numbers.py` and `for_rdflib`, used by all three loaders; `tests/unit/test_model_numbers.py` (23 tests) passes.
  - The suite: 2266 passed, 8 failed. All 8 pass on main and fail here for one reason: SemForge's generators write `xsd:double` values as plain whole floats (`"value": 60.0`), which are integers under the rule. Making them declare their doubles is #961, which lands first (task 5.1).
  - On top of #962 (#961's writers): 2287 passed, 3 skipped; the eight pass.
- [x] 4.2 Run the cross-check on a package whose examples hold the values of 1.1; verify it reports no difference for the plain and declared numbers
  - The cross-check compiles the package's model, not its examples, so the values went into the model of a copy of `kms/example`: a shape with an `xsd:double`, an `xsd:integer` and an `sh:or` of both, and one entity per row of the table, each giving all three the row's value. The unmodified copy agrees with pyshacl.
  - Rows 1-17, all plain and declared numbers: no difference; both sides raise the same violations, each as the table says.
  - Rows 18-21 differ, none of them numbers: the strings `"80.0"`, `"80"` and `"0"` are judged by their text on SQLite (D5, the known divergence also listed for test24), and for `true` on the `sh:or` attribute SQLite names a datatype violation where pyshacl names an `sh:or` one, with the same verdict. The cross-check does not yet list either as expected; follow-up.
- [x] 4.3 Load the models of the pyshacl comparison with shacl2flink's reading; verify `make test-pyshacl-compare` passes, reports no divergence on the new fixture's numbers, and the divergence list gains only string entries with their reason, if any
  - 90 models compared, 0 missed, 0 extra. Three string entries for test24 were added under the existing lexical-form reason.
- [x] 4.4 Describe in the `sh:datatype` entry of `docs/supported-features.md` how plain numbers, declared types and strings satisfy `xsd:double` and `xsd:integer`, and how to write a whole-valued double; verify by reading the rendered page against the scenario "Reading the documentation of sh:datatype"
  - New section *Datatypes of numbers*, linked from the `sh:datatype` row.

## 5. Order

- [x] 5.1 Before merging, confirm that #961's writers are merged and the kms and OPC UA instances in use have been written again with declared doubles; verify by naming the merged Pull Requests of #961 in this one
  - #961's writers are #962, merged on 2026-11-13 (`19b82ac4`), and its archive #963 (`d569b13d`); this change is rebased onto both.
  - OPC UA: #962 declares the doubles in the instance tool, the committed pump corpus and the generated KMS packages.
  - kms: the instances in `semantic-model/kms/example` hold no whole-valued plain number on an `xsd:double` attribute; the whole floats there (`hasWidth`, `hasHeight`, `hasLength`) are under shapes with ranges only, which accept integers.
