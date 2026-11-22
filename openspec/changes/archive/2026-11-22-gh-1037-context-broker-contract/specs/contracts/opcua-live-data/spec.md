# Delta for OPC UA Live Data

## MODIFIED Requirements

### Requirement: Form of attributes in the broker
Attributes updated through the chain SHALL have the same form as in the generated instances: numbers and booleans as JSON values, enums as IRIs, structures as `JsonProperty`. Produced by: Core Services, updates bridge. Relied on by: REST consumers. What the broker accepts, stores and refuses is stated in `contracts/context-broker`.

#### Scenario: Values over REST
- **WHEN** updates pass the updates bridge and the attribute is read over REST
- **THEN** a number is a JSON number, a boolean is a JSON boolean, an enum is an IRI, and a structure is a `JsonProperty`

#### Scenario: Refused by the broker
- **WHEN** an update merges a `Property` onto a `JsonProperty`
- **THEN** the broker refuses it as `contracts/context-broker` states (*The broker's own refusals*, *Batch operation results*)

### Requirement: The chain is verified automatically
An automated test SHALL verify these rules on GitHub-hosted runners, without a Kubernetes cluster, in stages using the real components, against the broker the platform pins (`contracts/context-broker`, *The platform checks the broker image against this specification*). The output of each stage SHALL be the input of the next. A logged error of a bridge SHALL fail the test.

#### Scenario: Broken contract
- **WHEN** one of the known bugs is put back: the label `PropertyIri`, Python booleans, `None` on an outage, enums without the lookup, the bridge dropping `IriProperty`
- **THEN** the test fails

#### Scenario: Correct code
- **WHEN** nothing is broken
- **THEN** the test passes, and passes again when repeated

#### Scenario: Refused update
- **WHEN** the updates bridge logs that the broker refused an update
- **THEN** the test fails, even if the attribute's value arrived

#### Scenario: Relevant change
- **WHEN** a Pull Request changes a component or dependency of the chain
- **THEN** the test runs and finishes in under 10 minutes once the pinned broker is built and cached; a run that builds it for a new pin takes longer

#### Scenario: Unrelated change
- **WHEN** a Pull Request changes nothing the chain depends on
- **THEN** the test doesn't run, and the runtime of `K8s tests` is unchanged
