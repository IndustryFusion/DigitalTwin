# Contributing

The IndustryFusion Process Data Twin uses specification-driven development with
[OpenSpec](https://github.com/Fission-AI/OpenSpec) where it pays off: new behaviour and
contracts between components are specified and approved before they are implemented, and
stay traceable from their GitHub Issue to their Pull Request and archived specification.

## Which changes need a specification?

| Change | Process |
|---|---|
| New feature, or behaviour visible to users or other components | Specification first |
| Change to a contract between components, e.g. message formats, topics or attribute forms | Specification first |
| Research or spike with an open outcome | Explore first, then write the specification from the result |
| Bug fix | An issue is enough. Add a scenario if the bug exposes a broken contract between components |
| Dependency updates, security fixes, chores | An issue is enough |

Components without specifications keep working as before. A capability gets its first
specification when a change that needs one touches it. Nobody has to specify existing
behaviour up front.

A change without a specification is an ordinary Pull Request which closes its issue. The
rest of this guide is about changes with a specification.

## Lifecycle

| # | Step | Who | Automated? |
|---|---|---|---|
| 1 | Open a feature issue | Contributor | Manual |
| 2 | Create the OpenSpec change proposal | Agent, started by a maintainer | Agent-assisted |
| 3 | Review the specification | Maintainers | Manual |
| 4 | Approve: add the `spec-approved` label | Any maintainer | Manual |
| 5 | Plan and implement the tasks | Agent, started by a maintainer | Agent-assisted |
| 6 | Verify | CI + maintainers | Partly: CI validates artifacts and runs the tests; humans review behaviour |
| 7 | Merge | Maintainer | Manual |
| 8 | Archive the change, which closes the issue | Agent or maintainer | Agent-assisted (`/opsx:archive`) |

### 1. Propose a feature

Open an issue with the **Feature request** form. Describe the problem, the desired outcome
and, if you can, how to tell that it works. You do not need to write code or install
OpenSpec.

### 2. Create the change proposal

A maintainer asks a coding agent to create a proposal from the issue, for example in
Claude Code:

```
/opsx:propose Issue #42
```

The agent follows [AGENTS.md](AGENTS.md). It creates `openspec/changes/gh-42-<summary>/`
containing:

- `proposal.md`: why, what changes, out of scope; starts with `Issue: #42`
- `specs/<capability>/spec.md`: requirements, each with WHEN/THEN scenarios that serve as acceptance criteria
- `design.md`: architectural implications, decisions and alternatives
- `tasks.md`: implementation checklist, each task with its verification

The agent opens a Pull Request containing only the proposal. Capabilities are named
`contracts/<name>` for contracts between components and `<component>/<name>` for one
component.

### 3–4. Review and approve

Maintainers review the proposal in the Pull Request like any other document: inline
comments, requested changes, revisions (`/opsx:update`). When the specification is
accepted, any maintainer adds the **`spec-approved`** label to the Pull Request. Agents
must not implement before the label is present, and do not add it themselves.

### 5. Implement

A maintainer asks the agent to continue on the same Pull Request:

```
/opsx:apply gh-42-<summary>
```

The agent works through `tasks.md`, adds or updates tests, and keeps implementation
commits separate from specification commits. It must not change approved requirements; if
one cannot be met, it stops and the specification goes back to review.

### 6. Verify

- **Automated:** the `OpenSpec validate` workflow runs `openspec validate --all --strict`
  on every Pull Request touching `openspec/`. It checks the structure of artifacts, for
  example that every requirement has a scenario, not whether the code is correct. The
  `Build` and `K8s tests` workflows run as on any other Pull Request.
- **Human review:** maintainers check that each spec scenario is met, that tests cover
  them, and that security constraints hold. The Pull Request lists verification results
  per scenario.

### 7–8. Merge and archive

After merge, run `/opsx:archive gh-42-<summary>` (or `openspec archive`) in a follow-up
Pull Request. This merges the delta specs into `openspec/specs/`, which is the
authoritative description of the system, and moves the change to
`openspec/changes/archive/`, preserving its history.

### When the issue closes

The issue stays open until its last change is archived, so a forgotten archive stays
visible:

- Commits and Pull Requests which propose or implement a change use `Refs #42`, never a
  closing keyword.
- The commit archiving the issue's last change contains `Closes #42`.
- If another change for the issue is open or planned, the archive commit uses `Refs #42`.

## Conventions

- **Change ID:** `gh-<issue>-<kebab-summary>`.
- **Proposal:** `Issue: #<number>` as its first line.
- **Pull Request:** names the change ID and references the issue (template provided).
- **Licence header:** new source files start with the Apache-2.0 header of the
  IndustryFusion Foundation, in that file type's comment style.

## Working locally (optional)

Only maintainers or contributors driving an agent need OpenSpec locally, and no component
needs it to build or run:

```bash
npm install -g @fission-ai/openspec   # needs Node.js 22.12 or newer; or use a release binary
openspec list            # in-flight changes
openspec list --specs    # approved capabilities
openspec validate --all --strict
```

## Supported agents

All agents read [AGENTS.md](AGENTS.md). Claude Code is the starting point and has native
OpenSpec skills and `/opsx:*` commands in `.claude/`. To add native support for another
agent, run for example:

```bash
openspec init --tools cursor,github-copilot,codex
```

and commit the generated files. `openspec init --help` lists all tool IDs.

Only files generated by OpenSpec and officially maintained skills are tracked in these
directories. Do not edit generated files, because `openspec update` overwrites them;
project rules for an OpenSpec operation go into `operations` in `openspec/config.yaml`.
Keep personal skills outside the repository, in `~/.claude/skills/`.

## Current limitations

- Proposal creation, implementation and archiving are started manually by a maintainer; nothing runs automatically from issues.
- Who may add `spec-approved` is not enforced (`CODEOWNERS` and branch protection are open decisions).
- `Build` and `K8s tests` also run on specification-only Pull Requests, about 50 minutes each.
- The rule for closing the issue is advisory for agents and is not checked by CI. If an issue stays open by mistake, a maintainer closes it.
- CI checks artifact structure only. Functional correctness and security require human review.
