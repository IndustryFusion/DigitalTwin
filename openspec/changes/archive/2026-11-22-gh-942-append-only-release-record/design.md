# Design

## Context

`semforge verify` on a directory checks the package contract and, for the current version, that its digest is the one its release record lists. `make kms-check` in the SDK runs `semforge verify --tests` on every package in `semantic-model/kms`; the `semforge-sdk` job of `Build` runs it. The record is written only by `semforge publish`, which appends one entry per new version and never rewrites one. Nothing compares the record with an earlier state of itself.

Conflict with existing specs: none. *Published versions are immutable* is kept and now has something to stand on; *Every package in semantic-model/kms is verified and tested in CI* gains the comparison.

## Goals / Non-Goals

**Goals:**
- A pull request that removes or changes a published entry fails `Build` and names the version and the field.
- Publishing in the same pull request, which appends, passes.
- The check also runs locally with the same command.

**Non-Goals:**
- Making the record tamper-proof without git, e.g. by signing.

## Decisions

### D1: An option of `semforge verify`, not a script in the workflow

`semforge verify --against <git-ref>` reads the record at the ref with `git show <ref>:<path>` and compares it with the package's record. `make kms-check` passes it on, and the workflow only names the ref.

*Alternatives:*
- A shell or Python script in the workflow that diffs the two YAML files: the record's format and its parsing would live twice, and the check would not run locally the way CI runs it.
- A separate subcommand (`semforge releases check`): `verify` is already what `kms-check` and authors run; an extra command is one more step to forget.

### D2: Entries are matched by version, and every field counts

Each entry at the ref must still be in the package's record, under the same version, with every field equal: the digest, the date and the test results (examples, met, coverage, threshold), and any field a later format adds. Values are compared as parsed, type included: `met: 2` and `met: "2"` differ, while `6.70` and `6.7` are the same number. A field added to or dropped from an old entry is a change, also when its value is null. A version listed twice fails too, because which entry counts would depend on the reader. Entries after the ref's ones are free. Their order is not checked: reordering changes no published fact.

*Alternatives:*
- Require the ref's list to be a byte-identical prefix: a reformatted file (comments, quoting) would fail without anything published having changed.
- Compare only the digest: the date and the test results are the evidence the contract says the record holds, and they would then be rewritable.
- Compare values as text: `2` and `"2"` would pass, and a null field added or dropped would not show.

### D3: The base is the pull request's base branch, and only pull requests compare

The workflow fetches `github.base_ref` into the shallow checkout (`git fetch --depth=1`) and sets `KMS_AGAINST=origin/<base>`. Pushes to `main`, scheduled and manual runs set it empty and skip the comparison. The `kms-check` default is `origin/main`, so a local run compares with the branch a pull request would target.

*Alternatives:*
- Compare a push with `github.event.before`: `main` is protected and changes only through pull requests, which are compared already; a force push has no reliable `before`.
- Compare with the merge base instead of the base branch's tip: an entry published on `main` after the branch was cut would then be missing from the branch's record without failing, and the merge would bring it back anyway; comparing with the tip fails such a branch until it is rebased, which is what a release record wants.

### D4: Which earlier records a package is held to

- A package is identified by the `name` in its descriptor. The directory of packages it is in (`semantic-model/kms`) is listed once at the ref (`git ls-tree -r -z`, NUL-separated, so that a directory name outside ASCII is not quoted), and the package's earlier records are the record at its own path and the record of every package there that declares its name. Each is compared, and a problem found against another path names that path. So a package moved within `semantic-model/kms`, a package that takes a published name at a path with a record of its own, and a package moved onto a removed package's path are all held to the record of the name they carry; renamed in place, a package is still held to the record at its path.
- Two packages in the directory that declare the same name fail: the name would no longer say which package a record belongs to.
- A package renamed in its descriptor as well as moved is, by that definition, a new package.
- `kms/default` is a symbolic link, at the ref and now. The listing shows it as one entry, not as a directory with a descriptor, and the name check skips it, so it is never a second package of the same name.
- Only a path the listing does not show is absent. A record the listing shows but `git show` cannot read is a problem, not an absent record.
- A package whose name the ref does not have (new in the pull request, or generated and never committed like `opcua-*`), and with no record at its path there, has nothing to keep and passes.

*Alternatives:*
- Fail every package without a record at the ref: a package's first publication would then fail.
- Fall back to the name only when the path has no record: a package that takes a published name at a path with a record of its own (an empty one, say), or is moved onto a removed package's path, would be compared with that record only, and could list another digest under a published version.
- Treat a moved package as new and leave the move to reviewers: moving `kms/<pkg>` and rewriting its record in the same pull request would then pass.
- Look the name up in the whole tree at the ref: test fixtures and corpora elsewhere may declare the same names, so a package could match a copy that is not it; the directory of packages is where names are unique.
- Match by content (the digest of an entry) instead of the name: a rewritten digest is exactly what must be caught, so it cannot be the key.

### D5: What cannot be compared fails, except a package without history

- `.kms/releases.yaml` or `.kms` as a symbolic link fails, in the package and at the ref (mode `120000` in the listing). `git show` returns a link's target path, not the file behind it, so a record behind a link could be rewritten while its history shows an unchanged link: turn the record into a link in one pull request, rewrite the file behind it in the next. A linked `.kms` would make the record look absent at the ref.
- A record at the ref that does not parse fails. Passing it would open the same two-step escape: break the record in one pull request, rewrite it in the next. It can only be on the base branch if `Build` was bypassed; the pull request that repairs it then needs a maintainer to merge it over the failing check, which is the right person for such a repair.
- A descriptor at the ref that does not parse, of a package that has a record there, fails for the same reason: without its name, whether its record belongs to this package cannot be told.
- An archive has no history: `--against` refuses it (exit 2); its record, if given with `--record`, is taken as it is.
- A directory outside a git work tree, or a ref that is not a commit, fails: the comparison was asked for and cannot be made.
- A package deleted, or moved out of its directory of packages, together with its record is not looked for: `kms-check` sees only the packages in `semantic-model/kms`, and the contract leaves removing a whole package out of the append-only rule (proposal, Out of Scope).

*Alternatives:*
- Pass with a note when the record at the ref is a link or does not parse, so that a repair is not blocked: each is then the first step of an escape that the second step completes unseen.
- Follow a link at the ref to the file it names: the file behind it may itself be a link, or lie outside the package, and the record would still not be a member of the history it claims.
