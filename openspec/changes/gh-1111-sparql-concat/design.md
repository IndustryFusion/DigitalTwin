## Context

The compiler represents a term as text with its delimiters: `"literal"`, `<iri>`. Two macros remove them, `SQL_DIALECT_STRIP_LITERAL` and `SQL_DIALECT_STRIP_IRI`; on Flink they remove every such character, also inside the text.

## Goals / Non-Goals

**Goals:** the text SPARQL gives, on both dialects. **Non-Goals:** see "Out of Scope" in the proposal.

## Decisions

### The text of an expression is compiled, not stripped
Inside `CONCAT` and `STR` an expression is compiled to its text without delimiters: a constant is written as it is, `IF`, `CONCAT` and `STR` pass it on to their arguments, and only a variable or another expression has its delimiters removed, one at each end. The whole result gets the delimiters of a literal once.
*Alternatives:* stripping the compiled argument with the existing macros: a text such as `" < "` loses its sign. Making the macros anchored: changes every query which uses them today. A UDF: needs a new image for what SQL can do.

### SQL concatenation gives the unbound case
`||` with a NULL is NULL in both dialects, as an unbound argument makes `CONCAT` unbound. The message shows `NULL` for an unbound variable, as today.

## Risks / Trade-offs

- A number is written as the platform holds it, e.g. `0` for a value declared `xsd:double` and sent as `0`, while a SPARQL engine may write the canonical `0.0` → stated in the documentation.

## Open Questions

None.
