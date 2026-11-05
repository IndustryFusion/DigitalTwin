# Delta for Spec-Driven Workflow

## Purpose

Defines which changes to the IndustryFusion Process Data Twin need a specification
and how those changes move from a GitHub Issue through an OpenSpec change proposal,
maintainer approval, implementation and verification to an archived specification,
while staying traceable throughout.

## ADDED Requirements

### Requirement: Changes are classified
The contributor guide SHALL state which kinds of change need a specification. New features, behaviour visible to users or other components, and changes to contracts between components SHALL be specified before implementation. Research with an open outcome SHALL be explored first and specified from the result. Bug fixes, dependency updates, security fixes and chores SHALL NOT require a specification.

#### Scenario: Contract between components changes
- **WHEN** a change alters a message format, topic or attribute form used by more than one component
- **THEN** the change has an OpenSpec change proposal which is approved before implementation

#### Scenario: Dependency update
- **WHEN** a Pull Request only updates a dependency
- **THEN** it needs no OpenSpec change proposal and no `spec-approved` label

#### Scenario: Bug fix exposes a broken contract
- **WHEN** a bug fix reveals that a contract between components is broken or unwritten
- **THEN** the fix adds a scenario for that contract to the specifications

### Requirement: Existing components work without specifications
Components without specifications SHALL keep working and SHALL be built and tested as before. A capability SHALL get its first specification when a change that needs a specification touches it.

#### Scenario: Unspecified component
- **WHEN** a Pull Request changes a component which has no specification and the change needs none
- **THEN** no validation or review step requires a specification for that component

### Requirement: Change originates from a GitHub Issue
Every OpenSpec change SHALL reference exactly one originating GitHub Issue with an `Issue: #<number>` line in its `proposal.md`.

#### Scenario: Proposal references its issue
- **WHEN** a change proposal is created for GitHub Issue 42
- **THEN** its `proposal.md` contains the line `Issue: #42`

### Requirement: Stable change identifiers
Every change directory under `openspec/changes/` SHALL be named `gh-<issue>-<kebab-summary>`, where `<issue>` is the originating issue number and `<kebab-summary>` is a short description in kebab case.

#### Scenario: Change ID follows the convention
- **WHEN** a change is proposed for issue 42 about adding alert filtering
- **THEN** the change directory is `openspec/changes/gh-42-add-alert-filtering/`

### Requirement: Proposal completeness
A change proposal SHALL contain a proposal with motivation and out-of-scope items, delta specifications whose requirements each have at least one WHEN/THEN scenario, a design with architectural implications, and tasks which state how they are verified. A delta specification for a new capability SHALL include a `## Purpose` section.

#### Scenario: Complete proposal passes strict validation
- **WHEN** `openspec validate <change-id> --strict` runs on a complete proposal
- **THEN** validation succeeds

#### Scenario: Requirement without scenario is rejected
- **WHEN** a delta specification contains a requirement with no scenario
- **THEN** `openspec validate <change-id> --strict` fails

#### Scenario: New capability stays valid after archiving
- **WHEN** a change which adds a capability is archived
- **THEN** the new specification has the written purpose and `openspec validate --all --strict` still succeeds

### Requirement: Specification approval gates implementation
Implementation of a change that needs a specification SHALL start only after a maintainer has added the `spec-approved` label to the Pull Request that contains the change proposal. Any maintainer MAY add the label.

#### Scenario: Agent waits for approval
- **WHEN** an agent is asked to implement a change whose Pull Request lacks the `spec-approved` label
- **THEN** the agent does not modify source code and reports that specification approval is pending

#### Scenario: Agent implements after approval
- **WHEN** the Pull Request carries the `spec-approved` label
- **THEN** the agent implements the change's tasks in the same Pull Request

### Requirement: Approved requirements are authoritative
Implementation SHALL NOT change approved requirements. When implementation reveals that a requirement must change, the agent SHALL stop and propose the specification change for maintainer review.

#### Scenario: Conflict found during implementation
- **WHEN** an agent finds during implementation that an approved requirement cannot be met as written
- **THEN** the agent stops, describes the conflict, and edits the specification only after maintainer agreement

### Requirement: Pull Requests reference their change
Every Pull Request that proposes or implements an OpenSpec change SHALL name the change ID and reference the originating issue without a closing keyword.

#### Scenario: Pull Request links change and issue
- **WHEN** a Pull Request for change `gh-42-add-alert-filtering` is opened
- **THEN** its description names `gh-42-add-alert-filtering` and contains `Refs #42`, and no closing keyword for issue 42

#### Scenario: Implementation is merged
- **WHEN** the Pull Request implementing a change is merged
- **THEN** the originating issue stays open until the change is archived

### Requirement: Archiving closes the originating issue
The commit archiving the last open change of an issue SHALL contain a closing keyword for that issue in its message. An issue with another change that is still open or planned SHALL stay open. A change without a specification has no archive step, and its Pull Request MAY close its issue directly.

#### Scenario: Only change of an issue is archived
- **WHEN** the single change of issue 42 is archived and the commit reaches the default branch
- **THEN** the commit message contains `Closes #42` and issue 42 is closed

#### Scenario: Further change of the issue is open
- **WHEN** one of two changes of issue 42 is archived while the other is still open
- **THEN** the commit message contains no closing keyword for issue 42 and the issue stays open

#### Scenario: Agent is told about the rule
- **WHEN** an agent requests the archive instructions for a change with `openspec instructions archive --change <id>`
- **THEN** the output contains the rule for closing the issue

#### Scenario: Update of the generated files
- **WHEN** `openspec update` regenerates the skills
- **THEN** the rule for closing the issue is still in effect

#### Scenario: Change without a specification
- **WHEN** a Pull Request for a dependency update is merged and contains `Closes #42`
- **THEN** issue 42 is closed without an archive step

### Requirement: Automated artifact validation
Every Pull Request that modifies files under `openspec/` SHALL run `openspec validate --all --strict` in CI, and a validation failure SHALL fail the check. The validation SHALL NOT add to the runtime of any other workflow.

#### Scenario: Malformed change fails CI
- **WHEN** a Pull Request adds a delta specification with a scenario using three hashes instead of four
- **THEN** the OpenSpec validation check fails

#### Scenario: Unrelated change does not run the check
- **WHEN** a Pull Request modifies no files under `openspec/` and not the validation workflow
- **THEN** the OpenSpec validation check is not triggered

### Requirement: OpenSpec is not a dependency of the components
No component's build, image or deployment SHALL depend on OpenSpec.

#### Scenario: Build without OpenSpec
- **WHEN** the `Build` workflow runs on a machine without OpenSpec
- **THEN** it behaves as before this change

### Requirement: Archived history remains accessible
After a change is merged, it SHALL be archived with OpenSpec, which merges its delta specifications into `openspec/specs/` and keeps the proposal, design and tasks under `openspec/changes/archive/`.

#### Scenario: Archive preserves history
- **WHEN** a merged change is archived
- **THEN** its requirements appear in `openspec/specs/` and its original artifacts are found under `openspec/changes/archive/`

### Requirement: Discoverable agent instructions
The repository SHALL provide agent-independent instructions in `AGENTS.md` describing the lifecycle, and each supported agent SHALL be able to reach them from its native configuration.

#### Scenario: Claude Code discovers the workflow
- **WHEN** Claude Code starts in the repository
- **THEN** `CLAUDE.md` directs it to `AGENTS.md` and the OpenSpec `/opsx:*` commands are available

### Requirement: Only official files in agent directories
Only files generated by OpenSpec and officially maintained skills SHALL be tracked in agent-specific directories. Such a directory SHALL NOT be ignored as a whole.

#### Scenario: Local Claude Code settings
- **WHEN** a contributor has a `.claude/settings.local.json` in their checkout
- **THEN** `git status` does not list it, and the tracked OpenSpec files under `.claude/` stay tracked

### Requirement: Contributor guide states automation boundaries
The repository SHALL provide a contributor guide that explains each lifecycle step and states for each step whether it is automated or requires manual action.

#### Scenario: Contributor without local tooling
- **WHEN** a contributor without OpenSpec installed wants to propose a feature
- **THEN** the guide explains how to do so by opening a GitHub Issue only
