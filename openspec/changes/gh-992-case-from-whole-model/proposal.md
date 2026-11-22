# Proposal

Issue: #992

## Why

A test case often wants the whole scene of the main model with a few
differences: some entities removed, some values changed. **New test case…** in
SemForge starts from a copy of a case, from one entity of the model, from a
fresh entity of a type, or from an empty file. Starting from the whole model
means picking its entities one by one or pasting the model files into an empty
case by hand.

Including the model files (`include:` in `expectations.yaml`) is no
substitute: a case and its includes are parsed into one graph, so a case can
neither remove an included entity nor override one of its values; two values
for the same attribute merge.

## What Changes

- **New start "The whole main model".** New test case… offers the main model
  as a start whenever the package has one. The new case file holds the
  documents of all model files, in load order, written into it, as a copied
  case gets its includes written in. Editing the case never changes the model,
  and later edits of the model do not reach the case. A relative `@context`
  (as `semforge retarget --to local` writes it) is rewritten to name the same
  file from the case's folder; ids that more than one model file defines are
  named in the message after writing. The suggested name is a free one.
- **Nothing half-made stays behind.** The case file is written whole or not at
  all, and a failure after it is written removes it and its declaration again
  (for every start).
- **Declared and run as the other starts.** The case is declared in its
  suite's `expectations.yaml`, `expect: valid` in `good/` or `expect: invalid`
  in `bad/`, as chosen, and run once; its case page opens.
- **The description says what the case still needs.** After the run, the
  description of the declaration says whether the model conformed and what
  that means for the case: a bad case from a conforming model fails until its
  data is edited, a good case from a violating model fails until its data
  conforms. A description given by the caller is kept.
- The language server's test-case options name the main model's files, and a
  written case reports how it was started, so the editor can say why a good
  case from a violating model fails.

## Capabilities

### New Capabilities
- `semforge-sdk/test-cases`: How SemForge's New test case… starts a case from
  the whole main model, writes it, declares it and runs it.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the test-case writer
  (`semforge/expect/addcase.py`), the options and the result of the language
  server requests `semforge/testCaseOptions` and `semforge/addTestCase` (an
  added field each; nothing removed), the extension's New test case… picker
  (`vscode/src/testcases.js`) and its README.
- No change to the `semforge` command line, to any other component, image,
  chart or deployment.

## Out of Scope

- Keeping the case in sync with later changes of the main model; the case is
  a snapshot.
- Starting from a subset of the model selected in one step (for example one
  entity and what it references).
- Changing the other starts of New test case…, Clone… or New case… of a
  SPARQL rule.
