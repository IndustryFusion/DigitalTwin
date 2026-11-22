# shacl2flink/literal-datatypes Specification

## Purpose
Defines which values of an NGSI-LD property satisfy an `sh:datatype` of
`xsd:double` or `xsd:integer`, and how `sh:hasValue` compares a value with
its constant, when shacl2flink validates a model, so that the checks give
the verdict a conformant SHACL engine gives on the JSON-LD reading of the
model where the platform can tell, state where they deliberately differ, and
the check on SQLite and the check on Flink agree.

## Requirements

### Requirement: Plain numbers are typed as JSON-LD types them
A plain JSON number SHALL be an `xsd:double` when it has a non-zero fractional part or an absolute value of at least 10^21, and an `xsd:integer` otherwise, however it is written. A plain `xsd:double` SHALL satisfy `sh:datatype xsd:double` and violate `sh:datatype xsd:integer`; a plain `xsd:integer` SHALL satisfy `sh:datatype xsd:integer` and violate `sh:datatype xsd:double`.

#### Scenario: Fraction on a double shape
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the plain value `80.5`
- **THEN** no datatype alert is raised for it

#### Scenario: Whole number on a double shape
- **WHEN** the property has the plain value `80`
- **THEN** a datatype alert is raised for it

#### Scenario: Whole number written with a decimal point on a double shape
- **WHEN** the property has the plain value `80.0`
- **THEN** a datatype alert is raised for it

#### Scenario: Zero on a double shape
- **WHEN** the property has the plain value `0.0`
- **THEN** a datatype alert is raised for it

#### Scenario: Very large number on a double shape
- **WHEN** the property has the plain value `1e21`
- **THEN** no datatype alert is raised for it

#### Scenario: Whole number written with a decimal point on an integer shape
- **WHEN** a property of a shape with `sh:datatype xsd:integer` has the plain value `80.0`
- **THEN** no datatype alert is raised for it

#### Scenario: Fraction on an integer shape
- **WHEN** the property has the plain value `80.5`
- **THEN** a datatype alert is raised for it

### Requirement: A declared type decides
A value with a declared `@type` of `xsd:double` SHALL satisfy `sh:datatype xsd:double` when its text is a number: an optional sign, then digits with an optional decimal point, or a decimal point and digits, then an optional exponent. A value declared `xsd:integer` SHALL violate `sh:datatype xsd:double`, and a value declared `xsd:double` SHALL violate `sh:datatype xsd:integer`.

#### Scenario: Declared double written as a whole number
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

#### Scenario: Declared double zero
- **WHEN** the property has the value `{"@value": 0.0, "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

#### Scenario: Declared double with a fraction
- **WHEN** the property has the value `{"@value": 80.5, "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

#### Scenario: Declared integer on a double shape
- **WHEN** the property has the value `{"@value": 80, "@type": "xsd:integer"}`
- **THEN** a datatype alert is raised for it

#### Scenario: Declared double on an integer shape
- **WHEN** a property of a shape with `sh:datatype xsd:integer` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** a datatype alert is raised for it

### Requirement: Strings are judged by their text
A JSON string without a declared type SHALL satisfy `sh:datatype xsd:double` when its text is a number with a decimal point or an exponent, and `sh:datatype xsd:integer` when its text is an optional sign followed by digits. Any other text SHALL violate both.

#### Scenario: Live value with a decimal point
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the string value `"80.0"`
- **THEN** no datatype alert is raised for it

#### Scenario: Digits only on a double shape
- **WHEN** the property has the string value `"80"`
- **THEN** a datatype alert is raised for it

#### Scenario: Zero as a string on a double shape
- **WHEN** the property has the string value `"0"`
- **THEN** a datatype alert is raised for it

#### Scenario: Digits only on an integer shape
- **WHEN** a property of a shape with `sh:datatype xsd:integer` has the string value `"80"`
- **THEN** no datatype alert is raised for it

#### Scenario: Text that is not a number
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the string value `"eighty"`
- **THEN** a datatype alert is raised for it

### Requirement: SQLite and Flink agree on datatypes
The checks generated for SQLite and for Flink SHALL raise the same datatype alerts and the same `sh:hasValue` alerts for every scenario of this specification.

#### Scenario: The same model on both
- **WHEN** a model with the values of the scenarios above is validated on SQLite and, after it was written to Scorpio, on Flink
- **THEN** both raise datatype alerts for exactly the same properties

#### Scenario: The same sh:hasValue verdicts on both
- **WHEN** a model with the values of the `sh:hasValue` scenarios is validated on SQLite and, after it was written to Scorpio, on Flink
- **THEN** both raise `sh:hasValue` alerts for exactly the same properties

### Requirement: The rule is documented
The shacl2flink documentation SHALL state how plain numbers, declared types and strings satisfy `xsd:double` and `xsd:integer`, that a whole-valued double has to be declared with `@type`, and that strings are judged by their text unlike in a conformant SHACL engine. It SHALL state that `sh:hasValue` compares a number constant by its value and a string constant by its text, unlike a conformant SHACL engine, which compares value and datatype.

#### Scenario: Reading the documentation of sh:datatype
- **WHEN** a modeller reads the entry for `sh:datatype` in the shacl2flink documentation
- **THEN** it says that a plain `80.0` is an integer, that `{"@value": 80, "@type": "xsd:double"}` is the way to write a whole-valued double, and that `"80.0"` as a string satisfies `xsd:double`

#### Scenario: Reading the documentation of sh:hasValue
- **WHEN** a modeller reads the entry for `sh:hasValue` in the shacl2flink documentation
- **THEN** it says that `80`, `80.0`, a declared `xsd:double` `80` and the string `"80.0"` all satisfy `sh:hasValue 80.0` and `sh:hasValue 80`, that this differs from a conformant SHACL engine, and that a string constant such as `"1.0"` is compared as text

### Requirement: sh:hasValue compares a number by its value
When the constant of `sh:hasValue` is a number, a value SHALL satisfy it when it is the same number, whatever numeric datatype the constant and the value have and whether the value declares a type at all. A plain number, a value declared with a numeric XSD datatype, and a string whose text is a number as defined for a declared `xsd:double` count as numbers. Any other value SHALL violate the constraint.

#### Scenario: Plain whole number
- **WHEN** a property of a shape with `sh:hasValue 80.0` has the plain value `80`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Plain whole number written with a decimal point
- **WHEN** a property of a shape with `sh:hasValue 80` has the plain value `80.0`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Declared double with a whole value
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Declared integer
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the value `{"@value": 80, "@type": "xsd:integer"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A different number
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the plain value `80.5` or the value `{"@value": 80.5, "@type": "xsd:double"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A declared integer against a fraction
- **WHEN** a property of a shape with `sh:hasValue 80.5` has the value `{"@value": 80, "@type": "xsd:integer"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A string holding the number
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the string value `"80.0"` or `"80"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Text that is not a number
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the string value `"eighty"`
- **THEN** a `sh:hasValue` alert is raised for it

### Requirement: sh:hasValue compares a string by its text
When the constant of `sh:hasValue` is a string, a string value SHALL satisfy it only when its text is the same text, even when both texts read as the same number.

#### Scenario: The same text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the string value `"1.0"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: The same number in another text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the string value `"1"`
- **THEN** a `sh:hasValue` alert is raised for it
