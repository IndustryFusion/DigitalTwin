## Purpose
Defines which tests a pull request, a push to `main` and the nightly run, where they run, and how the paths a pull request changes select the shards of the K8s end-to-end test.

## ADDED Requirements

### Requirement: Components build side by side
`Build` SHALL lint, test and build each component in a job of its own, and these jobs SHALL run side by side. No component's job SHALL depend on another component's job or on its output.

#### Scenario: One component fails
- **WHEN** the shacl2flink tests of a pull request fail
- **THEN** the shacl2flink job of `Build` fails, and the jobs of all other components still run to their end and report their own result

### Requirement: Tests without a cluster run outside the K8s test
Tests that need no cluster SHALL run in `Build`, not in a K8s end-to-end test: linting and shell-checking the bats suites, and the suites that run scripts from the helm templates against a mocked `kubectl`. A K8s end-to-end test SHALL NOT repeat a test that `Build` runs.

#### Scenario: A lint failure needs no platform
- **WHEN** a pull request adds a bats suite that fails the shell check
- **THEN** `Build` fails, and no platform was installed to find it

#### Scenario: No test runs twice
- **WHEN** `K8s tests` runs
- **THEN** it does not run the shacl2flink lint, unit tests or KMS tests, which `Build` runs

### Requirement: Pull requests run the K8s test in shards
The K8s end-to-end suites of a pull request SHALL run on GitHub-hosted runners, split into shards that run side by side. Each shard SHALL install the full platform on a runner of its own and run its own suites against it. Every suite SHALL belong to exactly one shard. A new push to the pull request SHALL cancel the runs of its older head. Adding a label other than `e2e-all` SHALL neither start nor cancel a run.

#### Scenario: Shards run side by side
- **WHEN** a pull request selects two shards
- **THEN** both run at the same time, each on its own GitHub-hosted runner with its own full install, and the self-hosted runner is not used

#### Scenario: A suite without a shard
- **WHEN** a pull request adds a suite directory that no shard lists
- **THEN** `Build` fails, so no suite can silently drop out of the pull request tests

#### Scenario: A new push
- **WHEN** a commit is pushed to a pull request while the shards of its previous head still run
- **THEN** those runs are cancelled and the shards of the new head run

#### Scenario: Another label
- **WHEN** a label other than `e2e-all`, such as `spec-approved`, is added to a pull request while its shards run
- **THEN** the shards keep running, and no new run starts

### Requirement: Changed paths select the shards
The paths a pull request changes SHALL select the shards it runs. A path that a shard's components, charts or suites are built from SHALL select that shard, a path every install depends on SHALL select every shard, and a path the cluster never runs SHALL select none. The label `e2e-all` SHALL select every shard.

#### Scenario: Agent change
- **WHEN** a pull request changes only files of the NGSI-LD agent
- **THEN** only the shard with the device connection suites runs

#### Scenario: Shared platform file
- **WHEN** a pull request changes the helmfile, the shared helm values or the platform install scripts
- **THEN** every shard runs

#### Scenario: Change the cluster never runs
- **WHEN** a pull request changes only the SemForge SDK, the OPC UA tools or documentation
- **THEN** no shard runs and no platform is installed

#### Scenario: Every shard on request
- **WHEN** a pull request that selects no shard carries the label `e2e-all`
- **THEN** every shard runs

### Requirement: The full K8s test
`K8s tests` SHALL run every suite on one full platform install on the self-hosted runner. It SHALL run in the nightly, when started by hand, and for a pull request with the label `e2e-full`. It SHALL NOT run for other pull requests or for pushes to `main`. Adding a label other than `e2e-full` SHALL neither start nor cancel it.

#### Scenario: Nightly
- **WHEN** the nightly runs
- **THEN** `K8s tests` runs every suite on the self-hosted runner, and images are pushed only if it passes

#### Scenario: Pull request without the label
- **WHEN** a pull request without the label `e2e-full` is opened or updated
- **THEN** `K8s tests` is skipped, and the K8s end-to-end shards its paths select run

#### Scenario: Pull request with the label
- **WHEN** the label `e2e-full` is added to a pull request
- **THEN** `K8s tests` runs every suite for it on the self-hosted runner

#### Scenario: Another label during the full run
- **WHEN** a label other than `e2e-full` is added to a pull request while its `K8s tests` run is in progress
- **THEN** that run keeps running, and no new run starts

#### Scenario: Push to main
- **WHEN** a pull request is merged into `main`
- **THEN** `Build` runs for the new `main`, and `K8s tests` does not
