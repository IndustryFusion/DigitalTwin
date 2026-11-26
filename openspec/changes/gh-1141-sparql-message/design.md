# Design

## Context

A SPARQL constraint's `sh:message` is shown by the workbench and filled in its
result. It is read by two consumers that differ: pyshacl, and with it
`semforge test`, fills `{?x}`/`{$x}` from the violating row and leaves a
placeholder without a value as text; shacl2flink replaces every `{?x}` by the
column `x` of the compiled query, puts the message between apostrophes in SQL,
and selects SPARQL constraints by `sh:message` and `sh:select` together. What
pyshacl forgives therefore breaks on the platform.

## Conflicts

None with an existing spec. The three new warnings appear on existing packages
that already have such messages; they are warnings, so `semforge check` without
`--strict` and every other command behave as before.

## Decisions

### D1: The message is edited in the workbench
- **Chosen:** one field under the query's name in the workbench; every other
  place opens the workbench with the field open. The workbench is where the
  query's variables and a run's rows are, which the field needs.
- *Alternative:* an input box from the shape page's menu. Rejected: it cannot
  list the variables of the query as edited, nor preview a row.
- *Alternative:* edit it in the query's editor as a comment. Rejected: the
  query document holds only the query.

### D2: One filling rule, pyshacl's
- **Chosen:** a placeholder's name is compared as written and one without a
  value stays as text, in the preview, the result and the checks, so the page
  shows what `semforge test` reports.
- *Alternative:* compare names ignoring case. Rejected: neither pyshacl nor
  shacl2flink does; the warning names the variable when only the case differs.

### D3: Warnings, not refusals
- **Chosen:** what does not fit is a warning; saving and validation go on.
- *Alternative:* refuse to save a message that names an unselected variable.
  Rejected: the query may be edited next, and SemForge validates it all the same.
- The variables are what the query's parser projects (`SELECT *` included);
  when the query does not parse, nothing is said about variables, since the
  query's own check says what is wrong.

### D4: One value written as text, checked by the graph
- **Chosen:** the value is replaced in the file's text, so formatting and
  comments stay. The written file is parsed, and the write is refused unless the
  graph differs only in that constraint's messages and the language tag or
  datatype is kept.
- *Alternative:* serialise the graph again. Rejected: it rewrites the whole
  file.
- An added message goes in front of `sh:select`, where no comment can swallow it.

### D5: Optimistic, by what the page showed
- **Chosen:** the request carries the message and the query the page started
  from; if the file says otherwise now, nothing is written.
- *Alternative:* a file version. Rejected: an unrelated edit elsewhere in the
  file would refuse it.

### D6: Left to the .ttl
- **Chosen:** several `sh:message` values (one per language) or a value that is
  no text are shown and not edited: which one is meant cannot be told from the
  page.

### D7: Removing asks
- **Chosen:** an emptied message is removed after a confirmation that says the
  platform does not compile a constraint without one.

## Risks / Trade-offs

- The preview shortens IRIs as the result does; `semforge test` shows them in
  full, and the platform keeps one text per entity when several rows violate.
- The apostrophe warning is about shacl2flink as it is; if it escapes the
  message one day, the warning goes.
