# Delta for Context Broker

## RENAMED Requirements

- FROM: `### Requirement: Deviations of the current image are transitional`
- TO: `### Requirement: Deviations of an older build are transitional`

## MODIFIED Requirements

### Requirement: Deviations of an older build are transitional
When the platform builds its broker on an upstream release older than the baseline, the deviations of that build beyond the baseline SHALL be listed as *transitional deviations* and SHALL be gone once the platform moves to the baseline. The platform builds its broker on the baseline, so no transitional deviation stands. Relied on by: a later fork update, which is checked against this list.

#### Scenario: Move to the baseline
- **WHEN** the platform's broker moves to a build on the baseline
- **THEN** the contract test of every transitional deviation fails as fixed, and the platform workarounds depending on them are removed

### Requirement: Batch operation results
A batch create, upsert or merge SHALL answer as CIM 009 clauses 6.14.3.1, 6.15.3.1 and 6.31.3.1 state: `201` or `204` when every entity succeeds; `207` with a BatchOperationResult (clauses 5.2.16, 5.2.17) when some or none succeed, with `success` an empty array when none do; `400` only when the request as a whole is incorrect. Relied on by: updates bridge, KMS loading, the end-to-end tests.

#### Scenario: Every entity succeeds
- **WHEN** a batch merge of two existing entities succeeds, and a batch create of two new ones
- **THEN** the merge answers `204`, and the create answers `201` with both ids

#### Scenario: One entity of two refused
- **WHEN** a batch merge names two entities and one of them is refused
- **THEN** the other is merged, and the broker answers `207` with the other's id under `success` and the refused one under `errors` with `entityId` and `error`

#### Scenario: The only entity refused
- **WHEN** a batch merge names one entity and it is refused
- **THEN** the broker answers `207` with the entity under `errors` and an empty `success`; without the fork's patch it leaves `success` out (accepted deviation A3)

### Requirement: The platform reads batch results as the standard states them
A platform component that sends a batch operation SHALL treat every entity under `errors` of a `207` as refused, and SHALL report it as it reports any other refused request; a `207` without a list of errors, and an entity reported neither under `success` nor under `errors`, SHALL be reported as refused too. Relied on by: the OPC UA chain test, which fails on a refusal the updates bridge logs.

#### Scenario: Refusal inside a 207
- **WHEN** the updates bridge sends a batch merge and the broker refuses one entity of it in a `207`
- **THEN** the bridge logs that entity as refused, with the error the broker gave

#### Scenario: Entity neither merged nor refused
- **WHEN** the updates bridge sends a batch merge of two entities and the broker answers `207` with one of them under `success` and no list of errors
- **THEN** the bridge logs the other entity as refused

### Requirement: Append attributes and upsert
An append to `/attrs` (CIM 009 clause 5.6.3) SHALL overwrite existing attributes unless `options=noOverwrite` is given. A batch upsert (clause 5.6.8) SHALL replace an existing entity with `options=replace`, and with `options=update` update it as clause 5.6.2 states, overwriting and appending. Relied on by: updates bridge, OPC UA instance tool and KMS loading.

#### Scenario: Append with overwrite
- **WHEN** a declared double, a language-tagged string and a new attribute are appended to an entity's `/attrs`
- **THEN** the broker answers `204` and a read returns each with its `@type` or `@language`

#### Scenario: Upsert
- **WHEN** an existing entity is upserted with `options=update` with a changed value of an existing attribute and a new attribute, and then with `options=replace` with a third attribute only
- **THEN** after the first upsert the existing attribute holds the new value and the new attribute is added, and after the second the entity holds only the third attribute

### Requirement: Batch update without overwriting
A batch update with `options=noOverwrite` (CIM 009 clauses 6.16.3.1, 5.6.9, 5.6.3) SHALL keep existing attributes and instances, append new attributes and new instances, and succeed for an entity with nothing new. Relied on by: updates bridge (*A non-overwriting update uses the standard's operation*).

#### Scenario: Nothing new
- **WHEN** an existing entity is batch updated with `options=noOverwrite` with only attributes it already has
- **THEN** the broker answers `204` and the entity is unchanged

#### Scenario: New attribute and new instance
- **WHEN** an existing entity with an instance of an attribute under one `datasetId` is batch updated with `options=noOverwrite` with a default instance of that attribute and a new attribute
- **THEN** both are appended and the existing instance keeps its value

### Requirement: A non-overwriting update uses the standard's operation
A platform component that wants to update an entity without overwriting existing attributes SHALL use an operation of the standard with that meaning, such as a batch create followed by a batch update with `options=noOverwrite` (CIM 009 clauses 5.6.7, 5.6.9), not an upsert with `options=update`. Relied on by: the updates bridge for `overwriteOrReplace=false`.

#### Scenario: Update without overwriting
- **WHEN** the updates bridge receives an upsert with `overwriteOrReplace=false` for an existing entity
- **THEN** existing values are kept and new attributes are added

### Requirement: Value forms the broker stores
The broker SHALL store and return, as CIM 009 clauses 4.5.2, 4.5.3, 4.5.18, 4.5.20, 4.5.21 and 4.5.24 state: a Property with a plain JSON value, a typed value or a language-tagged string; a Relationship's `object`; a JsonProperty's `json`; a ListProperty's `valueList`; a GeoProperty; a LanguageProperty's language map; and a VocabProperty's vocabulary. Relied on by: OPC UA instance tool, Core Services, readers of the NGSI-LD API. Accepted deviation A5 of the baseline: see the scenarios.

#### Scenario: Every form
- **WHEN** an entity with each of these forms is created
- **THEN** a read returns each of them as it was sent

#### Scenario: Sub-attribute array on an instance with a datasetId
- **WHEN** an entity is upserted whose attribute instance has a `datasetId` and a sub-attribute written as an array of instances (clauses 4.5.2, 4.5.3, 4.5.5)
- **THEN** the broker accepts it and a read returns the sub-attribute's instances; without the fork's patch (IndustryFusion/ScorpioBroker#16) it refuses the entity with `400`

### Requirement: Refusals the platform relies on
The broker SHALL refuse with BadRequestData a Property whose value is JSON `null` (CIM 009 clause 4.5.0), an `observedAt` that isn't a DateTime, two default instances of one attribute in one request (clause 4.5.5), and an entity id that isn't a valid URI. Accepted deviation A3 of the baseline: a batch merge of one entity with a `null` value answers `404`, not a `207`, and a fully refused batch leaves `success` out; the fork's patch (IndustryFusion/ScorpioBroker#12) removes both.

#### Scenario: Null value
- **WHEN** a Property with the value `null` is merged into an entity by a merge entity, and by a batch merge of that entity and another one
- **THEN** both refuse it with BadRequestData, the stored value is unchanged, and the other entity of the batch is merged

#### Scenario: Null value in a batch of one
- **WHEN** a batch merge names one entity whose Property has the value `null`
- **THEN** the broker answers `207` with the entity under `errors` as BadRequestData; without the fork's patch it answers `404`

#### Scenario: Malformed observedAt
- **WHEN** an upsert holds an entity whose `observedAt` is `2024-02-28 13:52:32.0`
- **THEN** the entity is refused with an error under `errors` and isn't created

#### Scenario: Two default instances
- **WHEN** an upsert holds an entity with two instances of one attribute without a `datasetId`
- **THEN** the entity is refused

#### Scenario: Id that isn't a URI
- **WHEN** an entity whose id contains a space is created
- **THEN** the broker answers `400` with BadRequestData

### Requirement: Core Services writes no null values
Core Services SHALL NOT write a Property whose value is JSON `null`, which cannot be an NGSI-LD value (CIM 009 clause 4.5.0). A null value means that no value is known, so Core Services SHALL deliver nothing for that attribute instance, and the broker keeps the last known value, as `contracts/opcua-live-data` (*Only values are delivered*) states for the device path.

#### Scenario: A null attribute value
- **WHEN** Core Services emits an attribute whose value is null, together with another attribute of the same entity
- **THEN** the update it writes holds the other attribute and nothing for the null one, and the broker accepts it and keeps the last known value

### Requirement: Default attribute instance
A batch merge SHALL treat an instance with `datasetId: "@none"` as the attribute's default instance (CIM 009 clause 4.5.5). Relied on by: updates bridge, which receives `@none` from Core Services. Accepted deviation A2 of the baseline: the broker answers `404`; the fork's patch (IndustryFusion/ScorpioBroker#11) removes it. The updates bridge still removes `@none` before merging, which keeps the same meaning.

#### Scenario: Default dataset id
- **WHEN** a batch merge names an instance with `datasetId: "@none"`
- **THEN** the broker merges it into the default instance; without the fork's patch it answers `404`

### Requirement: Subscriptions and notifications
A subscription to an entity type (CIM 009 clauses 5.8, 5.2.12) SHALL notify its MQTT or HTTP endpoint of every entity of that type created or changed, each under `data` with its `datasetId`, with or without `receiverInfo` or `notifierInfo` (clause 5.2.15). Without `notificationTrigger`, a delete SHALL NOT notify (clause 5.2.12). A subscription SHALL be readable by its id (clause 6.11.3.1). Relied on by: XanaAI live updates and alerts. Accepted deviation A4 of the baseline: see the scenarios.

#### Scenario: Create and merge
- **WHEN** a subscription exists for a type and entities of it are created, batch created, merged and appended to
- **THEN** every created or changed entity appears under `data` in a notification

#### Scenario: Batch merge of several entities
- **WHEN** a batch merge changes three entities of the type
- **THEN** each of the three appears in a notification with its new value; how many notifications carry them is left open

#### Scenario: Delete
- **WHEN** an entity of the type is deleted
- **THEN** no notification is sent for it

#### Scenario: A subscription read by its id
- **WHEN** a client with `Factory-Admin` reads a subscription it created by its id
- **THEN** the broker returns it

#### Scenario: MQTT endpoint without receiverInfo
- **WHEN** a subscription notifies an `mqtt://` endpoint without `receiverInfo`, as the first subscription of a freshly started broker
- **THEN** the notification arrives; without the fork's patch it is lost

### Requirement: A merge with a sub-attribute keeps notifications working
A merge of an attribute with a sub-attribute SHALL store the sub-attribute (CIM 009 clause 5.5.12) and SHALL NOT stop later notifications. Relied on by: subscribers, and the writers of sub-attributes.

#### Scenario: Sub-attribute merged
- **WHEN** an attribute is merged with a sub-attribute and the entity is merged again
- **THEN** a read returns the sub-attribute, the second merge is notified, and liveness stays up

### Requirement: The broker runs with the platform's configuration
The broker SHALL take its database, Kafka, topic and identity provider settings from the environment variables the platform's chart sets, SHALL connect to Postgres over TLS, and SHALL accept tokens signed with a configured public key instead of an identity provider. Kafka SHALL be required at startup. The broker SHALL NOT record entity history unless configured to, as the platform doesn't use the temporal API. Relied on by: the chart of the broker, the OPC UA chain test.

#### Scenario: Start with the chart's variables
- **WHEN** the broker image starts with the variables of the platform's chart against Postgres 14 with PostGIS 3.4 serving TLS, and Kafka
- **THEN** it answers requests, and its startup and liveness health checks are up

#### Scenario: Without an identity provider
- **WHEN** the broker starts with a public key and an issuer instead of the identity provider's address
- **THEN** it accepts a token signed with the matching private key

#### Scenario: No history by default
- **WHEN** the broker runs with the chart's variables and entities change
- **THEN** it writes no entity history
