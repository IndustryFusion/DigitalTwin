# Proposal

Issue: #1044

Also resolves #1045. Both issues close with the archive of this change.

## Why

`sh:hasValue` still gives different verdicts on SQLite and Flink for two
kinds of constant that #965 (PR #1043) left open:

- **A string constant against a number (#1044).** With `sh:hasValue "1.0"`
  and the plain value `1`, Flink compares the untyped text `1` with `1.0` and
  raises an alert, while SQLite casts both sides by the `xsd:integer` the
  model gives the value and does not. A declared `xsd:integer` or
  `xsd:double` is cast the same way: SQLite truncates
  (`CAST('1.0' AS INTEGER)` is `1`, so a declared integer `1` satisfies
  `"1.0"`), and Flink's safe cast yields NULL for a constant that is no
  integer text, such as `"1.0"`, so it never alerts. `tests/test_hasvalue_check.py`
  records the plain-number case as a strict expected failure.
- **A boolean constant (#1045).** The constraint table holds `sh:hasValue
  true` as `True`, the way Python writes it, while Flink receives a plain
  boolean as the untyped text `true`, so `sh:hasValue true` alerts on Flink
  for a plain `true`. SQLite casts both sides to a boolean, and SQLite reads
  `True`, `False` and `true` all as `0`, so on SQLite `false` satisfies
  `sh:hasValue true` and `"True"` satisfies it too.

## What Changes

- **A string constant is compared with the text the platform sends.** An
  untyped value is compared by its text, as Flink does today. A number, plain
  or declared, satisfies a string constant only when the constant is exactly
  the text the platform writes for that number. The bridge is JavaScript and
  writes a number the way JavaScript does: `1` for 1.0, `0.5`, `1e+21` for
  10^21, `1e-7` for 10^-7. So plain `1`, plain `1.0` and a declared double
  `1` satisfy `"1"`; only the string `"1.0"` satisfies `"1.0"`, which keeps
  #965's scenario that `"1"` violates `"1.0"`. A boolean value is written
  `true` or `false`.
- **A boolean constant is met by the same boolean:** a plain `true` /
  `false`, a value declared `xsd:boolean` with `true`/`1` or `false`/`0`, or
  an untyped string whose text is exactly `"true"` / `"false"`. `"True"`,
  `"TRUE"`, `"1"`, `"0"` and plain numbers do not satisfy it.
- The check never casts a value to the datatype it declares, so neither the
  SQLite truncation nor a NULL from Flink's safe cast decides a verdict.
  The one exception to comparing with the sent text: a value declared with a
  numeric datatype is compared by its value, also when written as a string
  (`{"@value": "1.0", "@type": "xsd:double"}` meets `"1"`), because the
  SQLite side cannot tell it from the number.
- A constant of another datatype (`xsd:gYear`, `xsd:token`, one of the
  model's own) is compared like a string constant, with its text as written.
- A number constant that is ill-typed or not finite, and an ill-typed boolean
  constant, fail the build, as other untranslatable shapes do.
- SQLite and Flink give the same verdict. The expected failure becomes a
  passing test.
- The pyshacl comparison lists where this deliberately differs from a
  conformant SHACL engine, which compares RDF terms.
- The `sh:hasValue` entry of the shacl2flink documentation states both rules.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `shacl2flink/literal-datatypes`: states how `sh:hasValue` compares a
  string constant with numbers and booleans, adds how it compares a boolean
  constant, and extends the documentation requirement. Its Purpose already
  covers "how `sh:hasValue` compares a value with its constant" and stays.

## Impact

- **shacl2flink** only: the generated `sh:hasValue` check, the compiler that
  fills the constraint table (it writes a boolean constant as `true`/`false`
  and marks a string constant that is the platform's text of a number, in the
  internal `hasValueType` column from #965, and rejects the constants of
  design D8), the writer of the SQLite model rows (a value of another declared
  datatype keeps its lexical form, D6), the documentation, and the tests
  (a kms-constraints fixture, unit tests of the generated check, the pyshacl
  comparison, the Flink e2e test).
- Deploying the change means deploying a regenerated shacl2flink package: its
  constraint rows and its SQL statements go together, as for #965.
- **No contract between components changes.** The bridge, Scorpio and the
  live-data path stay as they are; the rule is written against the text the
  bridge already sends. The constraint table is written and read only by what
  shacl2flink generates.
- Verdicts change only where SQLite and Flink disagreed or where both were
  wrong under the rule: on Flink, a plain boolean now meets a boolean
  constant; on SQLite, `false` and `"True"` no longer meet `sh:hasValue
  true`, and a plain or declared number no longer meets a string constant
  that is not the platform's text of it; on both, a declared integer or
  double whose text is not that of the constant alerts.

## Out of Scope

- Number constants: #965 settled them and they keep their rule.
- `sh:in`, whose members are compared by text and type.
- Lexical forms rdflib normalises when it reads a model (an `xsd:dateTime`
  written with `Z`), which can still make a declared value's text differ
  between the sides (design, D6).
- The SemForge SDK, whose offline validation uses a conformant SHACL engine
  and keeps comparing terms.
- Changing what the bridge or Scorpio write.
