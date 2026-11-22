# Delta for Context Broker

## Purpose

Defines what the platform expects from its context broker: where it expects clean NGSI-LD behaviour as ETSI GS CIM 009 V1.9.1 states it, where it accepts a known deviation and works around it, and which platform requirements lie outside NGSI-LD, such as access control, configuration, the entity store that change data capture reads, and health. Each requirement names the components that rely on it, so that the broker, its patches and the platform's components converge towards a standard compliant API, one listed deviation at a time.

## ADDED Requirements

### Requirement: NGSI-LD is the reference for the broker's API
For every NGSI-LD operation and data form the platform uses, the expected behaviour SHALL be the one ETSI GS CIM 009 V1.9.1 states, and each requirement of this specification about NGSI-LD SHALL name its clause. Behaviour the standard leaves open SHALL be named as such. Relied on by: every component that calls the broker.

#### Scenario: A requirement about the API
- **WHEN** a requirement of this specification states behaviour of an NGSI-LD operation
- **THEN** it names the clause of CIM 009 V1.9.1, and the contract test checks the standard's answer

### Requirement: Upstream Scorpio 6.0.2 is the baseline
The platform SHALL run a broker based on upstream Scorpio 6.0.2 or a later release. Where that release deviates from NGSI-LD, the deviation SHALL be accepted only as an *accepted deviation* of this specification, with its clause, the components it affects and their workaround. Relied on by: the fork update (IndustryFusion/ScorpioBroker#9) and every component that works around a deviation.

#### Scenario: A deviation found
- **WHEN** a component finds that the baseline answers differently from NGSI-LD
- **THEN** the deviation is added to this specification as accepted, with its workaround, before the component relies on it

#### Scenario: A deviation fixed upstream
- **WHEN** a newer upstream release fixes an accepted deviation
- **THEN** the contract test of its scenario fails, naming the workaround that can be removed

### Requirement: What the platform adds follows NGSI-LD
A patch the platform carries on the broker, and every platform component that calls the broker, SHALL follow NGSI-LD. Either MAY deviate only where conformance would destroy scalability or performance; the deviation SHALL then be listed in this specification with that reason and its measurement. Relied on by: reviewers of fork patches and of the components named here.

#### Scenario: A patch on the broker
- **WHEN** a patch changes the broker's NGSI-LD behaviour
- **THEN** its behaviour is the standard's, or this specification lists it as a deviation with the scalability or performance reason

#### Scenario: A component calling the broker
- **WHEN** a platform component writes to or reads from the broker
- **THEN** it uses the standard's forms and answers, or its deviation is listed here as a *platform deviation* with the change that removes it

### Requirement: Deviations of the current image are transitional
The broker the platform builds today, the fork on upstream 5.0.5 at the commit `test/build-local-platform.sh` pins, deviates beyond the baseline. Those deviations SHALL be listed as *transitional deviations* and SHALL be gone once the platform moves to the baseline. Relied on by: the fork update, which is checked against this list.

#### Scenario: Move to the baseline
- **WHEN** the platform's image moves to a build on upstream 6.0.2
- **THEN** the contract test of every transitional deviation fails as fixed, and the platform workarounds depending on them are removed

### Requirement: Batch operation results
A batch create, upsert or merge SHALL answer as CIM 009 clauses 6.14.3.1, 6.15.3.1 and 6.31.3.1 state: `201` or `204` when every entity succeeds; `207` with a BatchOperationResult (clauses 5.2.16, 5.2.17) when some or none succeed; `400` only when the request as a whole is incorrect. Relied on by: updates bridge, KMS loading, the end-to-end tests. Transitional deviation: the fork answers `400` when every entity is refused, and names the members `id` and `ProblemDetails`.

#### Scenario: Every entity succeeds
- **WHEN** a batch merge of two existing entities succeeds, and a batch create of two new ones
- **THEN** the merge answers `204`, and the create answers `201` with both ids

#### Scenario: One entity of two refused
- **WHEN** a batch merge names two entities and one of them is refused
- **THEN** the other is merged, and the broker answers `207` with the other's id under `success` and the refused one under `errors` with `entityId` and `error`; while the transitional deviation stands the members are `id` and `ProblemDetails`

#### Scenario: The only entity refused
- **WHEN** a batch merge names one entity and it is refused
- **THEN** the broker answers `207` with the entity under `errors`, and while the transitional deviation stands it answers `400` with `id` and `ProblemDetails`

### Requirement: The platform reads batch results as the standard states them
A platform component that sends a batch operation SHALL treat every entity under `errors` of a `207` as refused, and SHALL report it as it reports any other refused request. Platform deviation: the updates bridge counts a `207` as success and misses the entities refused in it. It SHALL be fixed before the platform moves to the baseline, which reports every batch refusal in a `207`.

#### Scenario: Refusal inside a 207
- **WHEN** the updates bridge sends a batch merge and the broker refuses one entity of it in a `207`
- **THEN** the bridge logs that entity as refused, with the error the broker gave

### Requirement: Merge keeps what it doesn't name
A merge entity (CIM 009 clause 5.6.17) and a batch merge (clause 5.6.20) SHALL follow the merge patch behaviour of clause 5.5.12: replace the values the fragment names, keep every attribute, instance and sub-attribute it doesn't name, and delete a member whose value is NGSI-LD Null, `urn:ngsi-ld:null`. A batch merge SHALL apply to every entity it names. Relied on by: updates bridge, which sends only the changed value and relies on `unitCode`, other sub-attributes and other attributes being kept.

#### Scenario: Sub-attributes kept
- **WHEN** a value of an attribute with a `unitCode` and a sub-attribute is merged without them
- **THEN** a read returns the new value with the same `unitCode` and sub-attribute

#### Scenario: New attribute
- **WHEN** a batch merge names an attribute the entity doesn't have
- **THEN** the attribute is added and the other attributes are unchanged

#### Scenario: Relationship deleted
- **WHEN** a Relationship is merged with the object `urn:ngsi-ld:null`
- **THEN** a read no longer returns it

### Requirement: Merge of typed and language-tagged values
A merge entity and a batch merge SHALL accept a typed value and a language-tagged string as a Property's value, both NGSI-LD Values (CIM 009 clause 3.1), and store them as sent. Relied on by: updates bridge. Accepted deviation (#967) of the baseline: both refuse them with `22023`; the fork's patch (IndustryFusion/ScorpioBroker#8) removes it and SHALL be carried on the update. Workaround: the updates bridge writes such entities through `/attrs`.

#### Scenario: Typed and tagged values through a merge
- **WHEN** a declared double and a language-tagged string are merged into an existing entity by a batch merge and by a merge entity
- **THEN** both are stored with their `@type` and `@language`, and on an image without the fork's patch the batch merge reports `22023` for the entity and the merge entity answers `500`

### Requirement: Append attributes and upsert
An append to `/attrs` (CIM 009 clause 5.6.3) SHALL overwrite existing attributes unless `options=noOverwrite` is given. A batch upsert (clause 5.6.8) SHALL replace an existing entity with `options=replace`, and with `options=update` update it as clause 5.6.2 states, overwriting and appending. Relied on by: updates bridge, OPC UA instance tool and KMS loading. Transitional deviation: with `options=update` the fork keeps the value of an existing attribute.

#### Scenario: Append with overwrite
- **WHEN** a declared double, a language-tagged string and a new attribute are appended to an entity's `/attrs`
- **THEN** the broker answers `204` and a read returns each with its `@type` or `@language`

#### Scenario: Upsert
- **WHEN** an existing entity is upserted with `options=update` with a changed value of an existing attribute and a new attribute, and then with `options=replace` with a third attribute only
- **THEN** after the first upsert the existing attribute holds the new value and the new attribute is added, and after the second the entity holds only the third attribute; while the transitional deviation stands the first upsert keeps the old value

### Requirement: Batch update without overwriting
A batch update with `options=noOverwrite` (CIM 009 clauses 6.16.3.1, 5.6.9, 5.6.3) SHALL keep existing attributes and instances, append new attributes and new instances, and succeed for an entity with nothing new. Relied on by: updates bridge. Transitional deviations: the fork refuses an entity with nothing new with `404` and the detail `Not Overwriting` (T8), and doesn't append a new instance of an existing attribute (T9).

#### Scenario: Nothing new
- **WHEN** an existing entity is batch updated with `options=noOverwrite` with only attributes it already has
- **THEN** the broker answers `204` and the entity is unchanged; while T8 stands the entity is refused with `Not Overwriting`

#### Scenario: New attribute and new instance
- **WHEN** an existing entity with an instance of an attribute under one `datasetId` is batch updated with `options=noOverwrite` with a default instance of that attribute and a new attribute
- **THEN** both are appended and the existing instance keeps its value; while T9 stands only the new attribute is appended

### Requirement: A non-overwriting update uses the standard's operation
A platform component that wants to update an entity without overwriting existing attributes SHALL use an operation of the standard with that meaning, such as a batch update with `options=noOverwrite` (CIM 009 clause 5.6.9), not an upsert with `options=update`. Platform deviation: the updates bridge maps `overwriteOrReplace=false` to an upsert with `options=update`, and its test expects existing values to be kept, which is the fork's transitional deviation.

#### Scenario: Update without overwriting
- **WHEN** the updates bridge receives an upsert with `overwriteOrReplace=false` for an existing entity
- **THEN** it sends an operation whose standard meaning keeps existing values, and existing values are kept on the baseline as well

### Requirement: Value forms the broker stores
The broker SHALL store and return, as CIM 009 clauses 4.5.2, 4.5.3, 4.5.18, 4.5.20, 4.5.21 and 4.5.24 state: a Property whose value is a plain JSON value, a typed value or a language-tagged string; a Relationship's `object`; a JsonProperty's `json`; a ListProperty's `valueList`; a GeoProperty; a LanguageProperty's language map; and a VocabProperty's vocabulary. Relied on by: OPC UA instance tool, Core Services, readers of the NGSI-LD API.

#### Scenario: Every form
- **WHEN** an entity with each of these forms is created
- **THEN** a read returns each of them as it was sent

### Requirement: IRI values use the standard's form
A platform component SHALL write a Property whose value is an IRI, such as an enum value, in the form NGSI-LD gives it, a VocabProperty (CIM 009 clause 4.5.20); `{"@id": …}` is not an NGSI-LD Value (clause 3.1). Platform deviation: Core Services, the updates bridge, the dataservice and the model tools write IRI values as `{"@id": …}` in a Property, and the broker stores them only through `/attrs`. Converges mid-term, in a change of the components on the OPC UA path (`contracts/opcua-live-data`).

#### Scenario: IRI value written
- **WHEN** a platform component writes an enum value
- **THEN** it writes a VocabProperty, and while the platform deviation stands it writes a Property with `{"@id": …}` through `/attrs`

### Requirement: Declared types in the broker
The broker SHALL store a declared `@type` and its value unchanged when an entity is created or upserted. A merge of a plain value onto a declared one merges into the stored value object, as the merge patch of CIM 009 clause 5.5.12 goes into JSON objects representing a Property value, and so keeps the `@type`; an append to `/attrs` replaces the attribute and drops it. Relied on by: debezium bridge and shacl2flink (`contracts/typed-literals`), readers of the NGSI-LD API, which accept both forms.

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
The broker SHALL refuse with BadRequestData a Property whose value is JSON `null` (CIM 009 clause 4.5.0), an `observedAt` that isn't a DateTime, two default instances of one attribute in one request (clause 4.5.5), and an entity id that isn't a valid URI. Accepted deviation: a batch merge of one entity with a `null` value answers `404`, not a `207`. Transitional deviations: the fork accepts two default instances, and answers `500` for an id that isn't a URI.

#### Scenario: Null value
- **WHEN** a Property with the value `null` is merged into an entity by a merge entity, and by a batch merge of that entity and another one
- **THEN** both refuse it with BadRequestData, the stored value is unchanged, and the other entity of the batch is merged

#### Scenario: Null value in a batch of one
- **WHEN** a batch merge names one entity whose Property has the value `null`
- **THEN** the broker answers `207` with the entity under `errors` as BadRequestData, and while the accepted deviation stands it answers `404`

#### Scenario: Malformed observedAt
- **WHEN** an upsert holds an entity whose `observedAt` is `2024-02-28 13:52:32.0`
- **THEN** the entity is refused with an error under `errors` and isn't created

#### Scenario: Two default instances
- **WHEN** an upsert holds an entity with two instances of one attribute without a `datasetId`
- **THEN** the entity is refused, and while the transitional deviation stands it is created with both

#### Scenario: Id that isn't a URI
- **WHEN** an entity whose id contains a space is created
- **THEN** the broker answers `400` with BadRequestData, and while the transitional deviation stands it answers `500`

### Requirement: Core Services writes no null values
Core Services SHALL NOT write a Property whose value is JSON `null`, which cannot be an NGSI-LD value (CIM 009 clause 4.5.0). A null value means that no value is known, so Core Services SHALL deliver nothing for that attribute instance, and the broker keeps the last known value, as `contracts/opcua-live-data` (*Only values are delivered*) states for the device path. Platform deviation: Core Services writes `"value": null`, which the broker refuses, so the update is lost.

#### Scenario: A null attribute value
- **WHEN** Core Services emits an attribute whose value is null, together with another attribute of the same entity
- **THEN** the update it writes holds the other attribute and nothing for the null one, and the broker accepts it and keeps the last known value

### Requirement: The broker's own refusals
A merge that changes the type of an attribute, such as a Property onto a JsonProperty, SHALL be refused. CIM 009 doesn't state this refusal; the platform relies on Scorpio's, an error of type InvalidRequest with the detail `SB001`. Relied on by: the OPC UA chain test.

#### Scenario: Type change
- **WHEN** a Property is batch merged onto a JsonProperty
- **THEN** the entity is refused with the detail `SB001`

### Requirement: Default attribute instance
A batch merge SHALL treat an instance with `datasetId: "@none"` as the attribute's default instance (CIM 009 clause 4.5.5). Relied on by: updates bridge, which receives `@none` from Core Services. Accepted deviation: the broker answers `404`. Workaround: the updates bridge removes `@none` before merging.

#### Scenario: Default dataset id
- **WHEN** a batch merge names an instance with `datasetId: "@none"`
- **THEN** the broker merges it into the default instance, and while the deviation stands it answers `404`

### Requirement: Reads
The broker SHALL return an entity, or entities by type and attributes, for `Accept: application/json` and `Accept: application/ld+json`, answer NotAcceptable (`406`) for other media types and ResourceNotFound (`404`) for an entity that doesn't exist (CIM 009 clauses 6.3.6, 6.4 and 6.5). Relied on by: the OPC UA chain test, the shacl2flink end-to-end tests, the sub-component tool, users following the getting-started guide.

#### Scenario: Read in both forms
- **WHEN** an entity is read with `Accept: application/json` and with `Accept: application/ld+json`
- **THEN** both return it with every attribute

#### Scenario: Missing entity
- **WHEN** an entity that doesn't exist is read
- **THEN** the broker answers `404` with ResourceNotFound

### Requirement: Subscriptions and notifications
A subscription to an entity type (CIM 009 clauses 5.8, 5.2.12) SHALL notify its endpoint, over MQTT or HTTP, of every entity of that type created or changed, each under `data` with its `datasetId`. Without `notificationTrigger`, a delete SHALL NOT notify (clause 5.2.14). How many notifications a batch produces is left open. A subscription SHALL be readable by its id (clause 6.11.3.1). Relied on by: XanaAI live updates and alerts. Transitional deviation: the fork refuses that read with `403`.

#### Scenario: Create and merge
- **WHEN** a subscription exists for a type and entities of it are created, batch created, merged and appended to
- **THEN** every created or changed entity appears under `data` in a notification

#### Scenario: Batch merge of several entities
- **WHEN** a batch merge changes three entities of the type
- **THEN** each of the three appears in a notification with its new value

#### Scenario: Delete
- **WHEN** an entity of the type is deleted
- **THEN** no notification is sent for it

#### Scenario: A subscription read by its id
- **WHEN** a client with `Factory-Admin` reads a subscription it created by its id
- **THEN** the broker returns it, and while the transitional deviation stands it answers `403`

### Requirement: A merge with a sub-attribute keeps notifications working
A merge of an attribute with a sub-attribute SHALL store the sub-attribute (CIM 009 clause 5.5.12) and SHALL NOT stop later notifications. Relied on by: subscribers, and the writers of sub-attributes. Transitional deviation (#969, fixed upstream since 6.0.0): the fork stores an internal result in place of the sub-attribute, the next change stops all notifications, and liveness fails about a minute later. Workaround: the liveness probe restarts the broker.

#### Scenario: Sub-attribute merged
- **WHEN** an attribute is merged with a sub-attribute and the entity is merged again
- **THEN** a read returns the sub-attribute, the second merge is notified, and liveness stays up; while the deviation stands the second merge isn't notified and liveness fails

### Requirement: Remote contexts
The broker SHALL resolve the remote `@context` a payload names, such as the IndustryFusion contexts and the NGSI-LD core context, when it expands the payload (CIM 009 clauses 4.4 and 5.5.7). Relied on by: KMS loading, the shacl2flink end-to-end tests, users following the getting-started guide.

#### Scenario: Entity with a remote context
- **WHEN** an entity whose `@context` names a published IndustryFusion context is upserted
- **THEN** a read with that context returns its attributes by their short names

### Requirement: Requests need a token with a platform role
Access control is not part of NGSI-LD; it is a platform requirement, carried as a patch on the broker. The broker SHALL refuse a request without a valid token with `401`, and one whose token carries no platform role with `403`. Relied on by: every client, and the platform's access control as a whole.

#### Scenario: No token
- **WHEN** a client reads the entity types without a token
- **THEN** the broker answers `401`

#### Scenario: No platform role
- **WHEN** a client reads the entity types with a valid token without a platform role
- **THEN** the broker answers `403`

### Requirement: Factory-Admin may do what the platform does
A token with the role `Factory-Admin`, given as a role of the client `scorpio` or as a realm role, SHALL be allowed every operation this specification names. Relied on by: updates bridge (service account of `ngsild-updates`), users and tools (client `scorpio`), the OPC UA chain test (realm role in a self-signed token).

#### Scenario: Administrator by client role or by realm role
- **WHEN** a client creates, merges, reads and deletes an entity with a token that carries `Factory-Admin` as a role of the client `scorpio`, and again with one that carries it as a realm role
- **THEN** every request succeeds

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
Every create, change and delete of an entity SHALL become a change of one row of the broker's entity store, which the platform's change data capture publishes with the complete row before and after the change. Deleting an entity SHALL delete its row. This is a platform requirement on Scorpio's storage, not on NGSI-LD. Relied on by: debezium bridge, and through it Flink, the TimescaleDB history and the alerts.

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

### Requirement: The broker's health reflects its notifications
The broker SHALL report its startup and liveness through health checks, and liveness SHALL fail when notifications can no longer be delivered. Relied on by: the chart's probes, which restart the broker.

#### Scenario: Healthy broker
- **WHEN** the broker has started and delivers notifications
- **THEN** its startup and liveness checks are up

### Requirement: What the platform doesn't rely on
The platform SHALL NOT depend on the broker's temporal API, tenants, `Link` context headers on writes, context source registrations, its `@context` endpoint, its own Kafka topics, or the roles `Factory-Writer`, `Factory-Editor` and `Subscriber`. A broker update MAY change these.

#### Scenario: Searching the platform
- **WHEN** a change makes a component use one of these
- **THEN** it adds a requirement to this specification in the same change

### Requirement: The platform checks the broker image against this specification
The platform SHALL verify every requirement on the broker with a contract test that uses only the broker's API, health checks and what the debezium bridge publishes, never the broker's code. It SHALL run against the broker built from the commit `test/build-local-platform.sh` pins, the build the K8s tests run, and the OPC UA chain test SHALL use the same build. The platform SHALL move to a new broker commit only after the contract test passes with it.

#### Scenario: Broker image changed
- **WHEN** a Pull Request changes the broker image or the commit it is built from
- **THEN** the contract test runs against the new image

#### Scenario: Deviation fixed
- **WHEN** the broker fixes a listed deviation, whose scenario asserts the current behaviour as well
- **THEN** the test of that scenario fails, naming the deviation and the workaround that can now be removed

### Requirement: The broker fork implements this specification
The platform's broker fork SHALL reference this specification: each patch it carries SHALL name the requirement it serves, SHALL follow NGSI-LD as *What the platform adds follows NGSI-LD* states, and SHALL be tested by the fork's own unit tests. A patch that serves no requirement SHALL be dropped on the next upstream update.

#### Scenario: A patch on the broker
- **WHEN** the broker fork is updated to a new upstream release
- **THEN** every patch it carries names a requirement of this specification and has a unit test in the fork, or is dropped
