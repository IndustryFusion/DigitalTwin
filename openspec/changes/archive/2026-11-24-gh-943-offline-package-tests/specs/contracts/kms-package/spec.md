# Delta for KMS Package

## ADDED Requirements

### Requirement: SERVICE in a package's SPARQL
A SPARQL constraint, rule or target of a package that uses `SERVICE`, however the keyword is written, SHALL make the package's tests fail before any example runs, naming the constraint, rule or target and the service, whether or not the caller allows network access, and no connection to the service SHALL be opened.

#### Scenario: SERVICE in a constraint
- **WHEN** a package's tests are run and a SPARQL constraint of shape `ex:RemoteShape` uses `SERVICE <http://127.0.0.1:8890/sparql>`
- **THEN** the tests fail naming `ex:RemoteShape/SPARQLConstraintComponent` and the service, and no connection to the service is opened

#### Scenario: SERVICE in a rule
- **WHEN** a package's tests are run and a SPARQL rule of shape `ex:RemoteRuleShape` uses `SERVICE <http://127.0.0.1:8890/sparql>`
- **THEN** the tests fail before any example runs, naming `ex:RemoteRuleShape` and the service, and no connection to the service is opened

#### Scenario: SERVICE with network access allowed
- **WHEN** the same tests are run with network access allowed
- **THEN** they fail the same way, and no connection to the service is opened

#### Scenario: SERVICE written with a code point escape
- **WHEN** a SPARQL rule writes the keyword as `\u0053ERVICE` or `\U00000053ERVICE`
- **THEN** the tests fail the same way

#### Scenario: SERVICE without a space after the keyword
- **WHEN** a SPARQL rule uses `SERVICE:sparql { … }` or `FILTER(?b<2).SERVICE?u { … }`
- **THEN** the tests fail the same way

### Requirement: SPARQL that does not parse fails the tests
A SPARQL constraint, rule or target that does not parse, with the prefixes declared for it, SHALL make the package's tests fail before any example runs, naming the constraint, rule or target.

#### Scenario: Syntax error in a rule
- **WHEN** a package's tests are run and the SPARQL rule of shape `ex:BrokenShape` has a syntax error
- **THEN** the tests fail naming `ex:BrokenShape`, and no example runs

### Requirement: A package's tests run offline
Running a package's tests SHALL open no network connection and resolve no host name, except to fetch a JSON-LD context or the NGSI-LD vocabulary when the caller explicitly allows it. When the tests need nothing remote, their result SHALL be the same with and without that permission.

#### Scenario: The example package without any network
- **WHEN** the tests of `kms/example` are run on a machine without network access
- **THEN** every example meets its expectations, and no connection or host name lookup is attempted

#### Scenario: Same result with and without the permission
- **WHEN** the tests of any package in `semantic-model/kms` are run once without and once with fetching allowed
- **THEN** both runs report the same examples, the same examples met, and the same covered constraints

### Requirement: Contexts of a test run resolve from the package
While a package's tests run, the model SHALL keep naming its published context URL, which SHALL resolve from the local context file the descriptor declares for it. Other contexts SHALL resolve only from a file inside the package or from a copy the consumer ships, pinned by its content. Unless fetching is allowed, any other context SHALL fail the tests, naming its URL and, for an undeclared own context, what to declare.

#### Scenario: Remote context
- **WHEN** a model of the package names, beside its published context, a remote context that is not pinned, and the tests are run without fetching allowed
- **THEN** the tests fail naming the context's URL, and nothing is fetched

#### Scenario: Own context not declared
- **WHEN** the model names `https://example.org/ctx.jsonld` as its context and `kms.yaml` declares no published context of that URL
- **THEN** the tests fail naming the URL and saying to add `published: https://example.org/ctx.jsonld` under `context:` in `kms.yaml`, and nothing is fetched

#### Scenario: Scheme in another spelling
- **WHEN** a context is named `HTTP://127.0.0.1:8890/ctx.jsonld`, or a file outside the package as `FILE:///…`
- **THEN** it is treated like its lower-case spelling: the tests fail naming it, and nothing is fetched or read

#### Scenario: Another scheme
- **WHEN** a context is named by a URL whose scheme is neither http, https nor file, such as `ftp://127.0.0.1:8890/ctx.jsonld`
- **THEN** the tests fail naming it, with fetching allowed too, and no connection is opened

#### Scenario: A file context that leaves the package
- **WHEN** a context, at any place a context can be named, is a file name that leads outside the package root, through `..`, percent-encoding, a `#` or `?` in it, or a symbolic link
- **THEN** the tests fail naming it, with fetching allowed too, and the file is not opened

### Requirement: An allowed fetch stays on http and https
When fetching is allowed, a context or vocabulary SHALL be fetched over http or https only, at every redirect, and only the document at the URL SHALL be read: no alternate a server names, and no file. A fetch that fails, takes too long or returns too much SHALL fail the tests, naming the URL.

#### Scenario: Redirect to another scheme
- **WHEN** fetching is allowed and the server of a context or vocabulary redirects to an `ftp:` or `file:` URL
- **THEN** the tests fail, no connection is opened to the new address and no file is read

#### Scenario: Link header
- **WHEN** fetching is allowed and the server of a context answers with a `Link` header naming a file as its alternate
- **THEN** the file is not read

### Requirement: The NGSI-LD vocabulary of a test run
While a package's tests run, its NGSI-LD vocabulary SHALL resolve from a file inside the package or from a copy the consumer ships, pinned by its content; it SHALL be fetched only when the caller allows it. A package that names none SHALL use the official vocabulary, whatever the environment names. A vocabulary that does not load SHALL fail the tests, naming its source.

#### Scenario: The official vocabulary offline
- **WHEN** a package names the official NGSI-LD vocabulary URL, pinned, and its tests are run without network access
- **THEN** the vocabulary resolves from the shipped copy and the tests run

#### Scenario: A remote vocabulary that is not shipped
- **WHEN** a package names another remote vocabulary and its tests are run without fetching allowed
- **THEN** the tests fail naming the vocabulary's source, and nothing is fetched

#### Scenario: The environment names a vocabulary
- **WHEN** a package names no vocabulary and the environment names a default one for such packages
- **THEN** its tests run with the official vocabulary

### Requirement: The tests read only the package's examples
While a package's tests run, an example or an include that resolves outside the package root SHALL fail the tests, naming it.

#### Scenario: Example outside the package
- **WHEN** an expectations entry names `../../../../outside.jsonld` or an absolute path
- **THEN** the tests fail naming the entry, and the file is not read
