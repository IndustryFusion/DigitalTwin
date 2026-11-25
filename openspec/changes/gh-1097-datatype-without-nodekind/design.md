# Design

## Context

The compiler stores a node kind for a value shape only when it is `sh:IRI` or
`sh:Literal`, or when the shape is one of a list or JSON property. The generated
SQL selects the rows of the datatype check by that node kind, and skips the node
kind check for a shape without one. Both dialects come from one template.

The circuit of a connective judges all instances of an attribute together: each
member says whether *some* instance violates it. A shape
`sh:or ( [integer] [double] )` on the property shape with the instances `1` and
`80.5` has both members violated and alerts, although each instance conforms.
That is existing behaviour, measured with `sh:nodeKind sh:Literal` on the state
before this change. It stayed unnoticed without `sh:nodeKind` because the
members never fired.

No existing specification conflicts with the change. The requirements of
`shacl2flink/literal-datatypes` speak of "a shape with `sh:datatype`" and never
mention `sh:nodeKind`; their scenarios fail today for a shape without it.

## Goals / Non-Goals

**Goals:** the datatype verdicts do not depend on `sh:nodeKind`; a missing
`sh:nodeKind` constrains what it constrains in SHACL, nothing; no value that
conforms starts to alert.

**Non-Goals:** the node kind check itself, the circuit of connectives,
`sh:class`, `sh:minCount` of a value shape (see the proposal, *Out of Scope*).

## Decisions

### D1 — A constraint of its own, read by no connective

- **Chosen:** the constraints the compiler extracts today stay as they are, also
  as members of connectives, and keep their verdicts. For each datatype that
  every instance has to meet by itself one more constraint is added that holds
  only the datatypes and is published on its own. It is collected by walking the
  shape: the value shape's own datatype, those of its `sh:and` branches, and the
  union over an `sh:or` whose branches all state one, on the value shape or on
  the property shape. A branch that states `sh:nodeKind sh:Literal` or `sh:IRI`
  is left to the existing constraint, and a deactivated shape requires nothing;
  both make an `sh:or` require nothing. So do a branch with an `sh:path`, which is
  about other values, and a branch that leads back to the shape. Each is a necessary condition of the shape, so a violation
  of it is a violation of the shape.
- *Let the existing constraint of the value shape fire:* the circuits mix
  instances and raise false alerts for conforming attributes; a datatype beside
  `sh:not` is folded into the negated branch and changes its verdict; the
  datatypes of list elements and of collapsed `sh:or` branches are read as the
  value's own.
- *Infer `sh:Literal`:* the same, and it turns on the node kind check, so a
  Relationship, ListProperty or JsonProperty would alert although SHACL finds
  nothing to judge.
- *Judge connectives per instance:* the right fix for them, but a rework of the
  circuit, its tables and its state. It belongs in its own change.
- *Reject such a shape at build time:* the shape is valid SHACL and its meaning
  is clear; rejecting it breaks packages that build today.

The added constraint is published like any other, also from a node shape applied
to a relationship's object. Only a property shape reached from its targeted node
shape through `sh:property` alone is considered: below a connective it
constrains nothing by itself.

### D2 — Only attributes with a value of hasValue are judged

- **Chosen:** a Property, and a GeoProperty, which Flink tells apart from a
  Property and whose value is never a literal. Any other attribute has no value
  node and conforms.
- *Every attribute of that name, as with `sh:nodeKind sh:Literal`:* there the
  datatype alert only accompanies a node kind alert; here it would be a false
  one.

### D3 — A value that is no literal violates every datatype

- **Chosen:** for a shape without a node kind, an IRI or a blank node is
  reported by the datatype check, as in SHACL. The model reader marks a blank
  node on `ngsi-ld:hasValue`, whose text satisfied `xsd:string`, as `@blank`;
  the bridge calls the geometry of a GeoProperty `@json`. The node kind check
  reads `@blank` as the literal it took it for, so shapes with a node kind keep
  their verdicts. On Flink this holds for IRIs and geometries: the bridge
  passes a Property on only when its value is a literal or an IRI, so a JSON
  object never arrives there.
- *Mark it `@json`:* new node kind alerts for `sh:nodeKind sh:Literal` on
  SQLite, also from members of connectives, whose verdicts would change.
- *Judge the text:* an IRI would satisfy `xsd:string` and every datatype the
  check cannot read, and nothing else would report it.

### D4 — Other node kinds count as none

`sh:IRIOrLiteral`, `sh:BlankNode`, `sh:BlankNodeOrIRI` and
`sh:BlankNodeOrLiteral` are stored as no node kind today, so `sh:datatype`
beside them is checked as well. SHACL checks `sh:datatype` independently of
`sh:nodeKind`. The alternative, storing them, would add a node kind check that
does not exist today.

### D5 — A list of datatypes accepts a value declared with any of them

- **Chosen:** for the added constraints, a declared type that is in the list
  satisfies it. A list with one of the four datatypes judged by text
  (`xsd:integer` and `xsd:decimal`) rejects a value declared with the other
  one when `sh:nodeKind sh:Literal` is stated. `rdf:langString` in a list accepts a value without a declared type,
  since the bridge passes none on for a language-tagged string. A declared
  boolean may be written `1` or `0`, as `sh:hasValue` reads it.
- *Also with `sh:nodeKind sh:Literal`:* one verdict per literal, but those
  constraints are members of connectives, which are judged over all instances.
  A comparison with the state before, on random shapes, showed connectives that
  lost a true alert or raised a new false one. It belongs with the rework of the
  circuit.

The infinities and NaN are accepted as `INF`, `+INF`, `-INF` and `NaN` in any
case, on SQLite and Flink alike: the bridge passes the text of the model on, the
model reader writes `inf`, `-inf` and `nan`. XSD knows the upper case only, so
`Inf` declared `xsd:double` is accepted although it is ill-typed.

A declared type is found in the list, or compared with a lone datatype, as a
whole. With `sh:nodeKind sh:Literal` the lone comparison tests for a part of the
text, so `xsd:gYear` satisfies `xsd:gYearMonth` there.

A list with `rdf:langString` therefore also accepts an untyped string, on both
sides, which SHACL rejects when `xsd:string` is not in the list. Flink also
accepts a plain number or boolean there, which SQLite reports: on Flink they
arrive as text without a type, like a language-tagged string.

### D6 — A value that is no literal is told by its type

- **Chosen:** the rows of the added constraints see the type `@no-literal` for
  such a value, so the datatype check needs no node type.
- *Read the node type in the datatype check:* Flink keeps one deduplication of
  the attributes, with its joins, per set of columns the checks read. Before, the
  checks read no type, the node type, or the declared type. A datatype check
  that reads the node type beside the declared type is a fourth set: the e2e job
  grows from 223 to 224 tasks, with one more copy of the attribute state. Told
  in the query all checks start from, the checks of a declared type (`sh:in`,
  `sh:hasValue`, `sh:datatype`) read both columns and share one set.

## Risks / Trade-offs

- [The deployment of the job is at its limit] On the one core the chart gives a
  TaskManager, the e2e job fails over with a timeout of Flink's task submission
  (10 s) before it runs, with and without this change. → Not changed here; with
  D6 the job has the tasks it had.
- [New alerts on running packages] The shapes asked for them. → The proposal
  names it under Impact; no package in `semantic-model/kms` is affected.
- [A datatype alert where pyshacl names the `sh:or` or `sh:and`] → The check
  that decides names the alert, a documented deliberate divergence; the new
  fixtures' lines are listed with it.
- [Datatypes that stay unchecked] In `sh:not` and `sh:xone`, in an `sh:or` with
  a branch that states none or states a node kind, under a connective of a node shape or of an
  enclosing attribute, and the other parameters of an `sh:or` branch. → As
  before the change; stated in the documentation and the proposal.
