# Delta for OPC UA Live Data

## MODIFIED Requirements

### Requirement: Form of attributes in the broker
Attributes updated through the chain SHALL have the same form as in the generated instances: numbers and booleans as JSON values, enums as IRIs, structures as `JsonProperty`. Produced by: Core Services, updates bridge. Relied on by: REST consumers. What the broker accepts, stores and refuses is stated in `contracts/context-broker`.

#### Scenario: Values over REST
- **WHEN** updates pass the updates bridge and the attribute is read over REST
- **THEN** a number is a JSON number, a boolean is a JSON boolean, an enum is an IRI, and a structure is a `JsonProperty`

#### Scenario: Refused by the broker
- **WHEN** an update merges a `Property` onto a `JsonProperty`, or an IRI value in a batch merge
- **THEN** the broker refuses it as `contracts/context-broker` states (*Refusals the platform relies on*, *Refusals in a batch are reported per entity*, *Value objects are merged*), and the updates bridge doesn't send an IRI value that way
