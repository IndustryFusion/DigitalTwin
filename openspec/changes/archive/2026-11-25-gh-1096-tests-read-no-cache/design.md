# Design

## Context

What a test run on a package directory can meet in caches:

| Cache | Before | Could decide the result |
|---|---|---|
| `.semforge/cache/graphs/` (parsed Turtle) | read and written | yes: replaces the triples of a file |
| `.semforge/cache/index/` (statement index) | read and written for the knowledge | yes: a malformed entry ends the run; its positions do not enter the result |
| `.semforge/cache/deps/` (fetched dependencies) | not read in a test run (#943) | no |
| `.semforge/cache/contexts/`, the user's context cache | not read in a test run (#943) | no |
| `.semforge/cache/views/` (editor views, verdicts) | read only by the editor | no |
| memory: statement index by text, possibly read from a changed entry earlier in the process | read | no known way from a command; closed as well |
| memory: prefix tables of the local context and the descriptor, and the descriptor's entity root, by the file's time and size | read | only when a file changes within one process keeping both; closed as well |

`.semforge/derived.ttl` and `.semforge/proposals.jsonl` are importer output and are not loaded by any of the commands. No existing spec conflicts: cache entries are not members of a package (`contracts/kms-package`), and the SDK's architecture document already calls the cache "never authoritative".

## Decisions

### D1: A test run reads no cache

While the offline scope of a test run is active, the reader of derived entries returns nothing, so the graphs and the index are computed from the files. The rule sits in the one module every derived entry passes through, so a later derived cache falls under it too.

Alternatives considered:
- *Check an entry against its file.* Showing that the triples are those of the file means parsing the file, which is all the cost the cache saves.
- *Sign entries with a key of this machine.* Keeps repeated local test runs fast, but adds key handling to protect a saving of seconds in a command that is run rarely and in CI always cold.
- *Keep the graphs cache in the user's directory.* Also keeps it fast, but a test result would still depend on what the machine kept, and every other use of the cache would move.
- *Read entries only when the directory is trusted.* Nothing tells a pull request's checkout from the author's own.
- *Refuse a package directory that holds a cache.* Every package opened in the editor has one.

### D2: A test run writes no cache

The entries a run would write are correct, but a directory from elsewhere can hold `.semforge/cache/graphs` as a link out of the package, through which the run would write and remove files. Not writing also keeps the directory as it was.

Alternatives considered:
- *Write, so that the next editor start is warm.* A saving of one parse per changed file for the editor, not worth writing into a directory that is under test.

### D3: A test run has its own memory

What a process remembers and that does not follow from a text alone (the statement index, which may have been read from a changed entry, and what is remembered of a file by its time and size) is kept per test run, starting empty. A run still reads and indexes each file once. Memory keyed on the text and filled only by computing from it, such as the statement positions of a text, stays shared: it was computed from the same content.

Alternatives considered:
- *Keep it, since each command is its own process.* True today; a caller that loads a package and then runs its tests in one process would bring the hole back.
- *Use no memory in a run.* The prefix tables are asked for once per term: thousands of parses of `kms.yaml`.
- *Key every memory on the content, everywhere.* Reads the files on every question in the editor, which the time and size avoid.

### D4: Verification and publishing, not `semforge test`

The requirement covers the test run of the contract, which verifies or publishes a package. `semforge test` is an authoring command like the editor: it resolves contexts as they do (#943) and uses the caches of the machine it runs on. The architecture document says so.

Alternatives considered:
- *Cover `semforge test` as well.* It would load large packages more slowly while authoring, on caches its user wrote.

## Risks / Trade-offs

- A repeated local test run of a large package is slower by the parsing the cache saved (about 4 s for the OPC UA pumps). Accepted: the result is the reason to run it.
