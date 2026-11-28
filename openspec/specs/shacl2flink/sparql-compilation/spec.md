# shacl2flink/sparql-compilation Specification

## Purpose
Defines the methods shacl2flink has to compile the SPARQL constraints (`sh:sparql`) and rules (`sh:rule`) of a KMS, how one is chosen, what they report alike, and how the alpha method scales and fails.

## Requirements

### Requirement: Two methods, classic by default
shacl2flink SHALL offer the methods `classic` and `ladder` to compile SPARQL constraints and rules. It SHALL use `classic` unless `ladder` is asked for explicitly, for all SPARQL constraints and rules of a build alike, and refuse any other name. The documentation SHALL mark `ladder` as alpha.

#### Scenario: Not asked for
- **WHEN** a KMS is built without naming a method
- **THEN** every SPARQL constraint and rule is compiled into a statement of its own, and no generated file refers to the functions or rows of `ladder`

#### Scenario: Asked for
- **WHEN** a KMS is built with `SPARQL_ENGINE=ladder`
- **THEN** no SPARQL constraint or rule has a statement of its own, and everything generated from the SHACL property constraints is the same as with `classic`

#### Scenario: Unknown method
- **WHEN** a KMS is built with another name
- **THEN** the build stops with a message naming the methods

### Requirement: The methods report the same
For every query both methods support, `ladder` SHALL give the alerts (resource, event, severity, text) and the constructed attributes (identifier, entity, name, kind, value) which `classic` gives on the same data, including an `ok` alert for every instance of the target class without a violation, whether it is deleted or not.

#### Scenario: The test models
- **WHEN** the models of the SQL tests with SPARQL constraints or rules are validated with both methods
- **THEN** alerts and constructed attributes are equal for every model

#### Scenario: Streamed changes
- **WHEN** attributes are changed and deleted, and entities deleted, while the validation runs on Flink
- **THEN** after the last change both methods have written the same current alerts and attributes

#### Scenario: Optional patterns first
- **GIVEN** a constraint which starts with two `OPTIONAL` patterns, a minimum and a maximum, and compares a value with them
- **WHEN** an entity has the value and only one of the two, and the value violates it
- **THEN** both methods report the violation

#### Scenario: Text of an alert
- **GIVEN** a constraint whose message contains a value of an attribute, a value of the knowledge and the result of `CONCAT`
- **WHEN** it is violated
- **THEN** the text of the alert is the same with both methods, character by character

#### Scenario: Deleted entity
- **GIVEN** an alert for an entity
- **WHEN** the entity is deleted
- **THEN** the alert turns to `ok`

### Requirement: The ladder job does not grow with the queries
With `ladder`, the number of joins and statements of the validation job SHALL depend on the query needing the most levels and on which kinds of results the KMS has, and SHALL NOT depend on the number of queries.

#### Scenario: More queries
- **WHEN** queries which need no more levels than the existing ones, over the same attributes and knowledge, are added to a KMS
- **THEN** the generated SQL is the same, and only the delivered rows are more

### Requirement: The ladder fails loud
A query `ladder` does not support SHALL stop the build with a message naming the shape, what is not supported, and that `classic` can be used instead. It SHALL NOT be skipped or compiled with the other method.

#### Scenario: Unsupported query
- **WHEN** a KMS with a `UNION` in a SPARQL constraint is built with `SPARQL_ENGINE=ladder`
- **THEN** the build exits with a non-zero status, and the message names the shape and `UNION`

### Requirement: Values in the ladder are those of classic
With `ladder`, a value SHALL be compared, computed and written as `classic` compiles it (`shacl2flink/sparql-expressions`, `shacl2flink/literal-datatypes`). A literal keeps its datatype: two numbers compare by value, two texts by their characters, and a text and a number are never equal and not ordered. An IRI and a literal SHALL NOT be equal.

#### Scenario: Numbers
- **WHEN** a `FILTER` compares the values `9` and `10` without a cast
- **THEN** `9` is less than `10`

#### Scenario: A text and a number
- **GIVEN** an entity whose limit is the number `10`
- **WHEN** a `FILTER` compares `STR(?limit)` with the number `10` by `=`, by `!=` and by `<`
- **THEN** `=` does not hold, `!=` holds, and `<` is an error, so its `FILTER` does not hold, with both methods

#### Scenario: A computed number
- **WHEN** a query binds `STR(xsd:float(?limit))` for a limit of `10`
- **THEN** both methods give the same text for it

### Requirement: Errors in the ladder are those of SPARQL
With `ladder`, an error in a condition SHALL make `IF` and what is built from it unbound, and `&&` and `||` SHALL decide as SPARQL does when one operand is an error.

#### Scenario: An error in a condition
- **GIVEN** a variable bound in an `OPTIONAL` only, without a value for an entity
- **WHEN** it is compared inside the condition of an `IF`
- **THEN** the `IF` is unbound for that entity, with both methods
