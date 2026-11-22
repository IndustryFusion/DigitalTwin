# Delta for Typed Literals

## MODIFIED Requirements

### Requirement: Documents passed on keep their declared types
A component that passes an NGSI-LD document on -- the context broker, the debezium bridge, and the SemForge SDK when it copies, exports or rewrites a document -- SHALL keep a value's declared `@type`. When the broker keeps it, and when an update replaces it, is stated in `contracts/context-broker` (*Declared types in the broker*).

#### Scenario: Through Scorpio and the bridge
- **WHEN** an entity holding `{"@value": 80, "@type": "xsd:double"}` is written to Scorpio
- **THEN** the attribute the debezium bridge publishes carries the type `xsd:double`

#### Scenario: A SemForge export
- **WHEN** the SemForge SDK exports a package whose example holds a declared `xsd:double`
- **THEN** the exported example holds the same declared value

### Requirement: Readers of the NGSI-LD API accept declared values
A component that reads property values from the NGSI-LD API or its notifications SHALL read a value object whose `@value` is a number, or a number written as a string, as that number, whether the type is given as `@type` or, compacted by the core context, as `type`. It SHALL read a plain number as before. It SHALL NOT depend on which of these forms the broker returns for an attribute; the forms are stated in `contracts/context-broker` (*Declared types in the broker*).

#### Scenario: A declared value read back
- **WHEN** a reader gets `{"type": "http://www.w3.org/2001/XMLSchema#double", "@value": 42.5}` as an attribute's value
- **THEN** it reads the number 42.5

#### Scenario: A live string merged onto a declared value
- **WHEN** a reader gets `{"type": "http://www.w3.org/2001/XMLSchema#double", "@value": "42.5"}`
- **THEN** it reads the number 42.5

#### Scenario: A plain value
- **WHEN** a reader gets the plain number `42.5`
- **THEN** it reads the number 42.5

#### Scenario: The chain test reads values back
- **WHEN** the OPC UA chain test loads instances with declared doubles into the broker, sends live values through the updates bridge and reads them back
- **THEN** it reads each number as that number, whatever form the broker returns it in
