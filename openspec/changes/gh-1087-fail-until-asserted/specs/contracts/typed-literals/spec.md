# contracts/typed-literals Delta

## MODIFIED Requirements

### Requirement: The SemForge SDK declares its doubles
The SemForge SDK SHALL write every value it generates or edits for an attribute whose shape says `sh:datatype xsd:double` as a declared `xsd:double`: the values of generated test cases, the example of a new package, and an example value a modeller sets.

#### Scenario: Generated valid case
- **WHEN** a valid test case is generated for an `xsd:double` attribute with `sh:minInclusive 0` and `sh:maxInclusive 160`
- **THEN** the case holds a declared `xsd:double` with the value 80, and validating it raises no violation

#### Scenario: Generated case that breaks a range
- **WHEN** a modeller sets the value of that attribute in a generated test case to `161`, so that it breaks `sh:maxInclusive 160`
- **THEN** the case holds a declared `xsd:double` with the value 161, and validating it raises the `sh:maxInclusive` violation and no datatype violation

#### Scenario: A modeller sets a value
- **WHEN** a modeller sets the value of that attribute in an example to `80`
- **THEN** the example holds a declared `xsd:double` with the value 80

#### Scenario: A new package
- **WHEN** a new package is created
- **THEN** every value of an `xsd:double` attribute in its example is a declared `xsd:double`

#### Scenario: A choice between a value and a list
- **WHEN** a valid test case is generated for an attribute whose shape says `sh:or ( [ sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:double ] ] [ sh:property [ sh:path ngsi-ld:hasValueList ; … ] ] )`, as generated OPC UA packages do
- **THEN** its value is a declared `xsd:double`: the `sh:or` chooses between a value and a list, not between datatypes, and only an `sh:or` over datatypes makes a value plain
