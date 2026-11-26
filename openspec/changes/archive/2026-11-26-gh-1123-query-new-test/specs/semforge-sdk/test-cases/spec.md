# semforge-sdk/test-cases Delta

## ADDED Requirements

### Requirement: New test is offered for a SPARQL query
The menu of a SPARQL constraint's row on a type page SHALL offer New test…, which offers exactly two kinds of test: one that should conform and one that should fail. It SHALL then ask only for the case's name, suggesting one no case in the target folder has. The menu of a SPARQL rule's row SHALL NOT offer it.

#### Scenario: A constraint
- **WHEN** the user opens the menu of a SPARQL constraint on a type page and picks New test…
- **THEN** Should conform and Should fail are offered and nothing else, and the name suggested is free

#### Scenario: A rule
- **WHEN** the user opens the menu of a SPARQL rule on a type page
- **THEN** New test… is not offered

#### Scenario: Not answered
- **WHEN** either question is left without an answer
- **THEN** nothing is written

### Requirement: A query's test that should conform is one the query runs on
A test of a query that should conform SHALL be written to the `good/` folder of the shape's suite and declared `expect: valid` without an assert. The query SHALL run on an entity of it. It SHALL NOT start from a case that is expected to violate.

#### Scenario: Silent
- **WHEN** a test that should conform is written for a query of the type Filter, and a valid case or the model has a Filter it holds on
- **THEN** the case passes, and the query's shape page lists it as a case in which the query was evaluated and did not fire

### Requirement: A query's test that should fail asserts the query
A test of a query that should fail SHALL be written to the `bad/` folder of the shape's suite and declared `expect: invalid`, with an assert that the query fires on an entity of the case. It SHALL fail until the query fires on that entity, and the message after writing SHALL say so.

#### Scenario: Not firing yet
- **WHEN** a test that should fail is written from data the query holds on
- **THEN** the case fails, its page shows the one assert, and the message names the query's shape and the entity

#### Scenario: Made to fire
- **WHEN** the data of that case is edited so that the query fires on that entity
- **THEN** the case passes

### Requirement: The test is about an entity of the page's type
The entity a test of a query is about SHALL be one of the page's type, or of a type below it, that the query is evaluated on. It SHALL come from a case, else from the main model together with the model's entities it points at, else be a new entity of the type with a valid value for each required attribute. When the query is not evaluated on the new entity either, the test SHALL be refused with a message that says so, and nothing SHALL be written.

#### Scenario: A query of several types
- **WHEN** a query reaches entities of the types Cutter and Plasmacutter, and New test… is run on the page of Plasmacutter
- **THEN** the case has a Plasmacutter, and the test is about it

#### Scenario: A type without entities
- **WHEN** neither a case nor the model has an entity of the page's type
- **THEN** the case has a new entity of it, and the test is about that one

#### Scenario: What an entity of the model points at
- **WHEN** the scene comes from the main model and its entity points at another entity of the model
- **THEN** the case has both

#### Scenario: Out of the query's reach
- **WHEN** the query is evaluated on no entity of the type, a new one included
- **THEN** the test is refused, and no file is written or changed

### Requirement: A query's test keeps what a relative context names
In a test of a query, and in a case New case… of a shape page writes, a relative `@context` of a copied or new document (a string, or an entry of an `@context` list) SHALL be rewritten to name the same file from the case's folder, whether the document comes from a case in another folder, from the main model or is a new entity. URLs, absolute paths and inline context objects SHALL be kept as written, and the documents copied from SHALL be unchanged.

#### Scenario: From a model with a relative context
- **WHEN** the model's documents name `"@context": "context.jsonld"` at the package root, and a test of a query is written from the model into `examples/<suite>/good/`
- **THEN** the case's documents name `../../../context.jsonld`, the query is evaluated on the case's entity, and the model keeps `context.jsonld`

### Requirement: A query's test is run once and written whole
A test of a query SHALL be run once, its case page SHALL open, and the message SHALL say whether it passes. When anything fails after the case was written and before its outcome is known, the case and its declaration SHALL be removed again. A name that is taken SHALL be refused.

#### Scenario: The outcome
- **WHEN** a test that should conform is written and something of its scene violates
- **THEN** the message says that it does not pass, and why

#### Scenario: A failure after declaring
- **WHEN** the run after declaring the case fails with an error
- **THEN** neither the case file nor its declaration remains, and the suite's `expectations.yaml` is as it was before

#### Scenario: A name that is taken
- **WHEN** the name given is one of a case in the target folder
- **THEN** the test is refused, and that case is unchanged

### Requirement: New case of a shape page is as before
New case… of a shape page SHALL write a case that should fail, about the first entity the query is evaluated on whatever its type, and SHALL NOT write a new entity.

#### Scenario: From the shape page
- **WHEN** New case… is run on the page of a shape nothing reaches
- **THEN** it is refused, as there is no scene to start from
