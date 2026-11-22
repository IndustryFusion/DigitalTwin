Issue: #942

## Why

A KMS package's release record `.kms/releases.yaml` lists every published version with its package digest, and the rule "the same name and version always mean the same digest" is checked against it. The record itself is not protected: deleting a version's entry, or rewriting its digest, lets a changed published version pass `semforge verify` and the `kms-check` step of the `Build` workflow. Today the rule holds only as far as a reviewer notices the edit (review of #940, finding 5). The record cannot protect itself: it is not a member, because a digest inside a member would change the digest, so the protection has to come from the record's history.

## What Changes

- The release record becomes append-only: an entry, once on the base branch, can be neither removed nor changed.
- `semforge verify --against <git-ref> <package directory>` compares the package's record with the record at that ref in the package's git repository. Removing an entry, changing any of its fields (digest, date, examples, met, coverage, threshold; values with their types) or listing a version twice fails with exit code 2 and names the version and the field. Appending passes.
- A package is identified by the name in its `kms.yaml`: it is compared with the record at its path at the ref and with the record of every package that declares its name in the same directory of packages there, so moving a package, taking a published name, or moving onto a removed package's path does not escape the rule. Two packages declaring one name fail. Only a name the ref does not have (a new package, or one renamed as well as moved) with no record at its path has nothing to keep.
- What cannot be compared fails: a record or `.kms` that is a symbolic link, in the package or at the ref, and a record at the ref that does not parse or cannot be read.
- `make kms-check` passes `--against` on for every package, from `KMS_AGAINST` (default `origin/main`; empty skips the comparison). The `Build` workflow fetches the pull request's base branch and sets `KMS_AGAINST` to it; other events skip the comparison.
- The documentation says what applies to packages without history.

## Capabilities

### New Capabilities

### Modified Capabilities
- `contracts/kms-package`: new requirements **The release record is append-only**, **The release record has a history to compare with** and **A package is identified by its name**; modified requirement **Every package in semantic-model/kms is verified and tested in CI** (the record is compared with the base branch).
- `semforge-sdk/package-tools`: new requirement **Verify the release record against its history**.

## Out of Scope

- Signing releases.
- Where published archives are stored.
- Removing a package, or moving it out of its directory of packages, together with its record: the pull request's diff shows a deleted package, and whether a published package may be withdrawn is a separate decision. The contract's append-only requirement states this exception.
- Comparing on pushes to `main` and in scheduled runs; `main` only changes through pull requests.

## Impact

- Components: SemForge SDK (`semforge verify`, the release record module, the `kms-check` target), the `semforge-sdk` job of the `Build` workflow, and the KMS documentation in `semantic-model/kms/README.md`.
- Contract: `contracts/kms-package` gains the append-only rule. The record format does not change; existing records stay valid, and `semforge publish` already only appends.
