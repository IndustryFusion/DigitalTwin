# semforge-sdk/test-cases Specification

## Purpose
Defines how SemForge's New test case… starts a test case from the whole main
model of a package: what the new case file holds, how it is declared and run,
and what its description says, so that a case can vary the model's scene
without changing the model.

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
