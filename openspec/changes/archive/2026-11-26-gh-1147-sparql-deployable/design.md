# Design

## Context

SemForge's SPARQL editor (`semforge/sparql/ngsild.py`) checks how a query reads
NGSI-LD attributes. Some of its findings are about the data (a query that takes
one step where the data has two matches nothing); three were about Flink only:
`explicit-node` (a named attribute instance), `path` (a property path) and
`not-compiled` (an attribute no shape nests a payload for), with a quick fix that
added such a shape (`semforge.nestForFlink`). #1108 made shacl2flink compile the
first two and recognise an attribute by the pattern that reads it, and added
`lib/query_check.py`: every `sh:select` and `sh:construct` of a shapes graph, or
one draft query, goes through the translation a build uses, and each that fails
is a problem with shape, target, kind, message, reason, pattern, query, file and
line.

## Goals / Non-Goals

**Goals:** say, while a query is written and for a whole package, what shacl2flink
cannot compile, in shacl2flink's words; remove what SemForge says about Flink of
its own.

**Non-Goals:** change the compiler; offer rewrites; ship shacl2flink with SemForge.

## Decisions

### D1. Ask the compiler, in process

SemForge imports shacl2flink's `lib.query_check` from a checkout and calls it on
the package's shapes graph, or on a draft query, as `sh:select` for a constraint
and `sh:construct` for a rule, once per target class of the shape (the build
compiles an expression once per target class, `$this` typed by it); the first
refusal is shown. That is the translation a build runs, so the answer cannot
drift.

Alternatives:
- *Keep SemForge's own list, updated to #1108.* Rejected: it drifted once and
  would again with every form shacl2flink learns (e.g. #1111, #1143).
- *Run `check_queries.py` as a subprocess.* Rejected for the editor: a process and
  a package load per keystroke pause; in process the shapes graph SemForge holds
  already is used.
- *Depend on shacl2flink as a package.* Not possible: it is not packaged, and the
  SDK should not carry a compiler's dependencies for a check (the same reason as
  the SQLite cross-check, `requirements-crosscheck.txt`).

### D2. Where the compiler is found, and silence without it

`SEMFORGE_SHACL2FLINK` names the checkout; when it is set and is no directory,
there is none. Otherwise the first `shacl2flink` directory with
`lib/query_check.py` up from the package, then up from SemForge's own files, is
used: in this repository both find `semantic-model/shacl2flink`. A checkout that
cannot be imported (a dependency missing) counts as none. Without one nothing is
said, neither "cannot" nor "can": silence is honest, a "can be deployed" without
the compiler would not be.

Alternative: a setting of the extension. Rejected for now: the variable serves the
language server, the CLI and CI alike; a setting can be added later.

### D3. The compiler's modules are kept apart

shacl2flink's modules are a package named `lib`. SemForge removes any `lib*`
modules from `sys.modules` before the import, imports with the checkout first on
`sys.path`, and afterwards removes the checkout from `sys.path` and its `lib*`
modules from `sys.modules`, restoring what was there. The loaded module is kept
per checkout, so later calls do not import again.

Alternative: a subprocess or a separate interpreter (rejected in D1); renaming
shacl2flink's package (out of scope, and it breaks its build).

### D4. One mark, at the line the compiler names

In the editor the mark is added only when the query has no error yet (a query
that does not parse, or one SemForge refuses already, needs no second opinion).
It is put on the line of the query body that holds the most names (variables,
prefixed names, IRIs) of the pattern the compiler names, or of the reason when no
pattern is named. Any exception of the check gives no mark, never an error of the
diagnostics request.

Alternatives: the whole query (rejected: says nothing about where); parsing the
compiler's pattern back into a position (rejected: the pattern is the compiler's
rendering, not the text).

### D5. Package-wide in the capability check and `semforge check`

Each problem of the package is a capability error `SF-CAP-006` on its shape, so it
is in the Problems panel and `semforge export` refuses the package like for any
other capability error. `semforge check` lists it as `not-deployable` at the
query's file and line (the shapes file, line 1, when the compiler found no line),
so the command exits 1.

### D6. What SemForge said about Flink goes

`explicit-node`, `path`, `not-compiled`, their quick fixes, `semforge.nestForFlink`
and the hover line are removed, not reworded: what they said is false since #1108,
and the compiler's mark takes their place where something is still refused. The
`variable-node` finding stays (`$this ex:hasStrength ?a` binds the attribute
instance, not its value, in the data as well) without its claim on how shacl2flink
reads it; shacl2flink refuses that form, and its mark says so.

## Risks / Trade-offs

- [A checkout of another version than the deployed one gives another answer] →
  The check is as true as the checkout; `SEMFORGE_SHACL2FLINK` points at the one
  to trust.
- [Import side effects of the compiler in the language server] → D3; the check
  runs only on the shapes graph and a draft, never writes.
- [The check costs time per keystroke] → One translation of one query: 4 to 6 ms
  on the kms corpus, of 7 to 11 ms for the whole diagnostics request; a whole
  package (the capability check) about 120 ms.
- [Users of `nestForFlink`] → The command was hidden from the palette and only
  reachable from the removed quick fix.

## Migration Plan

None: no data or file format changes. Rollback is reverting the SDK change.

## Open Questions

None.
