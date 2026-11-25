## ADDED Requirements

### Requirement: The tests use nothing kept from earlier
While a package's tests run to verify or publish it, parsed or indexed files, fetched documents and validation results kept on disk earlier, in the package directory or elsewhere, SHALL NOT be used, and none SHALL be kept there. What was kept in memory earlier SHALL be used only if it was computed from the same content. Contexts and the vocabulary SHALL resolve as the requirements on them say. Running the examples while authoring is not covered.

#### Scenario: Changed parsed triples in a package directory
- **WHEN** the tests are run on a package directory that holds, in a tool's cache, an entry for `shacl.ttl` as it is, whose triples were emptied
- **THEN** the run reports the same constraints, examples met and coverage as without the cache

#### Scenario: Cached triples that would hide a violation
- **WHEN** an example does not meet its expectations, and the package directory holds a cache entry for `shacl.ttl` with the triples of shapes it would meet
- **THEN** the tests fail and name the example

#### Scenario: Changed index of a file
- **WHEN** the tests are run on a package directory whose cached index of `knowledge.ttl` is malformed
- **THEN** the run reports the same result as without the cache

#### Scenario: Descriptor that changes without its size or time
- **WHEN** a process has read a package and its `kms.yaml` then changes to a text of the same size with the same modification time, and the same process runs the package's tests
- **THEN** the run goes by the changed text

#### Scenario: Nothing kept
- **WHEN** the tests are run on a package directory without a cache
- **THEN** no file or directory is added to it
