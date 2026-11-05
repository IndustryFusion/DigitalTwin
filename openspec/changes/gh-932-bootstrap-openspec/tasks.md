# Tasks

## 1. OpenSpec configuration

- [ ] 1.1 Run `openspec init --tools claude` and commit the generated skills and commands unchanged; verify `.claude/commands/opsx/propose.md` and `.claude/skills/openspec-propose/SKILL.md` exist
- [ ] 1.2 Fill `openspec/config.yaml` with project context and artifact rules (issue reference, out of scope, testable scenarios, `## Purpose` for new capabilities, verification per task); verify the links in the context resolve
- [ ] 1.4 Add the rule for closing the issue to `operations.archive.guidance` in `openspec/config.yaml`; verify `openspec instructions archive --change gh-932-bootstrap-openspec` shows it, also after `openspec update`, and that the generated archive skill is unchanged
- [ ] 1.3 Add `.claude/.gitignore`; verify `git status` shows no `settings.local.json` and no `worktrees/`

## 2. Agent instructions

- [ ] 2.1 Write `AGENTS.md` covering the lifecycle, which changes need a specification, inspecting existing specs, conflict reporting, the `spec-approved` gate, not altering approved requirements, tests, verification, and `Refs #N` in Pull Requests with `Closes #N` in the last archive commit; verify each topic is present
- [ ] 2.2 Add `CLAUDE.md` pointing to `AGENTS.md`; verify the reference resolves

## 3. GitHub integration

- [ ] 3.1 Add `.github/workflows/openspec-validate.yml` running `openspec validate --all --strict` with a pinned, checksum-verified binary on Pull Requests touching `openspec/**` or the workflow; verify the check runs and passes on this Pull Request
- [ ] 3.2 Add `.github/ISSUE_TEMPLATE/feature.yml`; verify it parses as YAML and the existing templates are unchanged
- [ ] 3.3 Add `.github/pull_request_template.md` with change type, issue link, change ID and the automated-versus-human checklist, using `Refs #N` for changes with a specification and `Closes #N` otherwise; verify the fields are present

## 4. Contributor documentation

- [ ] 4.1 Write `CONTRIBUTING.md` with each lifecycle step, whether it is automated or manual, which changes need a specification, when an issue is closed, and current limitations; verify it covers proposing, approval, implementation, verification and archiving
- [ ] 4.2 Link `CONTRIBUTING.md` from `README.md`; verify the link resolves and no other existing file changed

## 5. Integration check

- [ ] 5.1 Run `openspec validate --all --strict` and `openspec status --change gh-932-bootstrap-openspec`; verify validation passes and all artifacts are complete
- [ ] 5.2 Confirm a requirement without a scenario fails strict validation (temporary, not committed)
- [ ] 5.3 Compare with `main`: only new files and the `README.md` link; verify `Build` and `K8s tests` are unchanged and pass

## Workflow follow-up

- After merge, run `/opsx:archive gh-932-bootstrap-openspec` in a follow-up Pull Request; verify `openspec/specs/spec-driven-workflow/spec.md` exists and `openspec validate --all --strict` passes. The archive commit message closes #932, as this is the issue's only change; verify the issue is closed once it reaches `main`.
