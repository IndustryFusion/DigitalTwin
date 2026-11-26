# Proposal

Issue: #1107

## Why

A package's SPARQL constraints and rules run on the platform as the Flink SQL
that shacl2flink compiles them to. Today

- a build that cannot compile one ends with a traceback that names neither
  the expression nor its shape, and at the first one;
- valid queries are refused: attributes are only known from shapes with a
  target class, so an instance declaration reached through `sh:node`, or an
  attribute without a shape, is taken for plain RDF; a variable predicate, a
  named attribute instance, a path and a constant value are refused as well;
- some queries compile to SQL that Flink rejects when it is deployed;
- some compile to SQL that answers something else: numbers are compared as
  texts (9 is more than 10), an entity never equals an IRI, the `FILTER`
  inside an `OPTIONAL` is dropped, and so is a condition between two things
  that are bound before. Nothing reports these.

## What Changes

- **Every expression that cannot be compiled is reported**, all of them in
  one run, with shape, target, file and line, message, reason, the pattern
  where one is the reason, and the query. An error the compiler did not
  foresee is reported the same way.
- **A check without a build** says the same for a shapes file, and for one
  expression that is not in a file yet, also in a machine-readable form.
- **An attribute is recognised by the pattern that reads it**
  (`[ ngsild:hasValue … ]`, `[ ngsild:hasObject … ]`), whatever shapes say.
  They only say whether a value is an IRI or a literal; where they do not, or
  disagree, the attribute instance itself does.
- **More forms compile**: a variable predicate over attributes, a named
  instance, several payloads of one instance, a constant, a path to the
  payload, `<a>/<b>` and `^<a>` in the knowledge, `IN`, `NOT IN`, `EXISTS`,
  and the casts to `xsd:double` and `xsd:decimal`.
- **The answers are SPARQL's**: numbers are compared as numbers, an entity
  with an IRI as an IRI, the `FILTER` of an `OPTIONAL` belongs to it, no
  condition is dropped, and the first pattern of a query may be anything.
- The supported forms are documented.

A comparison of numbers without a cast (`?value > 10`) can now give another
verdict than before: the one SPARQL gives. Expressions that cast
(`xsd:float(?value) > 10.0`), as those of the packages in this repository
do, keep their verdict.

## Capabilities

### New Capabilities

- `shacl2flink/sparql-expressions`

### Modified Capabilities

None.

## Impact

- **Component:** `semantic-model/shacl2flink` (the SPARQL translation, the
  build, a new check, its tests and documentation).
- **Contracts between components:** none changes. Alerts keep their form.
- **Deployments:** a package has to be rebuilt to get the new verdicts. A
  package that compiled before compiles to the same joins; a comparison of
  values is a longer expression.

## Out of Scope

- Sub-attributes, `ngsild:unitCode`, `ngsild:datasetId`, list and JSON values
  in a query; `UNION`, `VALUES`, `MINUS`, sub-selects, `ORDER BY`, `LIMIT`,
  and functions beyond casts. They are refused by name.
- Planning the generated SQL with Flink's parser in the build (#955).
- Reading two values of one attribute of an entity, which needs two
  independent instances. It compiles today, to one instance for both, and is
  refused by name now; inside an `EXISTS` it is supported.
- Forms that would compile to another answer than SPARQL's (design D9):
  another name for an entity, one variable for an attribute's value and a
  literal of the knowledge outside a blank node, an attribute read again after
  its `OPTIONAL`, an entity named by its IRI in an `OPTIONAL`, and a constant
  inside a blank node of the knowledge. They are refused by name.
- Constraints that are not collected today (a SPARQL constraint without a
  message, a shape without a target class).
