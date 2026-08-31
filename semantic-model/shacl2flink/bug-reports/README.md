# Bug reports

Upstream defects found while building the validation pipeline, each with a
runnable reproducer so the claim can be checked rather than believed.

One directory per bug, named `<project>-<version>-<symptom>`. Each is
self-contained:

- `README.md` — the report: the failing case, expected vs observed, the root
  cause in the upstream source, and the versions it affects. Written to be
  pasted into an upstream tracker as is.
- a reproducer that runs in throwaway containers, including a **control** that
  is expected to pass, so a reviewer can see the difference rather than take
  our word for it
- `*.patch`, where a fix has been written and verified

| directory | status |
|---|---|
| `flink-2.1-topn-lost-retraction` | not filed upstream |

A report belongs here once it reproduces outside our schema. Anything still
tangled up in our own SQL is a bug in our SQL until proven otherwise -- that
distinction is what makes these worth sending.
