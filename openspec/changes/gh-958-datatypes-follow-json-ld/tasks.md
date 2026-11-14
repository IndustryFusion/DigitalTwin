# Tasks

## 1. Tests first

- [ ] 1.1 Add the table of test vectors (D3): every value of both delta specifications -- plain numbers, declared types, strings, `0.0`, `1e20`, `1e21` -- with its expected RDF type and text; verify it reproduces the JSON-LD 1.1 column of the design's table, row by row
- [ ] 1.2 Add a kms-constraints fixture with an `xsd:double` shape and an `xsd:integer` shape, and models with every value of the shacl2flink scenarios; verify that `tests/sql-tests/tests.sh` fails on it before the change exactly for the plain `80.0` and `0.0` on the double shape, the plain `80.0` on the integer shape, the declared double `80` and the string `"0"`
- [ ] 1.3 Add unit tests for shacl2flink's reading of plain numbers against the table of 1.1, in properties, sub-properties and lists, with and without `@type`; verify they fail before the change
- [ ] 1.4 Add unit tests for the generated `sh:datatype` check that run it on SQLite with rows as each side fills them (the design's table); verify they fail before the change exactly for the declared double `80` and the texts `0` without a type

## 2. shacl2flink

- [ ] 2.1 Accept any number as text when the type is `xsd:double` (D4), drop the exception for `0` from the pattern for a missing type (D6), leave `xsd:integer`, `xsd:boolean` and `xsd:string` unchanged; verify tasks 1.2 and 1.4 pass for the declared values and strings, and `make test` and `make lint` pass
- [ ] 2.2 Read plain numbers as D2 says before the model is turned into RDF for the SQLite checks; verify tasks 1.3 and 1.2 pass
- [ ] 2.3 Run all sql-tests; verify they pass, and list in the Pull Request every existing expected result that had to change -- datatype, `sh:in`, `sh:hasValue`, lists -- each with the reason from the design's *Effects on other checks*

## 3. Flink

- [ ] 3.1 On the light Scorpio stack (Scorpio, Postgres, Kafka in Docker), upsert `{"@value": 80, "@type": "xsd:double"}`, `{"@value": 0.0, "@type": "xsd:double"}` and a plain `80.0`, read back the stored entities and run them through the debezium bridge's parser; verify the typed values come out with `valueType` `xsd:double` and the plain one without, and report the result in the Pull Request before 3.2
- [ ] 3.2 Add the values of the shacl2flink scenarios to the e2e kms package (`tests/e2e-kms`) with the alerts they must and must not raise; verify `make test-flink-e2e` passes in the K8s tests workflow, which writes the model to Scorpio and reads the alerts from Flink

## 4. SemForge, pyshacl, documentation

- [ ] 4.1 Read plain numbers as D2 says in SemForge's one function in front of rdflib; test it against the table of 1.1, read from shacl2flink's tests; verify the SemForge unit suite passes and the scenarios of `semforge-sdk/model-numbers` hold for an example package
- [ ] 4.2 Run the cross-check on a package whose examples hold the values of 1.1; verify it reports no difference for the plain and declared numbers
- [ ] 4.3 Load the models of the pyshacl comparison with shacl2flink's reading; verify `make test-pyshacl-compare` passes, reports no divergence on the new fixture's numbers, and the divergence list gains only string entries with their reason, if any
- [ ] 4.4 Describe in the `sh:datatype` entry of `docs/supported-features.md` how plain numbers, declared types and strings satisfy `xsd:double` and `xsd:integer`, and how to write a whole-valued double; verify by reading the rendered page against the scenario "Reading the documentation of sh:datatype"

## 5. Order

- [ ] 5.1 Before merging, confirm that #961's writers are merged and the kms and OPC UA instances in use have been written again with declared doubles; verify by naming the merged Pull Requests of #961 in this one
