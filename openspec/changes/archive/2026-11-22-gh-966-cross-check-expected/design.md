# Design

## Context

The cross-check (`semforge/target/crosscheck.py`) keys a result as
(entity, attribute, constraint type) on both sides and compares the two as
multisets. A key that only the compiled SQL reports is *missed*, and one
that only pyshacl reports is *extra*. An extra key is expected when the
compiler is known not to compile it. The key carries no value, so the
cross-check cannot see that a rejected value was a string.

shacl2flink's pyshacl comparison does not decide per value either. It lists
each deliberate divergence of its own fixtures by name in
`expected-divergences.txt`, with a comment that gives the reason. The rule
itself lives in the compiler's `sh:datatype` check
(`lib/shacl_properties_to_sql.py`). For a value without a declared type, a
text with a decimal point or an exponent is a double, and a text of digits
is an integer.

## Goals / Non-Goals

**Goals:** the two deliberate divergences of #958's probe are listed as
expected, each with its reason, and a real difference on a number still
shows as missed or extra.

**Non-Goals:** changing a verdict on either side; `sh:hasValue` (#1044).

## Decisions

### D1: The validation result records the rejected value and the admitted datatypes

- **Chosen:** pyshacl's result for a value constraint records the value it
  rejected: its text and its declared datatype. A literal that declares no
  datatype is marked *untyped*, which is not `xsd:string`, so a value that
  declares `xsd:string` is not taken for an untyped one. For `sh:datatype`,
  and for an `sh:or` whose every branch says `sh:datatype` and no other
  constraint, it also records the datatypes the constraint admits. Names,
  messages and severities in a branch constrain nothing and are ignored. A
  branch such as `[sh:datatype xsd:integer; sh:maxInclusive 100]` rejects
  `"500"` whatever its text says, so its `sh:or` admits nothing. The fields
  are not part of the result's identity or equality, so expectations,
  coverage and digests do not change.
- *Alternative:* look the value up in the model by entity and attribute
  when the cross-check runs. Rejected: an attribute can have several
  instances (`datasetId`), and the shape that rejected the value is not
  known from the key, so the lookup would have to guess both.
- *Alternative:* list the probe's differences by name, as
  `expected-divergences.txt` does. Rejected: the cross-check runs on any
  package, so a name-based list cannot cover it. The reason stays the same,
  and the README points to the shacl2flink list.

### D2: The text rule is mirrored, and a test pins the copy to the compiler

- **Chosen:** the cross-check reads the text with the same two patterns as
  the compiler's `sh:datatype` check. A test in `test_profile_drift.py`
  reads them from shacl2flink's source and fails when they differ, as that
  file already does for the profile.
- *Alternative:* import the pattern from shacl2flink. Rejected: the SDK runs
  without shacl2flink on its path, like `semforge/rdfio/numbers.py`.
- *Alternative:* treat every string whose text is a number as expected.
  Rejected: `"80.5"` on `xsd:integer` would then be expected, although the
  compiled SQL rejects it too. A compiler that accepted it would be a bug
  that the cross-check exists to show.

A string is expected only when it declares no type and the datatype that
the compiled SQL reads its text as is one the constraint admits. Every other
rejected string stays a real difference, a declared `xsd:string` included,
because a declared type decides on both sides. The patterns match ASCII
digits only and the whole text, as PCRE does in the SQL, so `"٨٠"` and
`"80\n"` are not read as numbers.

When a key holds both strings and other values, the strings are expected
only if the SQL's alerts and the `sh:or` pairs (D3) account for every other
value of the key. Otherwise the counts cannot tell which values the SQL
matched, and the key stays a difference.

### D3: One sh:or, one difference

- **Chosen:** a missed `DatatypeConstraintComponent` and an extra
  `OrConstraintComponent` on the same entity and attribute are paired one to
  one into a single expected entry. Only `sh:or` results that are of
  datatypes (D1) and whose value is not a string judged by its text can be
  partners, because only those does the SQL reject too. The number of pairs
  is at most the number of such results. Take an attribute with the string
  `"80"` and the integer `80`: pyshacl rejects only the string, so a
  datatype alert of the SQL concerns the integer and stays missed, while the
  string is expected by its text. A pair that remains unmatched stays missed
  or extra.
- *Alternative:* alias `OrConstraintComponent` to the datatype component, as
  min and max count are aliased. Rejected: it would also rename an `sh:or`
  over shapes, which the compiler does not collapse into a datatype check.

### D4: "Agrees" means no unexpected difference

The command prints that the compiled SQL agrees with pyshacl when every
reported difference is expected, and lists those differences above that
line. Before this change, the line was printed only when no difference was
reported at all, so a package whose differences were all expected never
showed it.

## Risks / Trade-offs

- The result carries three more fields, which the editor's verdict cache
  serialises. Old cache entries lack them and load with empty defaults.
- CI now builds sqlite3's PCRE extension in the SDK job as well (about a
  minute), so the cross-check tests run there instead of skipping.
