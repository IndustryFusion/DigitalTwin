## MODIFIED Requirements

### Requirement: SemForge and shacl2flink agree on numbers
For every value of the scenarios of `shacl2flink/literal-datatypes` that is a plain number or has a declared type, the SemForge SDK SHALL report a datatype violation exactly when shacl2flink raises a datatype alert.

#### Scenario: Cross-check on numbers
- **WHEN** the cross-check with shacl2flink runs on a package whose model holds those values
- **THEN** it reports no difference between the two for them

## ADDED Requirements

### Requirement: The cross-check lists strings judged by their text as expected
When SemForge rejects a string without a declared type on `sh:datatype`, or on an `sh:or` whose branches each state only an `sh:datatype`, and shacl2flink reads its text as a datatype the constraint admits, the cross-check SHALL list the difference as *expected*, with the reason that strings are judged by their text. A decimal point or an exponent reads as `xsd:double`, ASCII digits as `xsd:integer`. Every other rejected string SHALL stay a difference.

#### Scenario: A string read as a double
- **WHEN** the cross-check runs on a package whose model sets an attribute of a shape with `sh:datatype xsd:double` to the string `"80.0"`
- **THEN** it lists that difference as expected, with the reason that strings are judged by their text

#### Scenario: A string read as an integer inside an sh:or
- **WHEN** the model sets an attribute of a shape with `sh:or ( [sh:datatype xsd:double] [sh:datatype xsd:integer] )` to the string `"80"` or `"0"`
- **THEN** the cross-check lists that difference as expected, with the reason that strings are judged by their text

#### Scenario: A string whose text the constraint does not admit
- **WHEN** shacl2flink accepts the string `"80.5"` on a shape with `sh:datatype xsd:integer` and SemForge rejects it
- **THEN** the cross-check reports the difference as extra, not as expected

#### Scenario: A declared string
- **WHEN** shacl2flink accepts the value `{"@value": "80.0", "@type": "xsd:string"}` on a shape with `sh:datatype xsd:double` and SemForge rejects it
- **THEN** the cross-check reports the difference as extra, not as expected

#### Scenario: A branch that constrains more than the datatype
- **WHEN** shacl2flink accepts the string `"500"` on a shape with `sh:or ( [sh:datatype xsd:integer; sh:maxInclusive 100] [sh:datatype xsd:boolean] )` and SemForge rejects it
- **THEN** the cross-check reports the difference as extra, not as expected

### Requirement: The cross-check counts a failing sh:or of datatypes once
shacl2flink may report a datatype violation where SemForge reports an `sh:or` violation, on the same entity and attribute, for an `sh:or` of `sh:datatype`s. The cross-check SHALL list such a pair as one expected difference, with the reason that the compiled SQL names its datatype check. An `sh:or` violation on a string that shacl2flink judges by its text SHALL NOT be paired with a datatype violation.

#### Scenario: A failing sh:or named twice
- **WHEN** the model sets an attribute of a shape with `sh:or ( [sh:datatype xsd:double] [sh:datatype xsd:integer] )` to `true`
- **THEN** the cross-check lists one expected difference for it, and reports nothing missed or extra for it

#### Scenario: Another value's datatype violation
- **WHEN** an attribute of a shape with `sh:or ( [sh:datatype xsd:double] [sh:datatype xsd:integer] )` has two instances, the string `"80"` and the integer `80`, SemForge rejects only the string, and shacl2flink reports a datatype violation for the attribute
- **THEN** the cross-check lists the string as expected by its text and reports the datatype violation as missed

### Requirement: The cross-check agrees when every difference is expected
Every difference that no requirement of the cross-check lists as expected SHALL be reported as missed or extra. When every difference is expected, the cross-check SHALL report that the compiled SQL agrees with SemForge.

#### Scenario: A difference on a number
- **WHEN** SemForge and shacl2flink disagree on a datatype for a plain number or a value with a declared type
- **THEN** the cross-check reports the difference as missed or extra, not as expected

#### Scenario: The probe of every number
- **WHEN** the cross-check runs on a package whose model has one entity per row of `shacl2flink/tests/jsonld-number-vectors.json`, each setting an `xsd:double`, an `xsd:integer` and an `sh:or` attribute to the row's value
- **THEN** it reports that the compiled SQL agrees with SemForge, and lists exactly the differences of the strings and of `true` on the `sh:or` attribute as expected

### Requirement: The cross-check states what it compiles and where the compiler is found
The SemForge SDK documentation SHALL state that the cross-check compiles the package's model, not its examples. When the cross-check cannot find shacl2flink, its message SHALL name the option that points it at a shacl2flink checkout.

#### Scenario: Package outside the repository
- **WHEN** the cross-check runs on a package that has no shacl2flink checkout beside it and no path is given
- **THEN** it reports that it did not run, and its message names the `--shacl2flink` option
