# semforge-sdk/test-cases Delta

## RENAMED Requirements

- FROM: `### Requirement: A query's test that should conform is one the query runs on`
- TO: `### Requirement: A query's test that should conform starts empty`
- FROM: `### Requirement: A query's test that should fail asserts the query`
- TO: `### Requirement: A query's test that should fail starts empty and unasserted`
- FROM: `### Requirement: The test is about an entity of the page's type`
- TO: `### Requirement: A test started from a scene is about an entity of the page's type`
- FROM: `### Requirement: New case of a shape page is as before`
- TO: `### Requirement: New case of a shape page asks what the case should show`

## MODIFIED Requirements

### Requirement: A query's test that should conform starts empty
A test of a query that should conform SHALL be written to the `good/` folder of the shape's suite and declared `expect: valid` without an assert, its file holding no document: the entities it needs are pasted into it from the main model. Its description and the message after writing SHALL say that it starts empty and that the query must stay silent on what is pasted.

#### Scenario: Written empty
- **WHEN** a test that should conform is written for a query of the type Filter
- **THEN** its file holds no document, it is declared `expect: valid` without an assert, and the message says that its entities are pasted from Main

#### Scenario: Silent
- **WHEN** entities the query holds on are pasted into that case
- **THEN** the case passes, and the query's shape page lists it as a case in which the query was evaluated and did not fire

### Requirement: A query's test that should fail starts empty and unasserted
A test of a query that should fail SHALL be written to the `bad/` folder of the shape's suite and declared `expect: invalid` without an assert, its file holding no document. It SHALL fail as unfinished until its data makes the query fire and that firing is asserted (Assert it on its case page). Its description and the message after writing SHALL say that it starts empty, that its entities are pasted from Main and edited until the query fires, and that it fails until then.

#### Scenario: Not firing yet
- **WHEN** a test that should fail is written
- **THEN** its file holds no document, the case fails, its page shows no assert, and the message says what to paste and that the case fails until the query fires

#### Scenario: Firing, not yet asserted
- **WHEN** entities are pasted into that case and edited so that the query fires, and nothing is asserted
- **THEN** the case still fails, as one whose reason is missing

#### Scenario: Made to fire
- **WHEN** the query fires in that case and that firing is asserted
- **THEN** the case passes

### Requirement: A test started from a scene is about an entity of the page's type
A test of a query started from a scene (`scene: copy` in `semforge/newCase`) SHALL be about an entity of the page's type, or of a type below it, that the query is evaluated on: from a case, else from the main model with the model's entities it points at, else a new entity of the type with a valid value for each required attribute. When the query is not evaluated on the new one either, it SHALL be refused with a message that says so, and nothing SHALL be written.

#### Scenario: A query of several types
- **WHEN** a test is started from a scene for a query that reaches entities of the types Cutter and Plasmacutter, on the page of Plasmacutter
- **THEN** the case has a Plasmacutter, and the test is about it

#### Scenario: A type without entities
- **WHEN** a test is started from a scene and neither a case nor the model has an entity of the page's type
- **THEN** the case has a new entity of it, and the test is about that one

#### Scenario: What an entity of the model points at
- **WHEN** a test is started from a scene that comes from the main model and its entity points at another entity of the model
- **THEN** the case has both

#### Scenario: Out of the query's reach
- **WHEN** a test is started from a scene and the query is evaluated on no entity of the type, a new one included
- **THEN** the test is refused, and no file is written or changed

### Requirement: New case of a shape page asks what the case should show
New case… of a shape page SHALL first ask whether the case should conform or fail, offering exactly Should conform and Should fail in the words New test… of a type page uses, then only the case's name, suggesting one no case in the folder the answer picks (`good/` or `bad/`) has. It SHALL write the case as a query's test that should conform, or should fail, is written: empty, and declared without an assert. A shape without a SPARQL constraint, or one without a target, SHALL be refused as before.

#### Scenario: Asked first
- **WHEN** the user runs New case… on a shape page
- **THEN** Should conform and Should fail are offered and nothing else, before the name

#### Scenario: Should fail
- **WHEN** the user answers Should fail and gives a name
- **THEN** the case is written empty into the shape suite's `bad/` folder and declared `expect: invalid` without an assert

#### Scenario: Should conform
- **WHEN** the user answers Should conform and gives a name
- **THEN** the case is written empty into the shape suite's `good/` folder and declared `expect: valid`

#### Scenario: Not answered
- **WHEN** either question is left without an answer
- **THEN** nothing is written

#### Scenario: From the shape page
- **WHEN** New case… is run on the page of a shape that no entity of a case or the model reaches
- **THEN** the case is written empty all the same: what reaches it is what will be pasted

## ADDED Requirements

### Requirement: New test case offers an empty file first
New test case… SHALL list An empty file first among its starts, saying that its entities are pasted from Main, before a copy of a case, the whole main model, an entity of the model and a new entity of a type.

#### Scenario: The first start
- **WHEN** the user runs New test case… and has chosen a suite and whether the case should conform or violate
- **THEN** An empty file is the first start offered

### Requirement: A test started from a scene is declared as before
A test that should conform started from a scene SHALL NOT start from a case that is expected to violate; a test that should fail started from a scene SHALL assert that the query fires on that entity, and SHALL fail until it does. Without `scene`, a request SHALL start the test empty.

#### Scenario: Asserted from the start
- **WHEN** a test that should fail is started from a scene the query holds on
- **THEN** the case fails, its page shows the one assert naming that entity, and once its data makes the query fire on it the case passes

#### Scenario: No scene asked for
- **WHEN** a request for a test of a query names no `scene`
- **THEN** the test is written empty
