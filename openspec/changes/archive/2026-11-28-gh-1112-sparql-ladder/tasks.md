## 1. Compiler

- [x] 1.1 Compile queries into rows and render the ladder for SQLite and Flink; verified by `tests/test_sparql_ladder.py`
- [x] 1.2 Switch in `create_sql_checks_from_shacl.py` and the Makefile, default `classic`; verified by `test_the_default_is_classic`, `test_switch`, and a build of `kms/example` byte-identical to main
- [x] 1.3 Unsupported queries stop the build; verified by `test_what_cannot_be_compiled_fails_and_names_the_shape`
- [x] 1.4 Every query of `tests/test_sparql_semantics.py` is either refused by the ladder by name or answered as SPARQL does; verified by running those queries through the ladder
- [x] 1.5 `CONCAT` and `STR`, and patterns which start with `OPTIONAL`; verified by the same comparison and by shared vectors
- [x] 1.6 The text of an alert equals the one of `classic`; verified by a comparison with attribute, knowledge and computed values in one message
- [x] 1.7 Values keep their datatype and errors are those of SPARQL, as `classic` compiles them; verified by `tests/test_sparql_ladder_semantics.py` (every query of the semantics suite through both methods) and by shared vectors

## 2. Functions

- [x] 2.1 Java functions and their build in the gateway image; verified by the shared vectors (`FlinkSqlGateway/sparql-udf/build.sh`)
- [x] 2.2 Register them in the submit job; verified by a job submitted through the gateway's `job.py`

## 3. Parity

- [x] 3.1 Same alerts and constructed attributes on SQLite; verified by `tests/test_sparql_ladder_parity.py`
- [x] 3.2 End-to-end on the platform with `SPARQL_ENGINE=ladder` (`make test-flink-e2e SPARQL_ENGINE=ladder`), in a shard of its own (`flink-ladder`) of k8s-e2e, selected when a pull request changes the files of the ladder (its compiler modules, functions and their tests), and in every nightly run (k8s-tests); verified by the suites passing there. `test-shacl-flink-e2e` changes and deletes attributes and deletes entities while the job runs: it is the test of "Streamed changes" and "Deleted entity"; constraints, rules and aggregates are in `tests/e2e-kms`
- [x] 3.3 Join count check in the `flink-ladder` shard: the number of `Join` nodes of the running job's plan (Flink REST `/jobs/<id>/plan`) equals the number the compiler writes into the build output for the deployed KMS; verified by the check failing when a level is duplicated

## 4. Documentation

- [x] 4.1 README: the two methods, the switch, the limits; verified by review
- [x] 4.2 Coverage of the changed code above 80 %, stated in the Pull Request; verified by `pytest --cov` and the Java vectors
