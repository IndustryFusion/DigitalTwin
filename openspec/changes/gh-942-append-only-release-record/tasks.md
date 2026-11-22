# Tasks

## 1. The comparison

- [ ] 1.1 Compare two release records: every entry of the earlier one present under its version with every field unchanged, each version listed once, appending free (D2); verify with unit tests in `semantic-model/SemForge-SDK/tests/unit/test_kms_record_history.py` ("Removed entry", "Changed entry", "Appended entry")
- [ ] 1.2 `semforge verify --against REF` reads the record at `REF` from the package's git repository, also through the `kms/default` link, and reports the result in text and JSON (D1, D4); verify with the CLI tests of the same file ("Unchanged record", "Changed date", "No record at the ref", "Archive", "Unknown ref", "Package new in the pull request"), and with a test that publishing a second version passes
- [ ] 1.3 When the ref has no record at the package's path, compare with the record of the package of the same name in the same directory of packages at the ref, naming its path there; the `kms/default` link is not a package; a descriptor there that does not parse is listed in the note (D4); verify with the tests of the same file ("Moved with a rewritten record", "Moved with its record intact", "Renamed and moved", "Default link", "Moved package")

## 2. CI

- [ ] 2.1 `make kms-check` passes `--against "$(KMS_AGAINST)"` (default `origin/main`, empty skips); verify with the tests of `make kms-check` in the same file: a removed entry fails, an append passes, an empty `KMS_AGAINST` skips the comparison
- [ ] 2.2 The `semforge-sdk` job of `Build` fetches the pull request's base branch and sets `KMS_AGAINST` to it, and leaves it empty for other events (D3); verify with `test/bats-unit/build-workflow.bats`, and on this pull request's `Build` log, whose `kms-check` prints a `history` line for every package ("Rewritten release record on a pull request" by the unit tests of 1.1/1.2)

## 3. Documentation and checks

- [ ] 3.1 `semantic-model/kms/README.md` and the SDK README describe the append-only record, the local command, and what applies to packages without history (D4); verify by reading
- [ ] 3.2 Run the SDK's lint and unit tests as the `semforge-sdk` job does, `bats test/bats-unit`, and `openspec validate --all --strict`; verify all pass
