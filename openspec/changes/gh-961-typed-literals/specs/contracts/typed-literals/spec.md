# Delta for Typed Literals

## Purpose

Defines how a writer of NGSI-LD JSON-LD states the numeric datatype of a
property value, and what the components that pass the document on must keep,
so that a value means the same to every reader: JSON-LD 1.1 types a plain
number by its value, and only a declared `@type` makes a whole number a
double.

## ADDED Requirements

### Requirement: A writer declares every non-integer numeric value
A writer that knows that an attribute's value is an `xsd:double`, `xsd:float` or `xsd:decimal` SHALL write every value of that attribute as a value object whose `@type` is that datatype, whatever the value, whole or not. A writer knows the datatype when the attribute's shape says `sh:datatype` with that datatype alone, or when its source type is one of them.

#### Scenario: Whole value of a double attribute
- **WHEN** a writer writes the value 80 for an attribute whose shape says `sh:datatype xsd:double`
- **THEN** the document holds `{"@value": 80, "@type": "xsd:double"}` or the same with `80.0`, and not a plain number

#### Scenario: Fractional value of a double attribute
- **WHEN** the writer writes the value 80.5 for that attribute
- **THEN** the document holds `{"@value": 80.5, "@type": "xsd:double"}`

#### Scenario: A float attribute
- **WHEN** a writer writes the value 2 for an attribute whose shape says `sh:datatype xsd:float`
- **THEN** the document holds a value object with `@value` 2 and `@type` `xsd:float`

### Requirement: The declared type resolves to the XSD IRI
The `@type` of a declared value SHALL expand to the full XSD IRI, such as `http://www.w3.org/2001/XMLSchema#double`, in the context of the document that holds it. A writer SHALL use the compact form `xsd:double` only when that context defines the `xsd` prefix, and the full IRI otherwise.

#### Scenario: Context with an xsd prefix
- **WHEN** a writer declares a double in a document whose context defines `xsd`
- **THEN** the document may say `"@type": "xsd:double"`, and expanding it gives the full XSD IRI

#### Scenario: Context without an xsd prefix
- **WHEN** a writer declares a double in a document whose only context is the NGSI-LD core context
- **THEN** the document says `"@type": "http://www.w3.org/2001/XMLSchema#double"`

### Requirement: Other values stay plain
A writer SHALL write integers, booleans and strings as plain JSON values, and an integer attribute's value without a fractional part (`80`, not `80.0`). The value of an attribute whose shape admits both doubles and integers, or whose source type is a number of either kind, SHALL be written plain: a whole value as an integer, a fractional one as it is.

#### Scenario: Integer attribute
- **WHEN** a writer writes the value 80 for an attribute whose shape says `sh:datatype xsd:integer`
- **THEN** the document holds the plain number `80`

#### Scenario: Double or integer
- **WHEN** a writer writes the values 0 and 3.5 for an attribute whose shape says `sh:or ( [ sh:datatype xsd:double ] [ sh:datatype xsd:integer ] )`
- **THEN** the document holds the plain numbers `0` and `3.5`

### Requirement: The OPC UA instance tool declares its doubles
The OPC UA instance tool SHALL write the value of a variable whose data type is Double, Float, Decimal or Duration, and the default it writes for such a variable, as a declared `xsd:double`. The value of a variable whose data type is Number SHALL be written plain.

#### Scenario: Double variable with a whole value
- **WHEN** an instance is generated for a Double variable whose value in the nodeset is 80
- **THEN** the instance holds `{"@value": 80.0, "@type": "xsd:double"}` or the same with `80`, as the context allows

#### Scenario: Default of a Double variable
- **WHEN** an instance is generated for a Double variable without a value
- **THEN** the instance holds a declared `xsd:double` with the value 0

#### Scenario: Number variable
- **WHEN** an instance is generated for a Number variable without a value
- **THEN** the instance holds the plain number `0`

### Requirement: The SemForge SDK declares its doubles
The SemForge SDK SHALL write every value it generates or edits for an attribute whose shape says `sh:datatype xsd:double` as a declared `xsd:double`: the values of generated valid test cases, the values of generated cases that break a range or a count, the example of a new package, and an example value a modeller sets.

#### Scenario: Generated valid case
- **WHEN** a valid test case is generated for an `xsd:double` attribute with `sh:minInclusive 0` and `sh:maxInclusive 160`
- **THEN** the case holds a declared `xsd:double` with the value 80, and validating it raises no violation

#### Scenario: Generated case that breaks a range
- **WHEN** a test case that breaks `sh:maxInclusive 160` is generated for that attribute
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

### Requirement: Documents passed on keep their declared types
A component that passes an NGSI-LD document on -- Scorpio, the debezium bridge, and the SemForge SDK when it copies, exports or rewrites a document -- SHALL keep a value's declared `@type`.

#### Scenario: Through Scorpio and the bridge
- **WHEN** an entity holding `{"@value": 80, "@type": "xsd:double"}` is written to Scorpio
- **THEN** the attribute the debezium bridge publishes carries the type `xsd:double`

#### Scenario: A SemForge export
- **WHEN** the SemForge SDK exports a package whose example holds a declared `xsd:double`
- **THEN** the exported example holds the same declared value

### Requirement: The rule is documented
The documentation of the OPC UA tools and of the SemForge SDK SHALL state that doubles are written as declared values, and why.

#### Scenario: Reading the documentation
- **WHEN** a developer reads the README of the OPC UA tools or of the SemForge SDK
- **THEN** it says that a double is written as `{"@value": …, "@type": "xsd:double"}` because JSON-LD makes a plain whole number an integer
