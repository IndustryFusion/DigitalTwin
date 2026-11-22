# Proposal

Issue: #1037

## Why

The platform runs Scorpio built from the IndustryFusion fork at `135b5ee`
(`test/build-local-platform.sh`, published as
`ibn40/scorpio-all-in-one-runner:v0.10`), four commits on top of upstream
5.0.5. Upstream is at 6.0.1 (tagged) and 6.0.2 (released in July 2026, not
tagged). What the platform relies on from the broker is spread over code,
workarounds and tests:

- `contracts/opcua-live-data` names the broker's refusals (`SB001`, `22023`)
  as `400`, the fork's answer; NGSI-LD and 6.0.2 report them in a `207`,
  which the updates bridge counts as success;
- `contracts/typed-literals` relies on the broker keeping a declared
  `@type`;
- the updates bridge sends IRI values and, with #1022, declared values
  through `/attrs`, because a merge refuses them with `22023` (#967); this is
  unchanged on 6.0.2;
- the debezium bridge reads Scorpio's database row, not its API, so a change
  of the stored form breaks the whole data path without any API test
  noticing.

None of the fork's patches is upstream: authorisation by Keycloak roles, the
platform's configuration variables, Postgres over TLS, the full row image for
change data capture, and one notification per batch merge. Without one place
that states what the platform needs, a patch can't say which requirement it
serves, and the update to the latest upstream release
(IndustryFusion/ScorpioBroker#9) has nothing to be checked against.

## What Changes

- **A contract for the context broker** (`contracts/context-broker`) on one
  rule (design, D1): NGSI-LD, ETSI GS CIM 009 V1.9.1, is the reference for
  every NGSI-LD behaviour the platform uses; upstream Scorpio 6.0.2 is the
  baseline, whose deviations are accepted and worked around; what the
  platform adds itself, fork patches and its own components, follows the
  standard unless that would destroy scalability or performance. So the
  platform converges towards a standard compliant API. The contract states:
  - for each NGSI-LD operation the platform uses, the standard's behaviour
    with its clause: batch results, merge, append and upsert, value forms,
    refusals, the default instance, reads, notifications, remote contexts;
  - every known deviation in a register of three kinds (design, D9):
    *accepted* deviations of 6.0.2, *transitional* deviations of today's
    image that the move to 6.0.2 removes, and *platform* deviations of the
    platform's own components, each with its workaround or the change that
    removes it, and a scenario that fails when it is fixed;
  - the platform requirements outside NGSI-LD: access by token and role, the
    configuration the chart passes, the entity store as read by change data
    capture, and health;
  - what the platform does **not** rely on, so that an update may change it.
- **Who does what:** this repository specifies the expectations and checks
  the pinned broker image with a thin black-box contract test. The broker
  fork references the requirements, names the one each patch serves, and
  tests its patches with its own unit tests (design, D8).
- **Verification:** every requirement is tested against the broker image the
  release deploys. The contract test on the GitHub-hosted light stack covers
  the API requirements, one check per scenario; the K8s tests cover change
  data capture and MQTT notifications. The OPC UA chain test and the K8s tests
  use the same image.
- **References instead of restatements:** `contracts/opcua-live-data` and
  `contracts/typed-literals` refer to the new contract where they state
  broker behaviour. No rule of theirs changes.
- `AGENTS.md` points to the contract for changes to the broker or its image.

## Capabilities

### New Capabilities
- `contracts/context-broker`: what the platform requires from its NGSI-LD
  context broker, and how a broker build is checked against it.

### Modified Capabilities
- `contracts/opcua-live-data`: *Form of attributes in the broker* refers to
  `contracts/context-broker` for the refusals.
- `contracts/typed-literals`: *Documents passed on keep their declared types*
  and *Readers of the NGSI-LD API accept declared values* refer to it for the
  forms the broker stores and returns.

## Impact

- Contract between components: **yes**, a new one. It concerns the broker
  and its chart (`helm/charts/scorpio`, `helm/charts/keycloak`), the updates
  and debezium bridges (`KafkaBridge`), Core Services, the OPC UA chain test
  (`test/opcua-chain`), the K8s tests (`test/bats`,
  `semantic-model/shacl2flink/tests/bats`) and XanaAI as a subscriber.
- New test code only: a contract test on the light stack and K8s test cases
  for the scenarios not yet covered (design, *Coverage*). No change to
  component code, images or charts.
- `AGENTS.md`: one line.
- IndustryFusion/ScorpioBroker#9 and #8 implement the fork update against this
  contract; the fork carries its own unit tests.

## Out of Scope

- Changing the broker. The fork update (IndustryFusion/ScorpioBroker#9), the
  merge of value objects (IndustryFusion/ScorpioBroker#8) and the defect of
  the subscription read by id are fork work.
- Fixing the platform deviations this contract names (design, D9): the
  updates bridge counting `207` as success (P1), Core Services writing `null`
  values (P2), the bridge's non-overwriting upsert (P3), and IRI values as
  `{"@id": …}` (P4). Each needs its own issue; P1 and P3 must land before the
  platform moves to 6.0.x.
- Moving the platform to a new broker image; that follows the fork update,
  once these tests pass with it.
- End-to-end tests the fork update needs beyond this contract: a separate
  DigitalTwin issue, if the update finds any.
- NGSI-LD conformance in general: only what the platform uses is specified,
  but that part is specified as the standard states it.
