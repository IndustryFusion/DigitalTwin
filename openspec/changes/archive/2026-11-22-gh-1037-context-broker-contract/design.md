# Design

## Context

The platform deploys only Scorpio's all-in-one runner (`helm/charts/scorpio`).
The K8s tests build it from the fork commit `test/build-local-platform.sh`
pins, `e1cea4bc` since #1040: `135b5ee` plus the merge fix for value objects
(IndustryFusion/ScorpioBroker#8). The published release image
`ibn40/scorpio-all-in-one-runner:v0.10`, which the OPC UA chain test pulls,
is still a build of `135b5ee`. No component uses Scorpio's temporal
API, tenants or Kafka topics. Data leaves the broker through Debezium on its
`public.entity` table, not through its API. The only runtime writer is the
updates bridge, which carries Core Services' writeback. XanaAI, outside this
repository, depends on its subscriptions.

### What the fork carries

The fork is upstream `5.0.5-java` plus five commits. None is in 6.0.1 or
6.0.2.

| Commit | Change | Requirement it serves |
|---|---|---|
| `67cdf1c` | Keycloak OIDC and role checks on every endpoint | *Requests need a token with a platform role*, *Factory-Admin may do what the platform does*, *Factory-Reader only reads* |
| `67cdf1c` | the chart's environment variables, `sslmode=require` | *The broker runs with the platform's configuration* |
| `67cdf1c` | `REPLICA IDENTITY FULL` on the entity table, edited into the migration `V20190604.1` (an update must add it as a new migration, or Flyway's checksum of `V20190604.1` breaks existing databases) | *Entity changes are published through the entity store* |
| `67cdf1c`, `a754fd8` | history managers out of the build, the at-context server back in | none (*What the platform doesn't rely on*) |
| `45e40a4` | image name | none |
| `135b5ee` | one notification for a whole batch merge, instead of one per entity | none: *Subscriptions and notifications* holds for both (D4) |
| `e1cea4b` | merge of value objects with `@type`, `@id` or `@language` as a whole (IndustryFusion/ScorpioBroker#8) | *Merge of typed and language-tagged values*: removes A1 (D9); carried on the update |

### Measured

Measured on 2026-11-21 on the light stack of `test/opcua-chain` with
Postgres 14/PostGIS 3.4 and Kafka. The upstream images are
`scorpiobroker/all-in-one-runner:java-kafka-6.0.1` and
`java-kafka-latest`, which is 6.0.2 (built 2026-07-03, and it validates IDs as
6.0.2's release notes say). They were started with upstream's variable names
and have no authorisation.

| Behaviour | `v0.10` (fork) | 6.0.1 | 6.0.2 |
|---|---|---|---|
| no token | `401` | no authorisation | no authorisation |
| `Factory-Reader`: read / create | `200` / `403` | n/a | n/a |
| `Factory-Writer`: create / read / delete | `201` / `403` / `403` | n/a | n/a |
| `Factory-Admin` as client role and as realm role | both allowed | n/a | n/a |
| `GET /subscriptions/{id}` as `Factory-Admin` | `403` | `200` | `200` |
| missing entity / `Accept: text/plain` | `404` / `406` | same | same |
| merge entity / batch merge with `"value": null` | `400` / `404` | same | same |
| batch merge with `datasetId: "@none"` | `404` | `404` | `404` |
| upsert with two default instances of one attribute | `201`, both stored | `207`, entity not created | as 6.0.1 |
| LanguageProperty, VocabProperty, tagged string: create and read | stored and returned | same | same |
| merge entity of a declared double | `500` `22023` | `500` `22023` | `500` `22023` |
| batch merge of a declared double, an IRI, a tagged string | `400` `22023` | `207` with `22023` | as 6.0.1 |
| batch merge of a Property onto a JsonProperty | `400` `SB001` | `207` with `SB001` | as 6.0.1 |
| `/attrs` with a declared double | `204` | `204` | `204` |
| entity id with a space | `500` | `201` | `400` |
| notifications: batch create of 3 | 1 with 3 entities | 1 with 3 | 1 with 3 |
| notifications: batch merge of 3 | 1 with 3 entities | 3 with 1 each | as 6.0.1 |
| notifications: merge entity, `/attrs`, delete | 1, 1, none | same | same |
| merge with a sub-attribute, then another merge | internal result stored, second merge not notified, liveness `DOWN` after about 60 s | stored correctly, notified | as 6.0.1 |
| upsert `options=update` with a changed value of an existing attribute | the stored value is kept, new attributes are added | not measured | **the value is overwritten**, new attributes are added |
| batch merge of two entities, one with `"value": null` | `207`: the null one refused, the other merged | not measured | as `v0.10` |

The last two rows come from the contract test of this change (`test/context-broker`). On 6.0.2 it fails exactly
on *Upsert* (the overwrite) and on the fixed sub-attribute deviation; every other scenario it can run there
passes, and the six checks of authorisation are skipped because upstream has none. The overwrite matters to the
updates bridge, which sends `options=update` for an upsert without `overwriteOrReplace`.

The 6.0.1 code agrees with these results: `merge_has_value` is unchanged
since `V20240801.1__mergepatchfix.sql`, so #967 is still there.
`V20250418.1__fixdeleteattrib.sql` (in 6.0.0) fixes the sub-attribute merge
(#969). 6.0.2 adds no migration.

The standard's answers these results are judged against (D9) were read from ETSI GS CIM 009 V1.9.1 (2025-07): batch results in
clauses 6.14.3.1, 6.15.3.1 and 6.31.3.1 (`207` "if only some or none of the entities" succeed, `400` only
when "the request or its content is incorrect"), BatchOperationResult and BatchEntityError in 5.2.16 and
5.2.17 (`success`, `errors`, `entityId`, `error`), upsert `options=update` in 5.6.8 with Update Attributes
in 5.6.2 ("updating already existing Attributes … and appending non-existing ones"), JSON `null` in 4.5.0
("null cannot be used as a value in NGSI-LD"), the default instance and `@none` in 4.5.5, NGSI-LD Value in
3.1, merge patch in 5.5.12, and the default notification triggers in 5.2.14 (`attributeCreated`,
`attributeUpdated`).

## Decisions

### D1 — NGSI-LD is the reference, upstream Scorpio 6.0.2 the baseline

- **Chosen:** wherever the platform uses NGSI-LD, the expected behaviour is the standard's, CIM 009
  V1.9.1, named by its clause. Upstream Scorpio 6.0.2 is the baseline broker: where it implements the
  standard, the platform expects exactly that; where it deviates, the deviation is accepted, listed with
  its workaround, and left to upstream or to a patch when one is useful. What the platform adds itself, fork
  patches and its own components, follows the standard, unless conformance would destroy scalability or
  performance, which is then stated with a measurement. Requirements outside NGSI-LD, such as access
  control, configuration, the entity store and health, are stated as platform requirements.
- So the platform converges towards a standard compliant API one listed deviation at a time, and a
  deviation is never silently made part of the contract.
- *Alternative:* specify what the platform uses as the current image answers it (this change's first
  draft). Rejected: it made the fork's deviations the contract, e.g. `400` for a fully refused batch and an
  upsert with `options=update` that keeps existing values.
- *Alternative:* require full conformance of the baseline now. Rejected: the baseline has deviations nobody
  can remove from here before the update, and the platform depends on working around them.
- *Alternative:* specify the broker against all of CIM 009. Rejected: most of it is unused, and the spec
  would be far larger than what any test of ours can back (acceptance criterion 2).

### D2 — A deviation states the target and the current behaviour

- **Chosen:** the requirement states the standard's behaviour. A deviation paragraph names its kind
  (accepted, transitional or platform, D9), its issue and the workaround, and the scenario adds "while the
  deviation stands" with today's answer. The test asserts today's answer and fails when the broker changes
  it, naming the workaround to remove.
- *Alternative:* specify only the target. Rejected: the tests would be red on the image the platform runs,
  and a red test that is expected teaches people to ignore it.
- *Alternative:* specify only today's behaviour. Rejected: it would make the deviation the contract (D1).

### D3 — Batch results as the standard states them

- **Chosen:** a batch create, upsert or merge answers `201` or `204` when every entity succeeds, `207` with
  a BatchOperationResult (`success`, `errors` of `entityId` and `error`) when some or none succeed, and
  `400` only for a request that is incorrect as a whole. 6.0.2 answers so. The fork answers `400` with
  `id` and `ProblemDetails` when every entity is refused: a transitional deviation.
- The updates bridge counts `207` as success, so on the baseline it would lose every refusal silently,
  and the chain test would no longer see them. That is a platform deviation (P1), and its fix must land
  before the platform moves to the baseline.
- *Alternative:* accept `400` or `207` (this change's first draft). Rejected: it is not the standard, and
  consumers would have to know both forms forever.

### D4 — Notifications are specified per entity, not per message

- **Chosen:** every created or changed entity appears in a notification. The standard leaves open how many
  notifications a batch produces. The fork's patch `135b5ee` (one notification per batch merge) serves no
  requirement; the fork update may drop it, or keep it with a measured performance reason (D1).
- *Alternative:* require one notification per batch, as the fork does. Not chosen without evidence: the
  patch's commit gives no reason, and no consumer in this repository reads notifications. Open question 2
  asks XanaAI.

### D5 — Only the roles the realm defines are part of the contract

- **Chosen:** `Factory-Admin` (everything the platform does) and `Factory-Reader` (reads only). Access
  control is not part of NGSI-LD; it is a platform requirement carried as a fork patch. The fork also names
  `Factory-Editor` and `Subscriber`, which the `iff` realm doesn't define. Nobody is given
  `Factory-Writer`, and it can create but not read, so it isn't relied on.
- *Alternative:* add the fork's other roles to the realm and specify them. Rejected for now: no component
  needs them.
- Roles are accepted as client roles of `scorpio` (real tokens) and as realm roles (the chain test's
  self-signed token); both were measured.

### D6 — Where the requirements are tested

- **Chosen:** a contract test on the light stack of `test/opcua-chain` (GitHub-hosted, the stack is up in
  about 15 s) for every API requirement. The K8s tests cover the requirements that need Debezium or EMQX:
  the entity store and MQTT notifications. The contract test reuses the light stack's startup rather than a
  copy of it.
- The sub-attribute scenario poisons the `v0.10` broker until it is restarted, so the contract test runs it
  last, on its own broker instance. The K8s tests don't run it.
- *Alternative:* everything in the K8s tests. Rejected: about an hour per run, and each check there is
  slower to write and to debug.
- *Alternative:* a fake broker. Rejected: the point is the real image's behaviour.

### D7 — One pinned image

- **Chosen:** the broker built from the commit `test/build-local-platform.sh` pins is the one every test of
  this contract runs against, because it is the one the K8s tests build and the next release ships. The
  contract test and the OPC UA chain test build it the same way, once per pinned commit, and keep the image
  in the Actions cache keyed by that commit, so a run that doesn't change the commit doesn't build Scorpio.
  The contract test runs when the pin, the broker's chart or the bridge's broker calls change.
- *Alternative:* the published release image (`.env` `DOCKER_TAG`), as the chain test does today.
  Rejected: since #1040 it is a different broker from the one the K8s tests run (`135b5ee` against
  `e1cea4bc`), so a test passing on it says nothing about the pinned build.
- *Alternative:* publish an image per pinned commit from the fork. Not chosen here: it needs a release
  pipeline on the fork; the cache gives the same result without one.

### D8 — DigitalTwin specifies and checks, the fork implements and unit-tests

- **Chosen:** this repository states the platform's expectations at the broker's interfaces and checks the
  pinned image with a thin black-box contract test: one check per scenario, through the API, the health
  checks and what the debezium bridge publishes, never the broker's code. The fork
  (IndustryFusion/ScorpioBroker) references the requirements: each patch names the one it serves, follows
  NGSI-LD (D1) and has its own unit test there.
- The contract test stays in this repository: only it sees failures between the broker and the platform's
  components, and moving the platform to a new image is decided here.
- *Alternative:* all broker tests in the fork. Rejected: the fork's tests run without the platform's
  components. *Alternative:* a copy of the contract test in the fork. Rejected: copies drift; the fork runs
  this one against its own build instead.

### D9 — The deviation register

Every deviation from NGSI-LD the platform knows is listed in the specification under one of three kinds.

**Accepted deviations** of the baseline, upstream 6.0.2. They stay until upstream fixes them or a patch is
worth carrying:

| Id | Deviation (clause) | Workaround | Converges by |
|---|---|---|---|
| A1 | a merge entity or batch merge of a typed value or language-tagged string fails with `22023` (3.1, 5.5.12) | the updates bridge writes such entities through `/attrs` (#1022) | the fork's patch for IndustryFusion/ScorpioBroker#8 (`e1cea4b`), in the pinned build since #1040 and carried on the update; reported upstream |
| A2 | a batch merge with `datasetId: "@none"` answers `404` (4.5.5) | the updates bridge removes `@none` | a fork patch (IndustryFusion/ScorpioBroker#11), reported upstream |
| A3 | a batch merge of one entity with a `null` value answers `404`, not a `207` with BadRequestData (6.31.3.1) | none needed once P2 is fixed | IndustryFusion/ScorpioBroker#12, a patch or an upstream report |

**Transitional deviations** of the broker built today, the fork on 5.0.5 at the pinned commit (`135b5ee`
and `e1cea4bc` alike). The move to the baseline
(IndustryFusion/ScorpioBroker#9) removes them, and their contract test fails as fixed then:

| Id | Deviation (clause) | Fixed by |
|---|---|---|
| T1 | a batch whose entities are all refused answers `400` (6.31.3.1) | the baseline |
| T2 | `errors` members are `id` and `ProblemDetails`, not `entityId` and `error` (5.2.17) | the baseline |
| T3 | upsert `options=update` keeps existing values (5.6.8, 5.6.2) | the baseline |
| T4 | two default instances of one attribute in one request are accepted (4.5.5) | the baseline |
| T5 | an entity id that isn't a URI answers `500`, not `400` | the baseline |
| T6 | a merge with a sub-attribute stops notifications (#969, 5.5.12) | the baseline (fixed since 6.0.0) |
| T7 | a subscription can't be read by its id, `403` (6.11.3.1) | the fork's access control patch, corrected on the update (IndustryFusion/ScorpioBroker#13) |
| T8 | a batch update with `options=noOverwrite` refuses an entity with nothing new with `404` `Not Overwriting` (6.16.3.1, 5.6.9) | the baseline (answers `204`); until then the updates bridge treats that refusal as success (#1049) |
| T9 | a batch update with `options=noOverwrite` doesn't append a new instance of an existing attribute (5.6.3) | the baseline |

T8 and T9 were found while fixing P3 (#1049), which moves the bridge's non-overwriting upsert to the batch
update with `options=noOverwrite`.

**Platform deviations** of the platform's own components. Each is fixed in a change of its own:

| Id | Deviation (clause) | Component | Change |
|---|---|---|---|
| P1 | a `207` is counted as success, its refusals are lost (6.31.3.1) | updates bridge | #1047; before the move to the baseline |
| P2 | a Property value of JSON `null` is written (4.5.0) | Core Services | #1048 |
| P3 | `overwriteOrReplace=false` is sent as an upsert with `options=update` and expected to keep values, relying on T3 (5.6.8) | updates bridge and its test | #1049; before the move to the baseline |
| P4 | IRI values are written as `{"@id": …}` in a Property, which isn't an NGSI-LD Value; the standard's form is a VocabProperty (3.1, 4.5.20) | Core Services, updates bridge, dataservice, model tools, shacl2flink | #1050, mid-term, a change of `contracts/opcua-live-data` |

Not a deviation: the refusal of a merge that changes an attribute's type (`SB001`) is Scorpio behaviour
the standard doesn't state; the platform relies on it (*The broker's own refusals*).

- *Alternative:* one list without kinds. Rejected: the kinds say who removes a deviation and when, which is
  what convergence needs.

### D10 — A declared type after a merge of a plain value

- **Chosen:** the merge patch of clause 5.5.12 goes "into JSON objects representing a Property value", so a
  plain value merged onto a declared one keeps the stored `@type`, as Scorpio does on every image. The
  specification states this as Scorpio's reading of the standard, and readers don't depend on either form
  (`contracts/typed-literals`).
- *Alternative:* call it a deviation. Rejected: the standard's deep merge supports it, and the opposite
  reading (a plain value replaces the value object) is just as possible; readers accept both.

## Conflicts with existing specifications

- `contracts/opcua-live-data`, *The chain is verified automatically*, ran the chain test "against the real
  broker image of the current release", which the chain test read as the published `v0.10`. Since #1040 the
  platform pins a different broker. The delta makes the chain test run against the pinned build (D7), and
  allows a run that builds it for a new pin to take longer than the 10 minutes of *Relevant change*.
- The same requirement listed "IRI values in a batch merge" among the known bugs the chain test must catch,
  and *Refused by the broker* expected that merge to be refused with `22023`. The pinned build carries the
  fork's patch for IndustryFusion/ScorpioBroker#8 (A1), so the broker accepts it and it is no longer a bug.
  The delta removes it from both; stage 4b asserts the merges of value objects as accepted. Refusals of a
  type change (`SB001`) stay; their form, `400` today, is the fork's transitional deviation T1.
- `contracts/opcua-live-data`, *Form of attributes in the broker*, makes enums IRIs in a Property, written
  as `{"@id": …}`. That is platform deviation P4. Alternatives:
  - **(chosen)** keep the rule for now, list P4, and change the OPC UA path to VocabProperty in a change of
    its own, mid-term;
  - change it in this change. Rejected: it touches five components and the SHACL shapes, far beyond a
    contract of the broker.
- `test/bats/test-bridges/test-ngsild-updates-bridge.bats`, *upserting and non-overwriting*, expects an
  upsert with `options=update` to keep existing values: it asserts T3, and with it P3. It stays until P3 is
  fixed, and must change with that fix.
- `contracts/typed-literals` names Scorpio and restates which forms it returns. The delta replaces the
  restatement by a reference; the rules don't change.

## Coverage

| Requirement | Test today | New in this change |
|---|---|---|
| NGSI-LD is the reference for the broker's API | review | every contract test check names its clause |
| Upstream Scorpio 6.0.2 is the baseline | none | the contract test run against 6.0.2 (`MODE=upstream`) |
| What the platform adds follows NGSI-LD | review | none |
| Deviations of the current image are transitional | none | contract test: each transitional deviation fails as fixed on 6.0.2 |
| Batch operation results | `stage4b.js` (`400` only) | contract test: all succeed, one of two refused, the only one refused |
| The platform reads batch results as the standard states them | none | with P1's fix |
| Merge keeps what it doesn't name | `test-scorpio-mergepatch.bats`, `test-ngsild-updates-bridge.bats` | contract test |
| Merge of typed and language-tagged values | `stage4b.js` on #1022 | contract test: both merge routes |
| Append attributes and upsert | `test-ngsild-updates-bridge.bats` | contract test |
| A non-overwriting update uses the standard's operation | `test-ngsild-updates-bridge.bats` (asserts T3) | with P3's fix |
| Value forms the broker stores | `stage4b.js` | contract test: every form |
| IRI values use the standard's form | `stage4b.js` (asserts P4) | with P4's change |
| Declared types in the broker | `literal.js` with `stage4b.js` | contract test: the three rows |
| Refusals the platform relies on | the shacl2flink e2e tests (207 from an upsert) | contract test: `null`, `observedAt`, two default instances, id |
| Core Services writes no null values | none | with P2's fix |
| The broker's own refusals | `stage4b.js` (SB001) | contract test |
| Default attribute instance | none | contract test |
| Reads | `stage4b.js`, `test-shacl-flink-scorpio-e2e.bats` (404) | contract test: both Accept forms, `406` |
| Subscriptions and notifications | `test-scorpio-mqtt-subscriptions.bats` (create, merge, no delete) | contract test over HTTP; K8s: batch merge over MQTT |
| A merge with a sub-attribute keeps notifications working | none | contract test, last and alone (D6) |
| Remote contexts | `test-shacl-flink-scorpio-e2e.bats` (published context) | contract test: read by short names |
| Requests need a token with a platform role | 401 without a token (`stage4a.sh`) | contract test: no role |
| Factory-Admin may do what the platform does | the chain test (realm role) | contract test: client and realm role |
| Factory-Reader only reads | none | contract test |
| The broker runs with the platform's configuration | the chain test's startup | contract test: health checks |
| Entity changes are published through the entity store | `test-debezium-bridge.bats` (create, delete, sub-attributes, geo) | K8s: JsonProperty, ListProperty, declared double |
| The entity store holds expanded JSON-LD | `test-shacl-flink-scorpio-e2e.bats` (typed numbers) | re-snapshot check on an existing store, with ScorpioBroker#9 |
| The broker's health reflects its notifications | the chart's probes | contract test: health checks up |
| What the platform doesn't rely on | review | none |
| The platform checks the broker image against this specification | none | the workflow trigger (D7) |
| The broker fork implements this specification | none | fork work (IndustryFusion/ScorpioBroker#9): patch list and unit tests |

This change adds test code only, so there is no product code whose coverage could be measured. The tests
themselves are measured by running each against `v0.10` and against the 6.0.2 image.

## Risks

- **The light stack has no Debezium.** Entity-store regressions are found only by the K8s tests.
- **Remote contexts need the network.** The contract test depends on the published IndustryFusion contexts
  being reachable from GitHub-hosted runners. Hosted e2e runs already depend on them.
- **The sub-attribute scenario** leaves a poisoned broker behind on `v0.10`. Running it last, on its own
  instance, contains that.
- **P1 and P3 gate the move to the baseline.** Moving before they are fixed loses refusals silently and
  changes what `overwriteOrReplace=false` does.

## Open Questions

1. Core Services writes `"value": null` (P2). Answered by the contract test: in a batch merge of two
   entities only the one with `null` is refused (`207`), the other is merged, on `v0.10` and on 6.0.2. A
   batch of that one entity alone answers `404` (A3). Decided for P2: a null value means that no value is
   known, so Core Services delivers nothing for it and the broker keeps the last known value, the rule
   `contracts/opcua-live-data` already states for the device path (*Only values are delivered*). A deletion
   (`urn:ngsi-ld:null`) would remove the attribute and raise count alerts; a JSON null literal would store a
   value no reader expects.
2. Does XanaAI need one notification per batch merge (the fork's `135b5ee`), or does it handle one per
   entity? The answer decides whether the fork update keeps the patch (D4).
3. Should the broker keep `scorpio.history.autorecording` on? Nothing reads the temporal tables, and they
   grow with every write. This is a question of chart configuration, not of this contract.
