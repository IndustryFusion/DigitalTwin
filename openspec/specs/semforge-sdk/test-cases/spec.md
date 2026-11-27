# semforge-sdk/test-cases Specification

## Purpose
Defines SemForge's test cases: how New test case… starts one from the whole
main model of a package (what the new case file holds, how it is declared and
run, and what its description says, so that a case can vary the model's scene
without changing the model), and when a case that should fail passes: only
once what fires is asserted as its reason, which an author names, adds and
removes in the editor, for a list as for a single value.

## Requirements

### Requirement: New test case offers the whole main model as a start
New test case… SHALL offer **The whole main model** as a start, beside a copy of a case, an entity of the model, a new entity of a type and an empty file, whenever the package has a main model. It SHALL NOT be offered for a package without a main model, and choosing it SHALL ask for nothing more than the case's name. The name suggested SHALL be one no case or file in the target folder has: `whole-model`, else `whole-model-2`, `whole-model-3` and so on.

#### Scenario: A package with a main model
- **WHEN** the user runs New test case… in a package with a main model and has chosen a suite and whether the case should conform or violate
- **THEN** the starts offered include The whole main model, which names the model's file, or the number of its files

#### Scenario: A package without a main model
- **WHEN** the user runs New test case… in a package whose main model has no file
- **THEN** The whole main model is not offered, and a request for that start is refused with a message saying the package has no main model

#### Scenario: The suggested name is free
- **WHEN** the target folder already has `whole-model.jsonld` and `whole-model-2.jsonld`
- **THEN** the name suggested is `whole-model-3`

### Requirement: The case holds the documents of all model files
A case started from the whole main model SHALL hold, written into its own file, every document of every file of the main model, unchanged except for its context (below) and in the order the package loads them. The case SHALL include no model file. Editing the case SHALL NOT change any model file, and later edits of the model SHALL NOT change the case.

#### Scenario: A model of several files
- **WHEN** a case is started from the whole main model of a package whose model is two files
- **THEN** the case file holds the documents of the first file followed by those of the second, and its declaration has no include

#### Scenario: The case is a snapshot
- **WHEN** a case is started from the whole main model, and afterwards the model file and the case file are each edited
- **THEN** the case keeps its content when the model changes, and the model keeps its content when the case changes

### Requirement: A relative context names the same file from the case
In a case started from the whole main model, a relative `@context` (a string, or an entry of an `@context` list) SHALL be rewritten to name the same file from the case's folder. URLs, absolute paths and inline context objects SHALL be kept as written.

#### Scenario: A model with a relative context
- **WHEN** the model's documents name `"@context": "context.jsonld"` at the package root, and a case is started from the whole main model in `examples/<suite>/good/`
- **THEN** the case's documents name `../../../context.jsonld`, the case loads, and the model keeps `context.jsonld`

### Requirement: Ids shared by model files are named
When more than one model file defines the same id, a case started from the whole main model SHALL hold each definition, and the editor's message after writing SHALL name those ids.

#### Scenario: Model files that share an id
- **WHEN** two model files both define the entity `urn:x:1` and a case is started from the whole main model
- **THEN** the case holds both definitions, and the message after writing names `urn:x:1` as defined by more than one model file

### Requirement: The case is declared and run as the other starts
A case started from the whole main model SHALL be written to the chosen suite's `good/` folder and declared there with `expect: valid` when it should conform, or to `bad/` and declared with `expect: invalid` when it should violate, and run once; its case page SHALL open with the outcome. The case file SHALL be written whole or not at all, and when anything fails after it is written and before the outcome is reported, the file and its declaration SHALL be removed again.

#### Scenario: A good case from a conforming model
- **WHEN** a case that should conform is started from the whole main model of a model that conforms
- **THEN** it is declared `expect: valid` in the suite's `good/expectations.yaml`, it passes, and its description says it was started from the whole main model, which conforms, as a snapshot

#### Scenario: A failure after declaring
- **WHEN** the run after declaring the case fails with an error
- **THEN** neither the case file nor its declaration remains, and the suite's `expectations.yaml` is as it was before

### Requirement: The description says what the case still needs
When no description is given, the declaration of a case started from the whole main model SHALL say that it was started from the whole main model and whether that model conformed. For a bad case from a conforming model it SHALL say that the case fails until its data is edited; for a good case from a violating model, that it fails until its data conforms; for a bad case from a violating model, that the model violates already. A description given SHALL be kept as given.

#### Scenario: A bad case from a conforming model
- **WHEN** a case that should violate is started from the whole main model of a model that conforms
- **THEN** it is declared `expect: invalid`, it fails with no violation, and its description says the model conforms and the case fails until its data is edited

#### Scenario: A good case from a violating model
- **WHEN** a case that should conform is started from the whole main model of a model that violates
- **THEN** it fails, its description says the model violates and the case fails until its data is edited so it conforms, and the editor's message says it still violates as the main model does

#### Scenario: A description given
- **WHEN** a case is started from the whole main model with a description given
- **THEN** its declaration carries that description unchanged

### Requirement: The description is neutral until the run decides
Until its one run has decided, and when the case does not load, the description of a case started from the whole main model SHALL be "Started from the whole main model."

#### Scenario: A good case that fails for another reason
- **WHEN** a case that should conform is started from the whole main model and fails without a violation, for example because it does not load
- **THEN** the editor's message says it does not pass yet and lists its failures, and its description stays "Started from the whole main model."

### Requirement: New test asks whether the attribute should conform or fail
New test… of an attribute SHALL offer exactly two kinds of test, whatever constraints the attribute has: one that should conform and one that should fail. It SHALL then ask only for the case's name, suggesting one.

#### Scenario: An attribute with a list
- **WHEN** the user runs New test… on an attribute whose value has an `sh:in` list
- **THEN** the two kinds Should conform and Should fail are offered, and nothing else

### Requirement: A failing test starts from valid data without a reason
A test that should fail SHALL be written with the same data as one that should conform, declared `expect: invalid` in its suite's `bad/` folder without an assert, and run once. It SHALL fail, its description SHALL say that it fails until its data is edited and that is asserted, and its case page SHALL open.

#### Scenario: Written and failing
- **WHEN** the user writes a test that should fail for an attribute with an `sh:in` list
- **THEN** the case's value is one the list allows, the case asserts nothing, and it fails

#### Scenario: Finished
- **WHEN** the value of that case is changed to one outside the list, and the `sh:in` constraint that then fires is asserted on the case page
- **THEN** the case passes

#### Scenario: Broken but without a reason
- **WHEN** the value of that case is changed to one outside the list and nothing is asserted
- **THEN** the case still fails, and the only failure says that it asserts nothing

### Requirement: A conforming test uses a value the list allows
A test that should conform, written for an attribute whose value has an `sh:in` list and that no scene provides, SHALL carry a value of that list in the form that compares equal to it: text, number, boolean, typed literal or IRI.

#### Scenario: Lists of each kind
- **WHEN** a test that should conform is written for an attribute with the list `"red", "green"`, `1, 2`, `20.5, 21.5` or `true`, with or without the matching datatype
- **THEN** the case passes

### Requirement: The value picker offers the list
Editing the value of an attribute with an `sh:in` list in a case SHALL offer the items of the list, each written so that it compares equal to the list's item, and SHALL accept any other value typed.

#### Scenario: Picked from the list
- **WHEN** the value of an attribute with the list `"1", "true"` is edited and the item `1` is picked
- **THEN** the text `1` is written and the list is not violated

### Requirement: The test case page says when a reason is missing
The page of a case that expects a violation and asserts nothing SHALL say that the case fails because it has no reason yet, and how to name one.

#### Scenario: No reason yet
- **WHEN** the page of an invalid case without asserts is opened
- **THEN** it says that the case has no reason yet and fails

### Requirement: Any constraint that judges the case can be asserted
The test case page of an invalid case SHALL offer to add an assert, chosen from every constraint the validation judged one of the case's entities by and the case does not assert yet, those that fire first. A constraint that holds now SHALL be offered too; asserted, the case fails until it fires.

#### Scenario: A reason named before it fires
- **WHEN** an assert is added for a constraint that holds in the case
- **THEN** the case fails until its data is edited so that the constraint fires, and passes then

#### Scenario: Already asserted
- **WHEN** a constraint is asserted on an entity of the case
- **THEN** it is not offered for that entity again

### Requirement: Every assert can be removed
The test case page SHALL offer to remove each assert of the case.

#### Scenario: The last assert removed
- **WHEN** the only assert of a passing invalid case is removed on its page
- **THEN** the case asserts nothing and fails

### Requirement: The tests about an attribute are listed with it
The attribute editor SHALL list the test cases about its attribute in the shape that declares it: those in which one of its constraints fires or is asserted, and those that have the attribute. Each entry SHALL say whether the case passes and what it asserts or what fires, open the case's page, and offer to delete the case. The list SHALL follow a validation run that ends while the editor is open, without redrawing the rest of the editor.

#### Scenario: A failing test in the list
- **WHEN** a test that should fail was written for an attribute and its validation has run
- **THEN** the attribute editor lists it as failing, and cases without the attribute are not listed

#### Scenario: Deleted from the attribute editor
- **WHEN** the user deletes a listed case and confirms
- **THEN** its file and its declaration are gone

### Requirement: Deleting a case is a visible action
The test case page SHALL show Clone, Rename and Delete as buttons, and the case lists of the type and shape pages SHALL offer Delete on each case. Each SHALL ask before deleting, as the case's context menu does.

#### Scenario: Deleted from the type page
- **WHEN** the user runs Delete on a case in the type page's list and confirms
- **THEN** the case's file and its declaration are gone

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

### Requirement: A test started from a scene is declared as before
A test that should conform started from a scene SHALL NOT start from a case that is expected to violate; a test that should fail started from a scene SHALL assert that the query fires on that entity, and SHALL fail until it does. Without `scene`, a request SHALL start the test empty.

#### Scenario: Asserted from the start
- **WHEN** a test that should fail is started from a scene the query holds on
- **THEN** the case fails, its page shows the one assert naming that entity, and once its data makes the query fire on it the case passes

#### Scenario: No scene asked for
- **WHEN** a request for a test of a query names no `scene`
- **THEN** the test is written empty

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

### Requirement: New test case offers an empty file first
New test case… SHALL list An empty file first among its starts, saying that its entities are pasted from Main, before a copy of a case, the whole main model, an entity of the model and a new entity of a type.

#### Scenario: The first start
- **WHEN** the user runs New test case… and has chosen a suite and whether the case should conform or violate
- **THEN** An empty file is the first start offered
