# contracts/typed-literals Delta

## ADDED Requirements

### Requirement: A modeller may choose another type for a value
A modeller SHALL be able to choose, in the SemForge SDK, the type of one value of an example on purpose, also one its attribute's shape does not allow, as a test of that shape needs. The SDK SHALL then write that type in the forms of this specification: a double or a decimal declared, an integer, a boolean and a text plain. A value whose type was not chosen SHALL be written as *The SemForge SDK declares its doubles* requires, and so SHALL a value that is edited after its type was chosen.

#### Scenario: An integer where the shape asks for a double
- **WHEN** a modeller chooses the type integer for the value 50.0 of an `xsd:double` attribute in an example
- **THEN** the example holds the plain number `50`

#### Scenario: A double where the shape asks for an integer
- **WHEN** a modeller chooses the type double for the value 50 of an `xsd:integer` attribute in an example
- **THEN** the example holds a declared `xsd:double` with the value 50

#### Scenario: Edited afterwards
- **WHEN** that value of the `xsd:double` attribute is edited to `51`
- **THEN** the example holds a declared `xsd:double` with the value 51

### Requirement: A chosen integer is written as JSON-LD reads it
A chosen integer of 10^21 and more, which JSON-LD would read as a double, SHALL be declared as `xsd:integer` with its digits as text, and a value of another XSD integer type (`xsd:int`, `xsd:long`, …) SHALL be declared with that type, since a plain number is an `xsd:integer`.

#### Scenario: A very large integer
- **WHEN** a modeller chooses the type integer for the value `1e21`
- **THEN** the example holds `{"@value": "1000000000000000000000", "@type": "xsd:integer"}`

#### Scenario: Another integer type
- **WHEN** a modeller chooses *as the shape says* for the value 50 of an attribute whose shape says `sh:datatype xsd:int`
- **THEN** the example holds `{"@value": 50, "@type": "xsd:int"}`
