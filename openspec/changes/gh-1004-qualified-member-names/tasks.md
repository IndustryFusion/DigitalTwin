# Tasks

## 1. opcua: member identity

- [x] 1.1 Match a child against the fixed-name members of the parent type's shape and of a declaration shape by its attribute name (namespace and name), and keep placeholders matched by pattern and type. Verified by unit tests: a member of the same namespace matches, one of another namespace does not, in a type shape and in a declaration shape, and a placeholder instance of another namespace matches.
- [x] 1.2 Take a variable's data type and value rank only from the declared variable reached through the same attribute name. Verified by unit tests: template found, no template for another namespace, template found for a namespace URI spelled with and without its trailing `/`.
- [x] 1.3 End to end, owl2instances to pyshacl: a new case with `0:Level` and `0:Link` on an `AlphaType` instance (the missing `hasLevel` and `hasLink` reported, the children kept under their own attributes, the namespace-0 placeholder instance accepted, `0:Level` generated as a scalar although `1:Level` is an array), and a new case with `0:Status` below `1:Link` (one violation through the declaration shape, `1:Level` generated as an array). Verified by the owl2instances suite with the expected shapes, instances and pyshacl results of both cases, and by the first case failing with the code before this change.
- [x] 1.4 Keep models whose browse names agree with their types unchanged. Verified by the full owl2instances suite with unchanged expected files for all existing cases, and by the example KMS packages (`make kms-packages kms-packages-check`).
- [x] 1.5 Document member identity in `semantic-model/opcua/README.md`. Verified by review against the documentation requirement.
- [x] 1.6 Measure the coverage of the changed code and keep the component gate. Verified by `pytest --cov` output (above 80 % for the changed modules), stated in the PR.

## Workflow follow-up

- Per-scenario verification list in the PR body (scenario → test), with the coverage numbers.
- After the merge: archive the change in a follow-up PR (`Closes #1004`).
