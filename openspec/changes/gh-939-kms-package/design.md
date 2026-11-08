# Design

## Context

The SemForge SDK (`semantic-model/SemForge-SDK`, `semforge/package/loader.py`
and `discover.py`) already reads a KMS as three roles, each one file or a
directory, with `semforge.yaml` as an optional descriptor and examples beside
the model. Nothing else in the repository knows this: shacl2flink, the
dataservice, kafka-bridges, the Fuseki upload and `test/bats` name the three
files directly, and shacl2flink's `Makefile` reads and writes
`semantic-model/kms` by path. This change writes the SDK's concept down as a
contract, narrows it where several independent implementations need one
answer, and adds an archive form, published versions and a directory of
packages.

A prototype of the package check, packing and verification ran the scenarios
against the real KMS before this proposal was written: the
directory and its archive gave the same digest, `sha256sum -c` accepted the
extracted archive, and `semforge validate` gave the same verdicts on both.

## Decisions

### D1 — The format is called KMS, and so is its descriptor

KMS stands for Knowledge, Model, Shapes, the three roles. SemForge is the SDK
that edits packages, not the format.

- **Chosen:** descriptor `kms.yaml` with `name`, `version` and `format`;
  archive `<name>-<version>.kms.zip`; tool state stays under `.semforge/`.
  Every setting `semforge.yaml` holds today (name, context, namespaces, entity
  root, NGSI-LD vocabulary) describes the package, so the file is renamed
  rather than split.
- *Alternative:* keep `semforge.yaml`. Rejected: every consumer would have to
  read a file named after one of the tools.
- *Alternative:* a generic name such as "semantic package". Rejected: KMS is
  already the name of the directory, the README and the convention.
- Package names: lowercase kebab-case (`opcua-pumps`) is the convention for
  new packages, not a rule; the contract allows the names it describes, and
  existing directories such as `SchweissenUndSchneiden/` keep theirs.
- The outside meaning of KMS (key management service) is a known clash. The
  README spells the term out.

### D2 — Canonical names, and two forms of one role is an error

The SDK accepts `main.jsonld`, `model.jsonld`, `main/`, bare documents in
`model/`, `shapes/` beside `shacl/`, and lets a file win over a directory.
With shacl2flink, the dataservice and the OPC UA tools each implementing the
contract, every alias is a place where two implementations can disagree.

- **Chosen:** one name per role (`knowledge`, `shacl`, `model-instance`, the
  names every consumer already uses), the `model/` grouping the SDK's scaffold
  writes, and two forms of one role make the package invalid.
- *Alternative:* adopt every SemForge alias. Rejected for the reason above.

### D3 — Integrity: `SHA256SUMS` inside the zip

- **Chosen:** a `SHA256SUMS` entry in the coreutils format, checkable without
  any project tool. Zip CRC-32 detects damage in transit, not deliberate change.
- *Alternative:* a JSON manifest with per-file hashes. Equally strong, but
  needs a tool to check.
- *Alternative:* a digest of the canonicalised RDF graphs (RDFC-1.0). Rejected
  for now: expensive, needs an RDF library in every consumer, does not cover
  YAML and README files. It remains a candidate for the semantic diff.

### D4 — The digest is over `SHA256SUMS`, not the zip bytes

Deflate output can differ between zlib builds, so a digest of the archive bytes
would depend on the packer's platform. `SHA256SUMS` depends only on member
paths and contents. Packing is still deterministic for one packer, so repeated
packs produce no spurious changes. The digest is what immutable versions,
future delta packages and dependencies, and a future signature refer to.

### D5 — Standalone

Packages are standalone by default (issue #939): every file a package needs
lies inside it. Deltas and dependencies, including `owl:imports` of remote
ontologies by URI, are planned and out of scope.

### D6 — Members are a fixed list, not what git tracks

Packing everything under the root would ship whatever happens to be there,
such as the derived `model-instance.scorpio.jsonld` and untracked notes. Using
git's view would make the verdict depend on the checkout; an unpacked archive
has no git at all.

- **Chosen:** a defined member list; everything else is reported when packing
  and left out.
- *Alternative:* an include/exclude list in the descriptor. Deferred: no
  package needs it yet, and a pattern language is a second contract.

### D7 — Verification before use, all or nothing

A consumer extracts into a fresh directory, checks every path before writing it
(zip slip), enforces a size limit (zip bomb), checks hashes, then checks the
tree as a package. Using part of a failed archive is forbidden, because
deploying half a package is worse than deploying none.

### D8 — Published versions are immutable, recorded in `.kms/releases.yaml`

- **Chosen:** `semforge publish` records version, digest and date in
  `.kms/releases.yaml`, committed with the package. Verification and packing
  fail when the current version is recorded with another digest; the editor
  warns on the first change and offers the three next versions. After a raise
  the package is a draft until published. The same rule as chart-testing's
  version-increment check on the helm charts in this repository, and as the
  immutability npm and Cargo registries enforce.
- The record cannot live in `kms.yaml`: it is a member, so recording the digest
  in it would change the digest. It is hidden, so it is not a member, and it is
  named after the format, not after SemForge.
- *Alternative:* git tags (`example/1.0.0`). Rejected: a package outside git
  (an archive, a generated OPC UA package) would lose its history.
- *Alternative:* a `-SNAPSHOT` suffix for drafts, as in Maven. Rejected: the
  record already tells a draft from a published version, without renaming.
- *Alternative:* derive the next version from the semantic diff. Planned as a
  follow-up; this change offers all three and lets the author decide.

### D9 — `semantic-model/kms` holds packages; `default` is a link

- **Chosen:** one subdirectory per package, named after it, and `default` as a
  relative symbolic link. Every consumer already understands a path, so
  pointing a Makefile at `kms/default` needs no new code.
- *Alternative:* a pointer file (`kms/packages.yaml` with `default: example`).
  Rejected: every consumer, including Makefiles, helm and bats, would need code
  to read it.
- A checkout without symbolic link support (Windows without `core.symlinks`)
  gets a text file instead of the link. Builds and CI run on Linux; the README
  says so.
- Today's KMS becomes `kms/example`. `SchweissenUndSchneiden/` stays a
  directory of examples, not a package, and is ignored.

### D10 — Only tested versions are published

A published version is what others deploy and build on, so it must carry proof
that its constraints work, not only that its files are intact.

- **Chosen:** `publish` requires every example to meet its expectations and the
  coverage to reach `tests.coverage` (default 80 %); the release record keeps
  the results; drafts are not gated; CI fails on a broken example always and on
  coverage only for published versions.
- **Coverage counts constraints that fire.** A constraint that no example makes
  fire cannot be told apart from one that is merely satisfied, so good examples
  alone do not cover it. This is what `semforge test --coverage` reports today,
  per shape, path and constraint component.
- *Alternative:* coverage per attribute (an attribute is covered when any of
  its constraints fires). Rejected: it hides untested constraints. It is
  tempting because the two-layer NGSI-LD encoding gives each attribute about
  seven constraints (cardinality and node kind on the attribute and on
  `hasValue`); `kms/example` covers 4 of its 117 constraints (3.4 %), mostly
  because of them. An earlier count of 5 of 99 came from `semforge test
  --coverage`, which counts only constraints some example evaluates and any
  firing, asserted or not.
- *Alternative:* require both a good and a bad example per constraint
  ("two-sided"). Stronger, deferred: firing is the part that is missing today.
- *Alternative:* gate packing too. Rejected: it would block sharing and
  deploying drafts while tests are written.
- *Alternative:* a fixed minimum. Rejected: a package may need a lower
  threshold for a while, and a declared one is visible in review and in the
  release record.

## Conflicts with existing documentation

- **C1 — SemForge aliases.** `SemForge-SDK/architecture.md` §6.1 says "a file
  wins when both are present", §6.2 documents `semforge.yaml`, and the scaffold
  writes `model/main.jsonld`. Under this contract all three are non-conforming.
  Resolution: the SDK keeps loading them, `verify`, `pack` and `publish` reject
  them, `init` writes the conforming names, and `architecture.md` points to the
  contract.
- **C2 — kms vocabulary.** `kms/semforge.yaml` declares
  `ngsild.source: ../ontology/ngsild.ttl`, outside the package. Resolution:
  copy the file into the package as `vocabulary/ngsild.ttl`; a test keeps the
  copy equal to `semantic-model/ontology/ngsild.ttl`, which stays the copy the
  SDK tests and other packages share. *Alternative:* the published URL with a
  pinned `sha256`, rejected because the published version lacks the terms the
  KMS uses.
- **C3 — Scorpio variant.** `kms/README.md` and shacl2flink's README describe
  `model-instance.scorpio.jsonld` as part of the KMS. It is not a member; it
  stays in the directory, and shacl2flink's adoption change replaces it with
  `semforge export --mode broker`.
- **C4 — kms is a package today.** The SDK's editor tests open
  `semantic-model/kms` as one package, and shacl2flink's `ontology2kms` target
  writes `knowledge.ttl` and `shacl.ttl` into it. Both move to `kms/default`
  or `kms/example`.

## Follow-up changes (one specification each)

1. shacl2flink, the dataservice, kafka-bridges, the Fuseki upload and
   `test/bats` read a package (directory or archive) and verify it.
2. OPC UA: `owl2kms.py` assembles a package from the output of
   `nodeset2owl.py` and `owl2instances.py`, checked with `semforge verify`.
3. SemForge suggests patch, minor or major from the semantic diff.
4. `kms/example` reaches 80 % coverage, so that it can be published; the
   SDK's commands for adding test cases make most of the missing firing cases
   mechanical.
5. Delta packages, dependencies (`owl:imports` by URI, packages by digest) and
   scoped names.
