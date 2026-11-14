# Delta for SemForge SDK Model Numbers

## Purpose

Defines how the SemForge SDK reads the numbers of a model, an example or a
test case when it validates them offline, so that its verdicts on
`sh:datatype` match those of shacl2flink and of a conformant SHACL engine on
the JSON-LD reading of the model.

## ADDED Requirements

### Requirement: SemForge reads plain numbers as JSON-LD types them
When the SemForge SDK validates a model, an example or a test case, a plain JSON number SHALL be an `xsd:double` when it has a non-zero fractional part or an absolute value of at least 10^21, and an `xsd:integer` otherwise. A value with a declared `@type` SHALL keep it.

#### Scenario: Whole-valued double written as a plain number
- **WHEN** an example sets an attribute of a shape with `sh:datatype xsd:double` to the plain value `80.0` and the package is validated
- **THEN** SemForge reports a datatype violation for it

#### Scenario: Whole-valued double declared
- **WHEN** the example sets it to `{"@value": 80, "@type": "xsd:double"}`
- **THEN** SemForge reports no datatype violation for it

#### Scenario: Very large number
- **WHEN** the example sets it to the plain value `1e21`
- **THEN** SemForge reports no datatype violation for it

### Requirement: SemForge and shacl2flink agree on numbers
For every value of the scenarios of `shacl2flink/literal-datatypes` that is a plain number or has a declared type, the SemForge SDK SHALL report a datatype violation exactly when shacl2flink raises a datatype alert.

#### Scenario: Cross-check on numbers
- **WHEN** the cross-check with shacl2flink runs on a package whose examples hold those values
- **THEN** it reports no difference between the two for them
