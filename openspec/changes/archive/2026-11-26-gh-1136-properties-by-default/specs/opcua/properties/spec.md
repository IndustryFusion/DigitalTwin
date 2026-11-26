## Purpose

Defines how the OPC UA tools translate OPC UA Properties (nodes reached through
`HasProperty`) into shapes, instances and bindings: that they are followed by
default, how to leave them out, and where a client finds the sub-attributes they
become.

## ADDED Requirements

### Requirement: Properties are followed by default
`owl2instances.py` without options SHALL follow OPC UA Properties. A Property of an object SHALL become an attribute of the object's entity: constrained in the shapes, filled in the instances and bound in the bindings like a variable of the object. A Property of a variable SHALL become a sub-attribute of the variable's attribute: constrained in the shapes under the variable's property and filled in the instances with the value the nodeset gives it.

#### Scenario: The unit of an analog variable
- **WHEN** `owl2instances.py` is run without options on the pump example
- **THEN** the shape of `pumps:DriveMeasurementsType` constrains `opcua:hasEngineeringUnits` under `pumps:hasMotorTemperature`, and the instance's `pumps:hasMotorTemperature` carries an `opcua:hasEngineeringUnits` whose value is the unit of the nodeset

#### Scenario: A Property of an object
- **WHEN** `owl2instances.py` is run without options on the pump example
- **THEN** the pump's identification entity has the attribute `devices:hasManufacturer`, the shapes constrain it, and the bindings bind it

#### Scenario: A nodeset without Properties
- **WHEN** `owl2instances.py` is run without options on a nodeset that has no `HasProperty` reference
- **THEN** its shapes and instances are the same as with `--no-properties`

### Requirement: Properties can be left out
With `--no-properties`, `owl2instances.py` SHALL NOT follow `HasProperty`: no Property SHALL become an attribute or a sub-attribute, and the output SHALL be what the tool wrote without options before Properties were followed by default.

#### Scenario: Opting out
- **WHEN** `owl2instances.py --no-properties` is run on a nodeset whose types have Properties
- **THEN** neither the shapes nor the instances contain an attribute made from a Property

### Requirement: The former opt-in is accepted and has no effect
`-p` and `--properties` SHALL still be accepted. Either SHALL leave the output unchanged, and SHALL NOT undo `--no-properties`. The tool's help SHALL say that the option has no effect and that Properties are followed by default.

#### Scenario: An existing script passes -p
- **WHEN** `owl2instances.py -p` is run on a nodeset with Properties
- **THEN** the output is the same as without `-p`

#### Scenario: Both options
- **WHEN** `owl2instances.py -p --no-properties` is run
- **THEN** Properties are left out

#### Scenario: Help
- **WHEN** `owl2instances.py --help` is run
- **THEN** it describes `--no-properties`, and says of `-p/--properties` that it has no effect

### Requirement: Shapes are the contract for sub-attributes
`entities.ttl` SHALL declare the attributes of entity types and SHALL NOT declare sub-attributes, also when Properties are followed. The documentation of the OPC UA tools SHALL say that the sub-attributes a variable may carry are declared only in the shapes, as nested property constraints of the variable's attribute, and SHALL describe the default, `--no-properties` and the no-op `-p`.

#### Scenario: A sub-attribute is not in the entities
- **WHEN** `owl2instances.py` is run without options on the pump example
- **THEN** `entities.ttl` does not mention `opcua:hasEngineeringUnits`, while `shacl.ttl` does

#### Scenario: A reader looks up sub-attributes
- **WHEN** a reader looks up OPC UA Properties in the documentation of the OPC UA tools
- **THEN** it explains what a Property of an object and of a variable become, that the shapes are where sub-attributes are declared, with an example, and how to leave Properties out
