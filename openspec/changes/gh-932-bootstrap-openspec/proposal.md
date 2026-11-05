# Proposal

Issue: #932

## Why

Contributors should be able to propose changes as GitHub Issues while AI coding
agents refine specifications, plan, implement and verify under maintainer
governance. Today this repository has no specification workflow, no agent
instructions and no contributor guide, so requirements and the contracts between
components are not written down anywhere an agent or a reviewer could check them
against.

## What Changes

- Initialize OpenSpec (default `spec-driven` schema) with `openspec/specs/` as
  the authoritative specification location and `openspec/changes/` for change
  proposals.
- Add project context and artifact rules in `openspec/config.yaml`, linking the
  existing documentation.
- Add agent-independent instructions (`AGENTS.md`) and a pointer for Claude Code
  (`CLAUDE.md`); commit the native OpenSpec skills and commands generated for
  Claude Code.
- Define the lifecycle Issue → Proposal → Spec review → Implementation plan →
  Implementation → Verification → Merge → Archive, with a `spec-approved` label
  gating implementation.
- Define which kinds of change need a specification. Features, behaviour visible
  to users or other components, and contracts between components do; dependency
  updates, security fixes and chores do not.
- Define traceability: change IDs `gh-<issue>-<kebab-summary>` and an
  `Issue: #N` line in every proposal.
- Keep an issue open until its change is archived: Pull Requests reference the
  issue without closing it, and the commit archiving the issue's last change
  closes it.
- Add a workflow validating OpenSpec artifacts, a feature issue form, a pull
  request template and a contributor guide.

## Capabilities

### New Capabilities
- `spec-driven-workflow`: How changes to this repository are classified,
  proposed, specified, approved, implemented, verified and archived, and how they
  stay traceable to GitHub Issues and Pull Requests.

### Modified Capabilities

None.

## Impact

- New files only: `openspec/`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`,
  `.claude/`, `.github/`. `README.md` gains a link to the contributor guide.
- No component's build, image or deployment changes. The new workflow downloads
  a pinned, checksum-verified OpenSpec binary and runs only when `openspec/**`
  or the workflow itself changes.
- The `Build` and `K8s tests` workflows stay as they are, so they also run on
  specification-only Pull Requests.
- A new `spec-approved` label on the repository.

## Out of Scope

- Autonomous issue-to-merge execution and multi-agent orchestration.
- Custom agent frameworks or orchestration servers.
- Automatic approval of specifications or architectural changes.
- Enforcing who may add the `spec-approved` label (`CODEOWNERS`, branch
  protection); this needs repository admin settings and is documented as a
  limitation.
- Requiring a specification for every change.
- Specifying the behaviour of existing components up front.
- Any change to application behaviour or to existing CI workflows.
