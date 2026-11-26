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
