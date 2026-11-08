# contracts/opcua-live-data Specification

## Purpose
Defines the rules between the components on the path from an OPC UA server to the context broker, who produces and relies on each rule, and how the chain is verified, so that a change to one component can find what depends on it.

## Requirements

### Requirement: Entity IDs are usable as device IDs
Entity IDs produced by the model tools SHALL NOT contain a `/`. Produced by: model tools. Relied on by: device agent, MQTT topics, MQTT access control. A device whose ID contains a `/` is rejected by the access control, while the agent still reports that its data was sent.

#### Scenario: IDs of the model
- **WHEN** entities are created from a nodeset with default options
- **THEN** no entity ID contains a `/`

#### Scenario: Topic with a slash in the device ID
- **WHEN** the MQTT access control is asked about a topic whose device ID contains a `/`
- **THEN** it denies access

### Requirement: Bindings address the server's namespace
The namespace URI in a binding's connector parameter SHALL be the one the OPC UA server uses for that node. Produced by: model tools. Relied on by: connector, which resolves nodes by this URI and reads no value otherwise.

#### Scenario: Node of the machine's namespace
- **WHEN** the connector reads a binding of the example pump from a server with that nodeset
- **THEN** it finds the node, whichever namespace index the server assigned to the namespace

### Requirement: The server URI identifies instances
A server URI SHALL be required for a machine's instances to be exported, and SHALL be part of their entity IDs. Produced by: model tools. Relied on by: everything using entity IDs.

#### Scenario: Translation without a server URI
- **WHEN** a nodeset with instances is translated without a server URI
- **THEN** creating entities from it fails with a message that no instance was found

#### Scenario: Two servers with the same NodeIds
- **WHEN** the same nodeset is translated for two different server URIs
- **THEN** the entity IDs of the two results differ

### Requirement: Bindings vocabulary
Bindings SHALL use one vocabulary, which the generated bindings, the dataservice, the test servers and the binding validation all agree on. Produced by: model tools. Relied on by: dataservice, test servers, binding validation.

#### Scenario: Generated bindings
- **WHEN** the pump example's bindings are generated
- **THEN** they conform to the binding validation, and the dataservice finds all 46 of them

### Requirement: Enum values are looked up in the knowledge
The numeric value of an enumeration SHALL be translated to the IRI of its enum value, using the knowledge the model tools generate. A number which isn't part of the enumeration SHALL deliver no value. Produced by: model tools. Relied on by: dataservice, consumers of the attribute.

#### Scenario: Known number
- **WHEN** a pump class node has the value `1`
- **THEN** the attribute in the broker holds the IRI of `PositiveDisplacementPump`, with no leftover number

#### Scenario: Unknown number
- **WHEN** an enum node has a number which isn't part of its enumeration
- **THEN** the dataservice sends no message for this attribute

### Requirement: Attribute type labels
The dataservice SHALL label its messages only with `Property`, `IriProperty`, `JsonProperty` or `Relationship`. The device agent and the MQTT bridge SHALL handle each of them. Known gap: `PropertyIri` is valid for the agent's schema, but the bridge silently drops it.

#### Scenario: Every label is handled
- **WHEN** the dataservice sends a message with one of the labels
- **THEN** the agent's schema accepts the label and the bridge maps it to an attribute

#### Scenario: A label the bridge doesn't map
- **WHEN** a change makes the dataservice send a label the bridge doesn't map
- **THEN** the chain verification fails

### Requirement: Value forms in messages
The dataservice SHALL send values in their lexical form: `true` and `false` for booleans, ISO 8601 for timestamps, JSON for structures. Messages SHALL be valid JSON whatever the value contains. Produced by: dataservice. Relied on by: MQTT bridge, Core Services, broker.

#### Scenario: Boolean
- **WHEN** a boolean node is `true`
- **THEN** the message contains the value `true`, in lowercase

#### Scenario: Timestamp
- **WHEN** a DateTime node has a value
- **THEN** the message contains it in ISO 8601 form

#### Scenario: Value with quotes
- **WHEN** a string node contains a double quote
- **THEN** the message is valid JSON and the value is unchanged

#### Scenario: Structure
- **WHEN** a node holds a structure such as an OptionSet
- **THEN** the message has the label `JsonProperty`, and its value is JSON with ByteStrings in base64

### Requirement: Only values are delivered
A failed read or a node without a value SHALL deliver nothing, so that the broker keeps the last known value. After a lost connection, the connector SHALL reconnect by itself. Produced by: connector. Relied on by: everything downstream.

#### Scenario: Unset node
- **WHEN** a bound node has no value
- **THEN** the connector sends nothing for it, and no message contains the string `None`

#### Scenario: Outage
- **WHEN** the OPC UA server is gone
- **THEN** the connector sends nothing and keeps running

#### Scenario: Recovery
- **WHEN** the server is back and a value is written
- **THEN** the value is sent without restarting the dataservice

### Requirement: Form of attributes in the broker
Attributes updated through the chain SHALL have the same form as in the generated instances: numbers and booleans as JSON values, enums as IRIs, structures as `JsonProperty`. Produced by: Core Services, updates bridge. Relied on by: REST consumers.

#### Scenario: Values over REST
- **WHEN** updates pass the updates bridge and the attribute is read over REST
- **THEN** a number is a JSON number, a boolean is a JSON boolean, an enum is an IRI, and a structure is a `JsonProperty`

#### Scenario: Refused by the broker
- **WHEN** an update merges a `Property` onto a `JsonProperty`, or an IRI value in a batch merge
- **THEN** the broker answers with `400`, with `SB001` and `22023` respectively, and the updates bridge doesn't send an IRI value that way

### Requirement: The chain is verified automatically
An automated test SHALL verify these rules on GitHub-hosted runners, without a Kubernetes cluster, in stages using the real components, against the real broker image of the current release. The output of each stage SHALL be the input of the next. A logged error of a bridge SHALL fail the test.

#### Scenario: Broken contract
- **WHEN** one of the known bugs is put back: the label `PropertyIri`, Python booleans, `None` on an outage, enums without the lookup, the bridge dropping `IriProperty`, IRI values in a batch merge
- **THEN** the test fails

#### Scenario: Correct code
- **WHEN** nothing is broken
- **THEN** the test passes, and passes again when repeated

#### Scenario: Refused update
- **WHEN** the updates bridge logs that the broker refused an update
- **THEN** the test fails, even if the attribute's value arrived

#### Scenario: Relevant change
- **WHEN** a Pull Request changes a component or dependency of the chain
- **THEN** the test runs and finishes in under 10 minutes

#### Scenario: Unrelated change
- **WHEN** a Pull Request changes nothing the chain depends on
- **THEN** the test doesn't run, and the runtime of `K8s tests` is unchanged

### Requirement: The limits of the verification are stated
This specification SHALL state what the automated test doesn't cover: the step through Core Services, whose output the test takes as written, including its handling of lowercase `true` as a boolean; and real MQTT authentication and Keycloak.

#### Scenario: Reading the specification
- **WHEN** someone relies on a passing test for a change to Core Services or to authentication
- **THEN** this requirement tells them that the test doesn't verify it

### Requirement: Changes to the contract are found
The contributor guide and the agent instructions SHALL point to this specification. A change to one of these rules SHALL be an approved specification change, and the consumers named here SHALL be checked.

#### Scenario: Changing a rule
- **WHEN** a change alters one of these rules
- **THEN** it has an approved specification change, which names the affected consumers

#### Scenario: Dependency update
- **WHEN** a dependency of the chain is updated in its requirements or lock file
- **THEN** the chain test runs, without the author having to know that the dependency matters
