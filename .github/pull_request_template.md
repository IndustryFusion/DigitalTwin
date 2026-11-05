## Summary

<!-- What this Pull Request does. -->

<!-- With an OpenSpec change: "Refs #<issue>", the archive commit closes the issue. Without one: "Closes #<issue>". -->
Issue: #<!-- issue number -->
OpenSpec change: <!-- `openspec/changes/gh-<issue>-<summary>/`, or "none" -->

## Type

- [ ] Change without a specification (bug fix, dependency update, security fix, chore)
- [ ] OpenSpec change: specification only (awaiting the `spec-approved` label)
- [ ] OpenSpec change: implementation (this Pull Request carries `spec-approved`)
- [ ] OpenSpec change: archive of a merged change

## Checked automatically (CI)

- [ ] `Build` and `K8s tests` pass (they don't run if only `openspec/` changed)
- [ ] `openspec validate --all --strict` passes, if `openspec/` changed

## Requires human review

- [ ] The change needs no specification, or the proposal reflects the issue and its out-of-scope items are acceptable
- [ ] Requirements are testable and architectural implications are stated
- [ ] Implementation does not change approved requirements
- [ ] Each spec scenario is verified (list results below)
- [ ] Tests added or updated where code changed

## Verification results

<!-- Per scenario: how it was verified and the result. Note any limitations. -->
