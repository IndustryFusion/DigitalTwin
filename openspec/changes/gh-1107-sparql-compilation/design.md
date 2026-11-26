# Design

## Context

A SPARQL expression is parsed into SPARQL algebra and translated pattern by
pattern. A triple is either read from the attribute view (an attribute of an
entity) or from the RDF table (the knowledge). Which of the two it is was
decided by looking the predicate up in the shapes, and everything the lookup
did not find became a join on the knowledge, where an entity is refused
("Cannot bind …").

Tables hold every value as text. A variable bound to an attribute value is
compared in the form of its RDF term: the text in quotes for a literal, in
angle brackets for an IRI.

The models of the offline checks gave an attribute instance without a time the
time of the build. The platform gives it none, so `ngsild:observedAt` matched
offline what it does not match on Flink. They give it none now.

## Goals / Non-Goals

**Goals:** a build says which expression fails and why; a supported form
answers what SPARQL answers, on SQLite and on Flink; the same check serves
tools that write queries.

**Non-Goals:** the whole of SPARQL. No plan of the SQL with Flink in the
build (#955).

## Decisions

### D1: The pattern says what is an attribute

A blank node or a variable with `ngsild:hasValue`, `ngsild:hasObject` or
`ngsild:observedAt` is an attribute instance, whatever the predicate that
leads to it. Shapes add only whether the value is an IRI or a literal
(`sh:nodeKind`), from node shapes with and without a target. Where no shape
says it, or two say it differently, the attribute's `nodeType` column decides
per row.

*Alternative:* collect attributes from all shapes, with or without a target.
It fixes declarations reached through `sh:node` and leaves attributes without
a shape, and a variable predicate, unreadable. Rejected.

### D2: Every way of writing it becomes one form before it is translated

Named instances, several payloads of one instance, paths to the payload and
constants are rewritten to `?entity predicate [ payload ?variable ]`; a
constant becomes a variable and a condition. The translation itself keeps
one form. What cannot be rewritten (a sub-attribute, `ngsild:unitCode`, an
instance of two attributes) is refused there, by name.

### D3: A variable predicate reads the name column

`?entity ?attribute [ ngsild:hasValue ?v ]` joins the attribute view without
a condition on the name, and `?attribute` is the name. When the variable is
bound before, by the knowledge or by another attribute, the name is compared
with it. The view holds an entity's Properties and Relationships, and the
payload selects between them, as in SPARQL.

`?s ?p ?o` without an instance stays refused: it would range over the
attributes and the knowledge at once.

### D4: Numbers are compared as numbers

For `<`, `<=`, `>`, `>=`, and for `=` and `!=` against a numeric constant or
cast, an attribute value or a literal of the knowledge is taken as the number
its text is: an optional sign, digits with an optional decimal point, an
optional exponent. A text that is no number is neither equal nor unequal to,
neither less nor more than a number, as a type error makes a SPARQL filter
fail. Two values that are both no numbers are compared as texts. Both targets
use the same pattern, because Flink's own conversion also takes `5d` and
surrounding blanks.

The platform sends a plain number and a string with the same text alike
(`shacl2flink/literal-datatypes`, "Strings are judged by their text"), so a
string that is a number is compared as one. This is the known difference to a
SPARQL engine. Numbers are compared as doubles.

`=` between two variables stays a comparison of texts: the platform writes a
number in one way only.

### D5: Subqueries read their own tables

An `EXISTS` or `NOT EXISTS` reuses no alias of the outer query, since under
the outer alias it would see the outer row. Its conditions are in the
`WHERE`: Flink cannot plan an `ON` that names something of the outer query.

### D6: A joined group sees only itself

An `OPTIONAL` with several patterns is a join inside a join. In parentheses
the inner one cannot name the left side, so a condition on the left side's
entity is said about the first inner table, which the outer `ON` ties to the
same entity. Where that does not hold, the group is refused by name.

An attribute of an entity is one table, so that its value and its time are of
the same instance. A second value would need a second table, and which of
the two a time belongs to would be open; it is refused instead of being the
first one again.

The `FILTER` of an `OPTIONAL` that reads nothing of its own would have to take
away what is read outside; it is refused.

A variable keeps what it is: an IRI bound by the knowledge stays in the
knowledge's form when an attribute is compared with it, and `BIND` of a
value is the same value under another name (D9 for an entity).

### D7: The check is the compiler

The report comes from running the translation itself, for the build and for
the check without one. A list of supported forms elsewhere would drift. The
check reads the shapes only, walks them instead of querying them (a package
with hundreds of shapes: under a second instead of half a minute), and needs
no RDF store.

### D8: Any exception is a report

An expression that fails for a reason nobody foresaw is named like the
others, marked as a defect of the compiler. Nothing of a package that has a
problem is written, as today.

### D9: What would answer otherwise is refused

Some forms compile to SQL that answers otherwise than SPARQL, or than the other
target. They are refused by name; supporting them is follow-up work:

- another name for an entity: its table would be the original's, and the scope
  of `BIND` is not followed;
- one variable for an attribute's value and a literal of the knowledge: the
  knowledge holds `20`, the platform `"20"`, and SQLite compares the column as a
  number while Flink compares texts. An IRI is the same on both sides and stays
  supported, as does a comparison in a `FILTER`. Inside a blank node of the
  knowledge (a list of texts, as the waste-class rule of the KMS reads) the
  value is compared with the knowledge's text as before, which finds texts and
  misses numbers; refusing it would break that rule, so the number is
  follow-up work;
- an attribute read again after the `OPTIONAL` that reads it: a condition on a
  table that may be empty;
- an entity named by its IRI inside an `OPTIONAL`: its table would become the
  group's first;
- a constant inside a blank node of the knowledge (`?s ex:a [ ex:b "x" ]`): the
  pattern cannot be ordered; a variable compared in a `FILTER` says the same.

`[ ]` as the object of a pattern of the knowledge stands for any node, an IRI as
well as a blank node, as in SPARQL. `rdfs:subClassOf*` holds a class itself for
the classes the knowledge names; a class that only a shape names is not in the
knowledge table that the SQL reads.

## Architectural implications

- The generated SQL of a query gets a comparison instead of a text
  comparison; joins and state stay. A variable predicate joins the attribute
  view on the entity alone, so it keeps one row per attribute of an entity.
- No conflict with existing specifications. `shacl2flink/literal-datatypes`
  describes `sh:datatype` and `sh:hasValue`; D4 follows its reading of texts.

## Risks / Trade-offs

- [Verdicts change for comparisons without a cast] → only to SPARQL's;
  stated in the documentation.
- [A form works in SQLite and Flink cannot plan it] → the end-to-end test
  deploys forms of every kind; #955 would catch the rest at build time.
