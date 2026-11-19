# Design

## Context

`K8s tests` (`.github/workflows/k8s-tests.yaml`) runs on the self-hosted runner labelled `private`: it creates a k3d cluster, builds every image, installs the full platform from the local registry, runs `bats */*.bats` and then the shacl2flink tests, including the lint, unit and KMS tests `Build` already runs. The bats suites reach the platform through kubefwd, the ingress hostnames and Kubernetes secrets, and already support a GitHub-hosted runner: without `SELF_HOSTED_RUNNER` they call kubefwd and `/etc/hosts` through `sudo`. `Build` (`.github/workflows/build.yaml`) runs all components in one job.

**Conflict with an approved specification.** `spec-driven-workflow`, *Specification-only contributions run only the validation*, requires that every other push or Pull Request runs `Build` and `K8s tests` "as before", with the scenario *Pull Request with specification and code → `Build` and `K8s tests` run*. This change runs `K8s tests` only in the nightly, by hand and on request, so it modifies that requirement instead of contradicting it. The rest of the requirement stays: specification-only contributions trigger neither `Build` nor any K8s end-to-end test.

## Goals / Non-Goals

**Goals:**
- A pull request's K8s end-to-end result without the self-hosted runner, with the same suites against the same platform as today.
- The selection is a tested script, so the path rules can be read and checked without running CI.

**Non-Goals:**
- Fewer components per install (see Out of Scope in the proposal).

## Decisions

### Shards with a full install each
Three shards group the suite directories by the components they exercise: `device` (device connection, TimescaleDB bridge), `broker` (Scorpio, the bridges, Keycloak, Fuseki, the platform and operator checks) and `flink` (core SQL services plus shacl2flink's Flink end-to-end test). Each installs the full platform with the same `install-platform.sh -l -c all` as the self-hosted run and runs only its own suites.

Alternatives:
- *One hosted job with every suite:* no gain in wall time over the self-hosted run, only no queue.
- *Slim installs per shard* (helmfile `-l app=…`, which works with helmfile 0.149: unselected `needs` are skipped and the selected releases keep their order): less time and memory, but a shard then tests a platform nobody deploys; a later change once the shards are proven.
- *Docker Compose stacks without Kubernetes:* the suites depend on kubectl, kubefwd, Kubernetes service names and secrets, and the charts would not be tested.

### Path rules in one tested script
`.github/scripts/e2e-shards.sh` maps every changed path to shards (`select`), lists each shard's suites (`suites`) and its shards (`list`). The rules follow the platform: the agent selects `device`; the bridges every shard; Scorpio, Alerta and Fuseki `broker` and `flink`; the Flink components and shacl2flink `flink`; the helmfile, shared values, the foundation charts (postgres, kafka, keycloak, seaweedfs, cert-manager), Keycloak and the install scripts every shard; everything else none. Its bats tests run in `Build` and check that every suite directory belongs to exactly one shard.

Alternatives: `paths:` filters per workflow can't be combined with a label and would duplicate the suite lists in YAML; a third-party paths-filter action adds a dependency for what a short script does.

### Images built once
An `images` job builds every image once (`build-local-platform.sh`, including Scorpio's Maven build), saves them as one zstd archive (`test/platform-images.sh`) and hands it to the shards as a workflow artifact kept for one day; each shard loads it into its local registry. A registry the shards could share is not available: pull requests come from forks, whose token cannot push packages.

Alternatives: every shard builds its own images. In the fork trial a slow Ubuntu mirror stretched that build to 34–57 minutes in each of three shards (the `flink-sql-gateway` image installs build tools with `apt`); built once, it delays one job.

### Runner preparation
`test/prepare-platform-for-github-runner.sh` installs the tools without prompting, removes preinstalled toolchains the test never uses (the platform images are stored twice, in the registry and in the nodes), and creates the k3d cluster with two agents like the self-hosted runner. Every k3d node advertises the host's CPUs; on a single node the summed CPU requests left velero unschedulable. `prepare-platform.sh` can't be used: it reinstalls Docker and runs `apt install` without `-y`.

`helm/install_operators.sh` waited for cert-manager with `kubectl wait`'s default of 30 seconds. With no image cached, the pods were still pulling after 37 seconds and the install failed, so it waits up to 5 minutes.

### The full run stays on the self-hosted runner
`K8s tests` keeps its steps and runs from the nightly (`workflow_call`), by hand (`workflow_dispatch`) and for a pull request labelled `e2e-full`; it no longer runs on pushes to `main`, which the nightly covers. The label `e2e-all` runs every hosted shard instead.

### Labels and concurrency
Both workflows start on `labeled` to react to `e2e-all` and `e2e-full`, but GitHub sends that event for every label, and a workflow's concurrency group cancels the run in progress before any job condition is evaluated. So a `labeled` event for any other label gets a concurrency group of its own (the run's ID), which cancels nothing, and its jobs are skipped; only pushes and the workflow's own label share the per-pull-request group that cancels the older run.

Alternative: no `labeled` trigger, labels read only on the next push. Simpler, but adding `e2e-full` would do nothing until someone pushes.

### Build per component
`Build` gets one job per component: docker images, shacl2flink, dataservice, SemForge SDK, datamodel tools, OPC UA tools, iff-agent, plus `test-scripts` (bats lint, shellcheck, `test/bats-unit`) and `debezium-snapshot-memory`. The sqlite3 PCRE extension, which the SemForge SDK's SQLite cross-check found only because it ran after shacl2flink in the same job, is installed by a shared script in both jobs.

## Risks / Trade-offs

- [A cross-shard chain fails only in the nightly, e.g. device data through the core services into Scorpio] → the nightly runs every suite on one install; `e2e-full` or `e2e-all` on the pull request when in doubt.
- [Anonymous image pulls from Docker Hub on hosted runners hit its rate limit] → not seen in the trial; a mirror of the external images can follow.
- [Suites depended on running after another directory alphabetically] → the trial ran every shard green; a hidden order dependency would show as a shard failure.
- [Flaky suites stay flaky] → unchanged by this change; a failed shard can be rerun alone.

Measured in the fork trial (DrGarbitsch/DigitalTwin#1): every shard green with a full install, peak memory 10.6 of 16 GB, 73 GB disk left; images 12 min, shards 22–34 min, the K8s end-to-end result 48 min after the push; `Build` about 32 min, set by the OPC UA tools job.

## Migration Plan

Merging switches pull requests to the hosted shards. Rollback: restore the pull request trigger of `K8s tests`, or label a pull request `e2e-full` to get the full run.
