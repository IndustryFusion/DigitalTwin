# Delta for Context Broker

## Purpose

Defines what the platform expects from its NGSI-LD context broker at its interfaces, independent of how a broker implements it: the API operations and value forms the platform's components use, the entity store that change data capture reads, the configuration and health checks the deployment relies on, the refusals components rely on, and where the platform works around the broker today. Each requirement names the components that rely on it. The platform checks a broker image against this specification with a black-box contract test; the broker fork references it, implements it and tests its patches itself.

## ADDED Requirements

### Requirement: Requests need a token with a platform role
The broker SHALL refuse a request without a valid token with `401`, and a request whose token carries no platform role with `403`. Relied on by: every client, and the platform's access control as a whole.

#### Scenario: No token
- **WHEN** a client reads the entity types without a token
- **THEN** the broker answers `401`

#### Scenario: No platform role
- **WHEN** a client reads the entity types with a valid token without a platform role
- **THEN** the broker answers `403`

### Requirement: Factory-Admin may do what the platform does
A token with the role `Factory-Admin`, given as a role of the client `scorpio` or as a realm role, SHALL be allowed every operation this specification names. Relied on by: updates bridge (service account of `ngsild-updates`), users and tools (client `scorpio`), the OPC UA chain test (realm role in a self-signed token). Known deviation: reading one subscription by its id is refused with `403`; no platform component reads it.

#### Scenario: Administrator by client role or by realm role
- **WHEN** a client creates, merges, reads and deletes an entity with a token that carries `Factory-Admin` as a role of the client `scorpio`, and again with one that carries it as a realm role
- **THEN** every request succeeds

#### Scenario: A subscription read by its id
- **WHEN** a client with `Factory-Admin` reads a subscription it created by the subscription's id
- **THEN** the broker returns the subscription, and while the deviation stands it answers `403`

### Requirement: Factory-Reader only reads
A token with only the role `Factory-Reader` SHALL be allowed to read entities and types, and SHALL be refused every write with `403`.

#### Scenario: Reader
- **WHEN** a client with only `Factory-Reader` reads the entity types and then creates an entity
- **THEN** the read succeeds and the create is refused with `403`

### Requirement: The broker runs with the platform's configuration
The broker SHALL take its database, Kafka, topic and identity provider settings from the environment variables the platform's chart sets, SHALL connect to Postgres over TLS, and SHALL accept tokens signed with a configured public key instead of an identity provider. Kafka SHALL be required at startup. Relied on by: the chart of the broker, the OPC UA chain test.

#### Scenario: Start with the chart's variables
- **WHEN** the broker image starts with the variables of the platform's chart against Postgres 14 with PostGIS 3.4 serving TLS, and Kafka
- **THEN** it answers requests, and its startup and liveness health checks are up

#### Scenario: Without an identity provider
- **WHEN** the broker starts with a public key and an issuer instead of the identity provider's address
- **THEN** it accepts a token signed with the matching private key

### Requirement: Entity changes are published through the entity store
Every create, change and delete of an entity SHALL become a change of one row of the broker's entity store, which the platform's change data capture publishes with the complete row before and after the change. Deleting an entity SHALL delete its row. Relied on by: debezium bridge, and through it Flink, the TimescaleDB history and the alerts.

#### Scenario: Create and change
- **WHEN** an entity with a Property, a Relationship, a GeoProperty, a JsonProperty, a ListProperty and a sub-attribute is created and one value is changed
- **THEN** the debezium bridge publishes each attribute with its value, `datasetId` and sub-attributes, and after the change publishes the changed attribute with its new value

#### Scenario: Delete
- **WHEN** the entity is deleted
- **THEN** the debezium bridge publishes the entity and each of its attributes as deleted

### Requirement: The entity store holds expanded JSON-LD
A row of the entity store SHALL hold the entity's id, its types with the first one first, and the entity as expanded JSON-LD: each attribute as a list of instances with its type, `datasetId`, `unitCode`, `observedAt` and a modification time; the value under `hasValue` with its `@value` or `@id` and its `@type`, or under `hasObject`, `hasJSON` or `hasValueList`; and sub-attributes nested in their instance. Relied on by: debezium bridge.

#### Scenario: Declared value in the store
- **WHEN** an entity holding a declared double is created
- **THEN** the debezium bridge publishes its value with the type `xsd:double`

#### Scenario: Update of the broker on an existing store
- **WHEN** the broker is updated on a store holding entities written by the previous version
- **THEN** a re-snapshot publishes the same attributes and values as before the update

### Requirement: Attribute writes of the platform
The broker SHALL accept, with `204`, a batch merge, a merge entity and an append to `/attrs` with overwrite whose attributes give the full IRI of their type in plain JSON, with `observedAt` and a `datasetId`; and an upsert with `options=replace` or `options=update`, with `201` or `204`. Relied on by: updates bridge (written by Core Services), OPC UA instance tool and KMS loading (upsert).

#### Scenario: Plain values through a batch merge
- **WHEN** the updates bridge merges a number, a boolean, a string, a JsonProperty, a ListProperty and a Relationship into existing entities
- **THEN** the broker answers `204` and a read returns each value in the form it was sent

#### Scenario: Upsert
- **WHEN** an entity is upserted with `options=update` with a new `datasetId` instance of an existing attribute, and then with `options=replace` without that attribute
- **THEN** after the first upsert the entity holds the old and the new instance, and after the second it holds only the attributes of the second upsert

### Requirement: Value forms the broker accepts
The broker SHALL store and return as a Property's value a plain number, boolean or string, a value object with `@value` and `@type`, a value object with `@value` and `@language`, and an IRI as `{"@id": …}`; a Relationship's `object`, a JsonProperty's `json`, a ListProperty's `valueList`, a GeoProperty, a LanguageProperty's language map and a VocabProperty's IRI. Relied on by: OPC UA instance tool, Core Services, readers of the NGSI-LD API.

#### Scenario: Value objects through /attrs
- **WHEN** a declared double, a language-tagged string and an IRI value are appended to an entity's `/attrs` with overwrite
- **THEN** the broker answers `204` and a read returns each value with its `@type`, `@language` or `@id`

#### Scenario: Language and vocabulary
- **WHEN** an entity with a LanguageProperty and a VocabProperty is created
- **THEN** a read returns the language map and the vocabulary IRI

### Requirement: Value objects are merged
A batch merge and a merge entity SHALL accept a value object with `@type`, `@language` or `@id` and store it as sent. Relied on by: updates bridge. Known deviation (#967): both refuse it with `22023`, the merge entity with `500`. Workaround: the updates bridge sends entities with IRI values, and with #1022 those with declared values, to `/attrs`.

#### Scenario: Value objects through a merge
- **WHEN** a declared double, a language-tagged string and an IRI value are merged into an existing entity by a batch merge and by a merge entity
- **THEN** the broker answers `204` and a read returns each value with its `@type`, `@language` or `@id`, and while the deviation stands the batch merge reports `22023` for the entity and the merge entity answers `500`

### Requirement: A merge changes only what it names
A merge SHALL replace the values it names and keep every attribute, instance and sub-attribute it doesn't name, also in a nested merge. A merge of a Relationship whose `object` is `urn:ngsi-ld:null` SHALL delete it. A batch merge SHALL apply to every entity it names. Relied on by: updates bridge, which sends only the changed value and relies on `unitCode`, other sub-attributes and other attributes being kept.

#### Scenario: Sub-attributes kept
- **WHEN** a value of an attribute with a `unitCode` and a sub-attribute is merged without them
- **THEN** a read returns the new value with the same `unitCode` and sub-attribute

#### Scenario: New attribute
- **WHEN** a batch merge names an attribute the entity doesn't have
- **THEN** the attribute is added and the other attributes are unchanged

#### Scenario: Relationship deleted
- **WHEN** a Relationship is merged with the object `urn:ngsi-ld:null`
- **THEN** a read no longer returns it

### Requirement: Declared types in the broker
The broker SHALL store a declared `@type` and its value unchanged when an entity is created or upserted. A merge of a plain value onto a declared one SHALL keep the stored `@type`. An append to `/attrs` with a plain value SHALL replace the value object and drop the type. Relied on by: debezium bridge and shacl2flink (`contracts/typed-literals`), readers of the NGSI-LD API.

#### Scenario: Declared value stored
- **WHEN** an entity holding `{"@value": 0, "@type": "http://www.w3.org/2001/XMLSchema#double"}` is upserted
- **THEN** a read returns the value with that type

#### Scenario: Plain value merged onto a declared one
- **WHEN** the plain number 42.5 and then the string `"42.5"` are batch merged onto that value
- **THEN** a read returns each with the type `http://www.w3.org/2001/XMLSchema#double`

#### Scenario: Plain value through /attrs
- **WHEN** the plain number 42.5 is appended to `/attrs` with overwrite
- **THEN** a read returns the plain number 42.5

### Requirement: Refusals the platform relies on
The broker SHALL refuse a merge that changes the type of an attribute, such as a Property onto a JsonProperty, with `SB001`; a Property whose value is `null`; and an `observedAt` that isn't ISO 8601. Relied on by: the OPC UA chain test, the shacl2flink end-to-end tests. Known gap of the platform: Core Services writes `null` values, which the broker refuses.

#### Scenario: Type change
- **WHEN** a Property is batch merged onto a JsonProperty
- **THEN** the response names the entity with `SB001`

#### Scenario: Null value
- **WHEN** a Property with the value `null` is merged into an entity by a merge entity and by a batch merge
- **THEN** both are refused and the stored value is unchanged

#### Scenario: Malformed observedAt
- **WHEN** an upsert holds an entity whose `observedAt` is `2024-02-28 13:52:32.0`
- **THEN** the response names that entity with an error and the entity isn't created

### Requirement: Refusals in a batch are reported per entity
A refusal in a batch operation SHALL name the entity and its error, in a response with `400` when every entity is refused or `207` when some are, and components SHALL find the refusal in either. A refused entity of an upsert SHALL NOT be created. Relied on by: the updates bridge, the shacl2flink end-to-end tests (which treat `207` from an upsert as a failure). Known gap of the platform: the updates bridge counts `207` as success.

#### Scenario: One entity of two refused
- **WHEN** a batch merge names two entities and one of them is refused
- **THEN** the other is merged, and the response names the refused one with its error

#### Scenario: The only entity refused
- **WHEN** a batch merge names one entity and it is refused
- **THEN** the response names it with its error, with `400` or `207`

### Requirement: Default dataset id in a batch merge
A batch merge SHALL merge an instance with `datasetId: "@none"` into the attribute's default instance. Relied on by: updates bridge, which receives `@none` from Core Services. Known deviation: the broker answers `404`. Workaround: the updates bridge removes `@none` before merging.

#### Scenario: Default dataset id
- **WHEN** a batch merge names an instance with `datasetId: "@none"`
- **THEN** the broker merges it into the default instance, and while the deviation stands it answers `404`

### Requirement: Reads
The broker SHALL return an entity, or entities by type and attributes, for `Accept: application/json` and `Accept: application/ld+json`, with IRI values as `{"@id": …}` or `{"id": …}`. It SHALL answer `404` for an entity that doesn't exist. Relied on by: the OPC UA chain test, the shacl2flink end-to-end tests, the sub-component tool, users following the getting-started guide.

#### Scenario: Read in both forms
- **WHEN** an entity is read with `Accept: application/json` and with `Accept: application/ld+json`
- **THEN** both return it with every attribute

#### Scenario: Missing entity
- **WHEN** an entity that doesn't exist is read
- **THEN** the broker answers `404`

### Requirement: Notifications of subscriptions
A subscription to an entity type SHALL notify its endpoint, over MQTT or HTTP, of every entity of that type that is created by create or batch create, or changed by merge entity, batch merge or append to `/attrs`, with each entity under `data` and its `datasetId` kept. Each changed entity SHALL appear in a notification; how many notifications a batch produces is not part of this requirement. Deleting an entity SHALL NOT notify. Relied on by: XanaAI live updates and alerts.

#### Scenario: Create and merge
- **WHEN** a subscription exists for a type and entities of it are created, batch merged, merged and appended to
- **THEN** every created or changed entity appears under `data` in a notification

#### Scenario: Batch merge of several entities
- **WHEN** a batch merge changes three entities of the type
- **THEN** each of the three appears in a notification with its new value

#### Scenario: Delete
- **WHEN** an entity of the type is deleted
- **THEN** no notification is sent for it

### Requirement: The broker's health reflects its notifications
The broker SHALL report its startup and liveness through health checks, and liveness SHALL fail when notifications can no longer be delivered. Relied on by: the chart's probes, which restart the broker.

#### Scenario: Healthy broker
- **WHEN** the broker has started and delivers notifications
- **THEN** its startup and liveness checks are up

### Requirement: A merge with a sub-attribute keeps notifications working
A merge of an attribute with a sub-attribute SHALL store the sub-attribute, and SHALL NOT stop later notifications. Relied on by: subscribers, and the writers of sub-attributes. Known deviation (#969): the broker stores an internal result in place of the sub-attribute, the next change of the entity stops all notifications, and liveness fails about a minute later. Workaround: the liveness probe restarts the broker; the entity and the consumer offset are repaired by hand.

#### Scenario: Sub-attribute merged
- **WHEN** an attribute is merged with a sub-attribute and the entity is merged again
- **THEN** a read returns the sub-attribute, the second merge is notified, and liveness stays up; while the deviation stands the second merge isn't notified and liveness fails

### Requirement: Remote contexts
The broker SHALL resolve the remote `@context` a payload names, such as the IndustryFusion contexts and the NGSI-LD core context, when it expands the payload. Relied on by: KMS loading, the shacl2flink end-to-end tests, users following the getting-started guide.

#### Scenario: Entity with a remote context
- **WHEN** an entity whose `@context` names a published IndustryFusion context is upserted
- **THEN** a read with that context returns its attributes by their short names

### Requirement: What the platform doesn't rely on
The platform SHALL NOT depend on the broker's temporal API, tenants, `Link` context headers on writes, context source registrations, its `@context` endpoint, its own Kafka topics, the roles `Factory-Writer`, `Factory-Editor` and `Subscriber`, or the acceptance of several default instances of one attribute in one request. A broker update MAY change these.

#### Scenario: Searching the platform
- **WHEN** a change makes a component use one of these
- **THEN** it adds a requirement to this specification in the same change

### Requirement: The platform checks the broker image against this specification
The platform SHALL verify every requirement with a contract test that treats the broker as a black box: it uses only the broker's API, health checks and what the debezium bridge publishes, never the broker's code. It SHALL run against the image the release deploys, which the OPC UA chain test and the K8s tests SHALL use too. The platform SHALL move to a new broker image only after the contract test passes with it.

#### Scenario: Broker image changed
- **WHEN** a Pull Request changes the broker image or the commit it is built from
- **THEN** the contract test runs against the new image

#### Scenario: Deviation fixed
- **WHEN** the broker fixes a known deviation, whose scenario asserts the current behaviour as well
- **THEN** the test of that scenario fails, naming the deviation and the workaround that can now be removed

### Requirement: The broker fork implements this specification
The platform's broker fork SHALL reference this specification: each patch it carries SHALL name the requirement it serves, and SHALL be tested by the fork's own unit tests. A patch that serves no requirement SHALL be dropped on the next upstream update. How the fork implements a requirement is not part of this specification.

#### Scenario: A patch on the broker
- **WHEN** the broker fork is updated to a new upstream release
- **THEN** every patch it carries names a requirement of this specification and has a unit test in the fork, or is dropped
