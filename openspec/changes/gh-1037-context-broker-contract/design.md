# Design

## Context

The platform deploys only Scorpio's all-in-one runner
(`helm/charts/scorpio`, image `ibn40/scorpio-all-in-one-runner:v0.10`, built
in CI from the fork commit `135b5ee`). No component uses Scorpio's temporal
API, tenants or Kafka topics. Data leaves the broker through Debezium on its
`public.entity` table, not through its API. The only runtime writer is the
updates bridge, which carries Core Services' writeback. XanaAI, outside this
repository, depends on its subscriptions.

### What the fork carries

The fork is upstream `5.0.5-java` plus four commits. None is in 6.0.1 or
6.0.2.

| Commit | Change | Requirement it serves |
|---|---|---|
| `67cdf1c` | Keycloak OIDC and role checks on every endpoint | *Requests need a token with a platform role*, *Factory-Admin may do what the platform does*, *Factory-Reader only reads* |
| `67cdf1c` | the chart's environment variables, `sslmode=require` | *The broker runs with the platform's configuration* |
| `67cdf1c` | `REPLICA IDENTITY FULL` on the entity table, edited into the migration `V20190604.1` (an update must add it as a new migration, or Flyway's checksum of `V20190604.1` breaks existing databases) | *Entity changes are published through the entity store* |
| `67cdf1c`, `a754fd8` | history managers out of the build, the at-context server back in | none (*What the platform doesn't rely on*) |
| `45e40a4` | image name | none |
| `135b5ee` | one notification for a whole batch merge, instead of one per entity | none: *Notifications of subscriptions* holds for both (D4) |

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

The 6.0.1 code agrees with these results: `merge_has_value` is unchanged
since `V20240801.1__mergepatchfix.sql`, so #967 is still there.
`V20250418.1__fixdeleteattrib.sql` (in 6.0.0) fixes the sub-attribute merge
(#969). 6.0.2 adds no migration.

## Decisions

### D1 — The contract states what the platform uses, not NGSI-LD conformance

- **Chosen:** each requirement is something a platform component does with
  the broker, named with that component. A separate requirement lists what
  the platform does not use, so that an update may change it freely.
- *Alternative:* specify the broker against ETSI GS CIM 009. Rejected: most of
  it is unused, and the spec would be far larger than what any test of ours
  can back (acceptance criterion 2).
- *Alternative:* specify Scorpio's implementation (its tables and
  functions). Rejected, with one exception: the entity store is specified by
  what the debezium bridge publishes, because the platform reads it, but not
  by column types or functions.

### D2 — A deviation states the target and the current behaviour

- **Chosen:** a requirement states the behaviour the platform wants. A
  *Known deviation* paragraph names the issue and the workaround, and the
  scenario adds "while the deviation stands" with today's answer. The test
  asserts today's answer and fails when the broker changes it, naming the
  workaround to remove.
- *Alternative:* specify only the target. Rejected: the tests would be red
  on the image the platform runs, and a red test that is expected teaches
  people to ignore it.
- *Alternative:* specify only today's behaviour. Rejected: it would make the
  bug the contract, and a fixed broker would "break" it.

### D3 — Refusals in a batch are found in `400` and in `207`

- **Chosen:** the contract requires a refusal to name the entity and its
  error, with `400` when every entity is refused and `207` when some are, and
  requires components to find it in either. The fork answers `400` and 6.0.x
  answers `207` for the same single-entity batch.
- *Alternative:* require `400`, as `contracts/opcua-live-data` says today.
  Rejected: 6.0.x follows the NGSI-LD batch result, and a patch that only
  changes a status code is a patch carried forever.
- **Consequence:** the updates bridge counts `207` as success
  (`KafkaBridge/lib/ngsildUpdates.js`), so on 6.0.x it would lose refusals
  silently, and the chain test would no longer see them as errors. This is a
  platform gap, named in the requirement, and its fix must land before the
  platform moves to 6.0.x. The modified *Form of attributes in the broker*
  refers to the contract instead of naming `400`.

### D4 — Notifications are specified per entity, not per message

- **Chosen:** every created or changed entity appears in a notification. How
  many notifications a batch produces is not specified. The fork's patch
  `135b5ee` (one notification per batch merge) serves no requirement, and the
  fork update may drop it.
- *Alternative:* require one notification per batch, as the fork does. Not
  chosen without evidence: the patch's commit gives no reason, and no
  consumer in this repository reads notifications. Open question 2 asks
  XanaAI.

### D5 — Only the roles the realm defines are part of the contract

- **Chosen:** `Factory-Admin` (everything the platform does) and
  `Factory-Reader` (reads only). The fork also names `Factory-Editor` and
  `Subscriber`, which the `iff` realm doesn't define. Nobody is given
  `Factory-Writer`, and it can create but not read, so it isn't relied on.
- *Alternative:* add the fork's other roles to the realm and specify them.
  Rejected for now: no component needs them. They can be added with a
  component that does.
- Roles are accepted as client roles of `scorpio` (real tokens) and as realm
  roles (the chain test's self-signed token); both were measured.

### D6 — Where the requirements are tested

- **Chosen:** a contract test on the light stack of `test/opcua-chain`
  (GitHub-hosted, the stack is up in about 15 s) for every API requirement.
  The K8s tests cover the requirements that need Debezium or EMQX: the entity
  store and MQTT notifications. The contract test reuses the light stack's
  startup rather than a copy of it.
- The sub-attribute scenario poisons the `v0.10` broker until it is
  restarted, so the contract test runs it last, on its own broker instance.
  The K8s tests don't run it.
- *Alternative:* everything in the K8s tests. Rejected: about an hour per
  run, and each check there is slower to write and to debug.
- *Alternative:* a fake broker. Rejected: the point is the real image's
  behaviour, and a fake would only restate this specification.

### D7 — One pinned image

- **Chosen:** the image the release deploys (`.env` `DOCKER_TAG`, built from
  the fork commit in `test/build-local-platform.sh`) is the one every test
  of this contract runs against. The OPC UA chain test already uses it. The K8s
  tests build it from the same commit. The contract test runs when either of
  the two changes, or when the broker's chart changes.

### D8 — DigitalTwin specifies and checks, the fork implements and unit-tests

- **Chosen:** this repository states the platform's expectations at the
  broker's interfaces and checks the pinned image with a thin black-box
  contract test: one check per scenario, through the API, the health checks
  and what the debezium bridge publishes, never the broker's code. The fork
  (IndustryFusion/ScorpioBroker) references the requirements: each patch
  names the one it serves and has its own unit test there. How the fork
  implements a requirement is not specified here.
- The contract test stays in this repository for two reasons. Only it can
  see failures between the broker and the platform's components, such as the
  updates bridge reading a `207`, or the stored row the debezium bridge
  parses. And moving the platform to a new image is decided here, so the gate
  belongs here.
- *Alternative:* all broker tests in the fork, with DigitalTwin keeping only
  the chain test and the K8s tests. Rejected: the fork's tests run without
  the platform's components, and the chain test covers only the values the
  OPC UA path writes.
- *Alternative:* duplicate the contract test in the fork. Rejected: two
  copies of the same checks drift. The fork can run this repository's
  contract test against its own build instead.

## Conflicts with existing specifications

- `contracts/opcua-live-data`, scenario *Refused by the broker*, says the
  broker answers `400` with `SB001` and `22023`. That holds for the fork and
  not for 6.0.x (D3). The delta makes the scenario refer to this contract.
  The chain test keeps asserting the current image's answer.
- `contracts/typed-literals` names Scorpio and restates which forms it
  returns. The delta replaces the restatement by a reference; the rules
  don't change.

## Coverage

| Requirement | Test today | New in this change |
|---|---|---|
| Requests need a token with a platform role | 401 without a token (`stage4a.sh`) | contract test: no role |
| Factory-Admin may do what the platform does | the chain test (realm role) | contract test: client and realm role, subscription by id |
| Factory-Reader only reads | none | contract test |
| The broker runs with the platform's configuration | the chain test's startup | contract test: health checks |
| Entity changes are published through the entity store | `test-debezium-bridge.bats` (create, delete, sub-attributes, geo) | K8s: JsonProperty and ListProperty in one entity |
| The entity store holds expanded JSON-LD | `test-shacl-flink-scorpio-e2e.bats` (typed numbers through the bridge) | re-snapshot check on an existing store, with ScorpioBroker#9 |
| Attribute writes of the platform | `stage4b.js` through the real bridge, `test-ngsild-updates-bridge.bats` | none |
| Value forms the broker accepts | `stage4b.js` | contract test: value objects through `/attrs`, language and vocabulary |
| Value objects are merged | `stage4b.js` on #1022 | contract test: every value object by both merge routes |
| A merge changes only what it names | `test-scorpio-mergepatch.bats`, `test-ngsild-updates-bridge.bats` | none |
| Declared types in the broker | `literal.js` with `stage4b.js` | contract test: the three rows |
| Refusals the platform relies on | `stage4b.js` (SB001), the shacl2flink e2e tests (207 from an upsert) | contract test: `null`, `observedAt` |
| Refusals in a batch are reported per entity | `stage4b.js` (`400` only) | contract test: one of two refused, the only one refused |
| Default dataset id in a batch merge | none | contract test |
| Reads | `stage4b.js`, `test-shacl-flink-scorpio-e2e.bats` (404) | contract test: both Accept forms |
| Notifications of subscriptions | `test-scorpio-mqtt-subscriptions.bats` (create, merge, no delete) | contract test over HTTP: batch create, batch merge, `/attrs`; K8s: batch merge over MQTT |
| The broker's health reflects its notifications | the chart's probes | contract test: health checks up |
| A merge with a sub-attribute keeps notifications working | none | contract test, last and alone (D6) |
| Remote contexts | `test-shacl-flink-scorpio-e2e.bats` (published context) | contract test: read by short names |
| What the platform doesn't rely on | review | none |
| The platform checks the broker image against this specification | none | the workflow trigger (D7) |
| The broker fork implements this specification | none | fork work (IndustryFusion/ScorpioBroker#9): patch list and unit tests |

This change adds test code only, so there is no product code whose coverage
could be measured. The tests themselves are measured by running each against
`v0.10` and against the 6.0.2 image (tasks 1.5 and 1.6).

## Risks

- **The light stack has no Debezium.** Entity-store regressions are found
  only by the K8s tests. Adding Debezium to the light stack is possible, but
  it is not needed for this contract.
- **Remote contexts need the network.** The contract test depends on the
  published IndustryFusion contexts being reachable from GitHub-hosted
  runners. Hosted e2e runs already depend on them.
- **The sub-attribute scenario** leaves a poisoned broker behind on `v0.10`.
  Running it last, on its own instance, contains that.

## Open Questions

1. Core Services writes `"value": null` (`sql_statements.sql`), and every
   measured broker refuses it, a batch merge with `404`. Does one `null`
   refuse the whole batch merge or only its entity? The contract test
   measures it. Fixing Core Services is its own issue.
2. Does XanaAI need one notification per batch merge (the fork's `135b5ee`),
   or does it handle one per entity? The answer decides whether the fork
   update keeps the patch (D4).
3. Should the broker keep `scorpio.history.autorecording` on? Nothing reads
   the temporal tables, and they grow with every write. This is a question of
   chart configuration, not of this contract.
