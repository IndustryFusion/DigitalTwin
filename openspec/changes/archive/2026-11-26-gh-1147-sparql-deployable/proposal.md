# Proposal

Issue: #1147

## Why

Validation (pyshacl) evaluates any SPARQL; the platform runs what shacl2flink
compiles to Flink SQL, which is less. Since #1108, shacl2flink compiles each
SPARQL expression to what it says and names every one it cannot compile, with
its reason and the pattern. The SemForge SPARQL editor still judges Flink with a
list of its own, written before #1108, and that list is now wrong both ways: it
warns about a named instance, a property path and an attribute no shape nests a
payload for, which all compile now, and it says nothing about `UNION`, `REGEX`
or `$this ?attribute ?value`, which do not. Such a query validates, its tests
pass, and the shapes fail only when shacl2flink builds them.

## What Changes

- **The compiler is asked.** While a SPARQL constraint or rule is edited,
  SemForge runs the query through shacl2flink's own check, in its process and
  without a build. A query that cannot be compiled is marked as an error
  `not-deployable` at the line of the pattern the compiler names, with the
  reason. A query that already has an error gets no second one, and a failure
  of the check never takes the other marks away.
- **The package is checked too.** The Problems panel (`SF-CAP-006`) and
  `semforge check` (`not-deployable`, exit 1) name every SPARQL constraint and
  rule of a package that cannot be deployed, with its shape, its message and
  the reason. `semforge export` refuses such a package, as it refuses every
  other capability error.
- **No compiler, no verdict.** shacl2flink is found at `SEMFORGE_SHACL2FLINK`,
  or else in a `shacl2flink` directory beside the package or beside SemForge.
  Where none is found, or it cannot be loaded, nothing is said: never that a
  query can be deployed.
- **SemForge's own claims about Flink go.** The findings `explicit-node`,
  `path` and `not-compiled`, their quick fixes, the command
  `semforge.nestForFlink`, and the hover line "shacl2flink would read it as a
  plain triple" are removed. The finding `variable-node` keeps what it says
  about the data and no longer says how shacl2flink reads it.

## Capabilities

### New Capabilities
- `semforge-sdk/sparql-deployable`: what SemForge says about whether a SPARQL
  constraint or rule can be deployed, in the editor, the Problems panel and the
  terminal, and that it says it only as shacl2flink's compiler does.

### Modified Capabilities

None. The findings and the command that are removed were never specified.

## Impact

- Components: `semantic-model/SemForge-SDK` (the language server's SPARQL
  diagnostics and hover, the capability check, `semforge check`, the VS Code
  extension's commands and README). shacl2flink is read, not changed.
- Contract between components: **no**. SemForge loads shacl2flink's query
  check from a checkout; that check is shacl2flink's own and keeps its
  behaviour (`shacl2flink/sparql-expressions`).
- No new dependency. The SDK's CI job installs the compiler's dependencies
  already (`requirements-crosscheck.txt`), so its tests run the real check.
- No image, chart or deployment changes.

## Out of Scope

- Changing what shacl2flink compiles, or its reasons (#1143, #1144, #1111).
- Quick fixes that rewrite a query until it compiles.
- Packaging shacl2flink so that SemForge can find it without a checkout.
