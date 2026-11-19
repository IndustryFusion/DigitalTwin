## MODIFIED Requirements

### Requirement: Specification-only contributions run only the validation
A push or Pull Request that changes only files under `openspec/` SHALL NOT trigger `Build` or any K8s end-to-end test. Every other push or Pull Request SHALL run `Build`, a Pull Request SHALL also run the K8s end-to-end shards its changed paths select, and the nightly SHALL run `Build` and `K8s tests` regardless of which files changed.

#### Scenario: Specification-only Pull Request
- **WHEN** a Pull Request changes only files under `openspec/`
- **THEN** the OpenSpec validation check runs, and neither `Build` nor any K8s end-to-end test is triggered

#### Scenario: Pull Request with specification and code
- **WHEN** a Pull Request changes files under `openspec/` and at least one other file
- **THEN** `Build` runs, and the K8s end-to-end shards that the other files select run

#### Scenario: Nightly run
- **WHEN** the nightly workflow calls `Build` and `K8s tests`
- **THEN** they run regardless of which files changed
