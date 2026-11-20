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
Three shards group the suite directories by the components they exercise: `device` (device connection, TimescaleDB bridge), `broker` (Scorpio, the bridges, Keycloak, Fuseki, the platform and operator checks) and `flink` (core SQL services plus shacl2flink's Flink end-to-end test). Each installs the full platform with `install-platform.sh -l -c all` and runs only its own suites. The self-hosted run installs the same releases offline (`-lo`, from the local registry the airgap preparation fills); the shards install online, pulling the external images, charts and operator manifests directly, so they also exercise the online install path while the nightly exercises the offline one.

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

### Labels
GitHub sends `labeled` for every label. Only a small dispatcher, `e2e-labels.yaml`, listens to it: it calls `K8s e2e` (as a reusable workflow) for `e2e-all` and `K8s tests` for `e2e-full`, and its jobs are skipped for any other label. So no other label starts or cancels a run of either K8s workflow, and none puts a skipped `changes`, `images` or `build` check next to the real one on the same head, where it would read as passing and could hide a failure. Pushes keep their per-pull-request concurrency group, which a run for `e2e-all` joins.

Alternatives: both K8s workflows listen to `labeled` and skip other labels (they still create skipped checks of the same names, and need a concurrency group per event to cancel nothing); no `labeled` trigger at all (adding `e2e-full` would do nothing until someone pushes).

### Build per component
`Build` gets one job per component: docker images, shacl2flink, dataservice, SemForge SDK, datamodel tools, OPC UA tools, iff-agent, plus `test-scripts` (bats lint, shellcheck, `test/bats-unit`) and `debezium-snapshot-memory`. The shacl2flink job installs sqlite3 with the PCRE extension through a script of its own. The SemForge SDK's optional SQLite cross-check needs that and shacl2flink's Python dependencies, which its environment doesn't install; it did not run before the split either, so its job needs neither.

A failed job opens a tmate shell only when asked for: the label `ci-debug` on the pull request, or the input `debug` of a manual run, for at most 30 minutes and only for the person who started the run. Before, every failed job waited for a connection until the job timed out, so a failure showed hours late. Alternative: no tmate at all; but a shell on the runner is the only way to look at some failures.

## Risks / Trade-offs

- [A cross-shard chain fails only in the nightly, e.g. device data through the core services into Scorpio] → the nightly runs every suite on one install; `e2e-full` or `e2e-all` on the pull request when in doubt.
- [Anonymous image pulls from Docker Hub on hosted runners hit its rate limit] → not seen in the trial; a mirror of the external images can follow.
- [Suites depended on running after another directory alphabetically] → the trial ran every shard green; a hidden order dependency would show as a shard failure.
- [Flaky suites stay flaky] → unchanged by this change; a failed shard can be rerun alone.
- [Startup checks that look once] → a GitHub-hosted runner starts the platform more slowly, so checks that looked once at something still starting failed there: the MQTT port-forward of the device suites, the task count of the shacl job, and the core services' tasks. Each now waits for its condition with a bound and still fails if it never holds; every shard waits for the Flink jobs to run all their tasks before its suites.
- [A Flink job submitted twice] → on a slow startup the core services' FlinkSessionJob ran as two Flink jobs, so every output arrived twice and the core SQL suites failed. The operator's log showed why: it submits the session job and waits with its Flink client timeout, 10 s by default; a session cluster that still starts answers later, the operator takes the submission as failed while it still runs, and the retry submits the job again. That is a platform defect on any slow cluster, so the operator now waits 120 s (`helm/flink-operator-values.yaml`, used by `install_operators.sh` online and offline), and newer operators' own submission timeout is set to its default explicitly. The wait step still fails at once, naming the job and printing the operator's log, if a job runs twice.

Measured in the fork trial (DrGarbitsch/DigitalTwin#1): every shard green with a full install, peak memory 10.6 of 16 GB, 73 GB disk left; images 12 min, shards 22–34 min, the K8s end-to-end result 48 min after the push; `Build` about 32 min, set by the OPC UA tools job.

## Migration Plan

Merging switches pull requests to the hosted shards. Rollback: restore the pull request trigger of `K8s tests`, or label a pull request `e2e-full` to get the full run.
