## Purpose
Defines how an entity, or an entity with its subtree, is copied in the SemForge
editor and pasted into a test case: where it is offered, what a subtree is, what
a paste writes, asks and refuses, and what is said about what was left out.

## ADDED Requirements

### Requirement: Copy and paste are offered where entities and cases are
An entity's row in Entities & Test Cases and its card on a page SHALL offer copying the entity and copying it with its subtree. A test case's row, the rows in it and its page SHALL offer Paste; in the view, Paste SHALL be offered while a copy is held. The Main page SHALL NOT offer Paste. None of them SHALL be in the command palette.

#### Scenario: From a row to a case's row
- **WHEN** the user copies `urn:filter:1` from its row under Main and chooses Paste on the row of a test case
- **THEN** the case's file holds `urn:filter:1` as the main model has it, the view shows it in the case, and the main model is unchanged

#### Scenario: From a card to a case's page
- **WHEN** the user chooses Copy on the card of an entity and Paste on a case's page
- **THEN** the case holds the entity and its page shows it, without a question

#### Scenario: A copy that fails
- **WHEN** an entity was copied, then copying another one fails, and Paste is chosen
- **THEN** nothing is written, a message says there is nothing to paste, and the view's rows do not offer Paste

#### Scenario: Paste in the main model
- **WHEN** the user chooses Paste on a row under Main
- **THEN** nothing is written, and a message says Paste works in a test case

### Requirement: Copy and paste by keyboard
With the list of Entities & Test Cases focused, Ctrl/Cmd+C SHALL copy the entity of the selected row, Ctrl/Cmd+Shift+C copy it with its subtree, and Ctrl/Cmd+V paste into the case of the selected row; not while text is typed. On a case's page, Ctrl/Cmd+V SHALL paste into the case, except in a text field and for a key that is held down.

#### Scenario: Keys in the view
- **WHEN** an entity's row is selected and Ctrl+C is pressed, then a case's row is selected and Ctrl+V is pressed
- **THEN** the case holds the entity

#### Scenario: Ctrl+V on a case's page
- **WHEN** Ctrl+V is pressed on a case's page, and again in its filter's text field
- **THEN** the first pastes into the case, and the second is left to the text field

### Requirement: A row dragged onto a case is copied there
Dropping an entity's row of Entities & Test Cases onto a test case, or a row in it, SHALL paste that entity alone into that case, as Paste does, and SHALL keep what was copied before. Dropped elsewhere, it SHALL write nothing and say where it can be dropped.

#### Scenario: Dropped on a case
- **WHEN** `urn:workpiece:1` was copied, and the row of `urn:filter:1` is dropped on a case
- **THEN** the case holds `urn:filter:1` and not `urn:workpiece:1`, and Paste afterwards pastes `urn:workpiece:1`

#### Scenario: Dropped on the main model
- **WHEN** an entity's row is dropped on a row under Main
- **THEN** nothing is written, and a message says to drop it on a test case

### Requirement: A copy is a snapshot
What is pasted SHALL be what the entities were when they were copied. One copy SHALL be pasteable into several cases, also after the package was loaded again. A copy SHALL replace the one held before from when it starts; a copy that fails SHALL leave nothing to paste.

#### Scenario: The original goes
- **WHEN** `urn:filter:1` is copied, then removed from the main model, then pasted
- **THEN** the case holds it as it was when copied

#### Scenario: The package is loaded again
- **WHEN** an entity is copied, the package is loaded again, and it is pasted into a case
- **THEN** the case holds the entity

### Requirement: The types' shapes decide what a child is
Copying with subtree SHALL take the entity, its children, their children and so on. A relationship, or a sub-attribute's, that the shapes of the entity's types or of types above them declare, applied shapes and connectives included, SHALL lead to children when such a shape names the reference type (`base:hasReferenceType`) OPC UA `HasChild` or one below it, by the knowledge or the OPC UA core; else SHALL NOT.

#### Scenario: A hierarchy of an OPC UA package
- **WHEN** the pump of an OPC UA package, whose shapes name `HasComponent` and the like, is copied with its subtree and pasted into a case of the package
- **THEN** the case holds the pump, its groups and all that is below them, and shows them

#### Scenario: A reference type of a companion specification
- **WHEN** a shape names a reference type that the knowledge puts below `HasChild` over another one
- **THEN** what the relationship leads to is copied

#### Scenario: A reference that is no child's
- **WHEN** a relationship's shape names `Organizes`, or names no reference type
- **THEN** what it leads to is not copied

#### Scenario: A relationship to several entities
- **WHEN** a child relationship has several objects, several instances or a list of objects
- **THEN** each of them is copied

### Requirement: Other shapes decide an undeclared relationship
A relationship that the shapes of the entity's types do not declare SHALL be decided by the other shapes of the package that declare it: it SHALL lead to children when one of them names `HasChild` or a reference type below it, else SHALL NOT.

#### Scenario: Declared for another type
- **WHEN** an entity has a relationship its type does not declare, and another type's shape declares it with `HasComponent`
- **THEN** what it leads to is copied

### Requirement: The data decides what no shape declares
In a package whose shapes name reference types, a relationship that no shape declares SHALL lead to a child when the target is defined and no other entity points at it, where the entity or the target is written. Copying SHALL say how many children were taken that way. In a package whose shapes name none, it SHALL NOT be followed.

#### Scenario: Only this entity points at it
- **WHEN** an entity points by an undeclared relationship at one entity nothing else points at, and at another that something else points at
- **THEN** the first is copied and counted as read off the data, and the second is said to be pointed at and not copied

#### Scenario: A case's entity and the main model
- **WHEN** an entity of a case points by an undeclared relationship at an entity of the main model that another entity of the model points at
- **THEN** it is not copied

#### Scenario: A package without a hierarchy
- **WHEN** an entity of a package whose shapes name no reference type is copied with its subtree
- **THEN** the entity alone is copied, and what it points at is said not to be copied

### Requirement: Each entity is copied once
A subtree SHALL hold each entity once, so that circles end. It SHALL be found for a case in the case, the files it includes and then the main model; for an included file in that file and then the main model; else in the main model. A case that is another case's file by a link SHALL be read with the files it includes itself. Of an id defined more than once among those of one kind, the first SHALL be copied, that of the row's own file before others, and copying SHALL name it.

#### Scenario: A circle
- **WHEN** a child points back at the entity it is below
- **THEN** copying ends, and each is copied once

#### Scenario: An included child
- **WHEN** an entity of a case is copied with its subtree and a file the case includes defines its child
- **THEN** the child is copied as that file defines it, not as the main model does

#### Scenario: Two definitions
- **WHEN** two model files define an id, and it is copied from the row of the second
- **THEN** the second file's definition is copied, and the id is named as defined more than once

#### Scenario: A case that is a link to another's file
- **WHEN** a case without includes is a link to the file of a case that includes `urn:cartridge:1`, and an entity is copied with its subtree from the first
- **THEN** `urn:cartridge:1` is copied as the main model has it

### Requirement: What was left out is said
Copying and pasting SHALL say how many children are written nowhere, and how many entities are pointed at otherwise and not copied; pasting SHALL also say which entities, or how many, were left as the case or its included files have them.

#### Scenario: A child written nowhere
- **WHEN** a child relationship leads to an id that no file of the copy defines
- **THEN** copying and pasting say that one child is written nowhere, and the rest is copied and pasted

### Requirement: Paste asks before it replaces
When the case has a pasted entity with other values, Paste SHALL ask whether to replace it, and paste only the others, or nothing, when it is not. A replaced entity SHALL keep its place in the file. A replaced entity SHALL have the id as copied. The order of keys and the spelling of an id SHALL be no difference; the type of a value SHALL be one. When nothing changes, the file SHALL NOT be written.

#### Scenario: Replaced
- **WHEN** the case has `urn:filter:1` with another strength, and the user pastes it and chooses Replace
- **THEN** it has the copied values, once, in its place

#### Scenario: An id the case spells otherwise
- **WHEN** an entity is copied with a prefix in its id, and the case has it by its whole IRI, with other values
- **THEN** Paste asks, naming both spellings, and the case has it once after Replace, with the id as copied; with the same values nothing is written

#### Scenario: Only the others
- **WHEN** two entities are pasted, the case has one with other values, and the user chooses to paste only the other
- **THEN** the first is unchanged and the second is added

#### Scenario: Not answered
- **WHEN** the question is dismissed
- **THEN** the case is unchanged

#### Scenario: Pasted twice
- **WHEN** the same copy is pasted into a case again
- **THEN** the file is not written, and a message says the case has it just like that

### Requirement: The question is what the answer does
What Paste says and refuses before its question SHALL be what it writes and refuses with the answer, judged with Replace on the case as it is once replaced.

#### Scenario: The question and the answer
- **WHEN** Paste asks, and Replace is chosen
- **THEN** what is written is what the question named, and a paste that is refused is refused before the question

### Requirement: What a case includes is left
Paste SHALL write into the case's own file only; a file that holds one object SHALL stay one object while it holds one entity. An entity that a file the case includes has, and the case's own file has not, SHALL be left as it is there, and Paste SHALL say so. When other cases include the case's own file, Paste SHALL name them and ask before writing; a case that is the same file by a link SHALL count as one of them, and what it includes as included.

#### Scenario: An included entity
- **WHEN** a case includes a file with `urn:cartridge:1`, and `urn:cartridge:1` and `urn:filter:9` are pasted
- **THEN** only `urn:filter:9` is written, and Paste says the other is in a file the case includes

#### Scenario: A case of one object
- **WHEN** a case's file is one object, and its entity is replaced by a paste
- **THEN** the file is one object still, and a list once a second entity is pasted

#### Scenario: A case that others include
- **WHEN** another case includes the case pasted into, and the question is not confirmed
- **THEN** nothing is written

#### Scenario: Two cases of one file
- **WHEN** a case is a link to another case's file, which includes a file with `urn:cartridge:1`, and `urn:cartridge:1` is pasted into the first
- **THEN** it is left, and the other case is named as sharing the file

### Requirement: A pasted context names the same file
A relative `@context` of a pasted entity SHALL be rewritten to name the same file from the case's folder; URLs, absolute paths and inline contexts SHALL be kept. Ids and all other content SHALL be written as they are in the file copied from. An id SHALL name the IRI its context gives it, and one with a prefix its context leaves open the IRI the package's names give it, for finding children and for comparing with the case.

#### Scenario: A relative context
- **WHEN** an entity with `"@context": "context.jsonld"` at the package root is pasted into a case in `examples/<suite>/bad/`
- **THEN** it has `../../../context.jsonld` there, and the original keeps `context.jsonld`

#### Scenario: Ids written in other ways
- **WHEN** an entity whose id is relative, written with a prefix, or holds special characters is copied with its subtree and pasted
- **THEN** its children are found, and its id is written as it was

#### Scenario: A prefix only the package names
- **WHEN** an entity's id has a prefix that its context leaves open and `kms.yaml` names, and the case has it by its whole IRI with other values
- **THEN** Paste asks to replace it, and a child pointed at by either spelling is found

### Requirement: A paste that cannot be right is refused
Paste SHALL be refused, with a message that says why and the case unchanged, when the copy was taken in another package, what is pasted is not a copy of entities, the file is no test case of the package or is one of the main model's, is not valid JSON or has unsaved edits, or the case has changed since the question. Copying SHALL be refused for an entity that is gone, and from a file that is no data file of the package. A paste SHALL write the case file whole or not at all.

#### Scenario: Another package
- **WHEN** an entity is copied in one package, another package is opened, and Paste is chosen on a case of it
- **THEN** nothing is written, and the message says it was copied in another package and which

#### Scenario: Unsaved edits
- **WHEN** the case's file is open with unsaved edits and Paste is chosen
- **THEN** nothing is written, and the message says to save or discard them

#### Scenario: A case that is a main model file
- **WHEN** a case's file is a link to a file of the main model and Paste is chosen on it
- **THEN** nothing is written, and the message says it is a file of the main model

#### Scenario: Changed since the question
- **WHEN** the case, or a file it includes, changes while the question is open, and it is answered
- **THEN** nothing is written, and the message says the case was changed meanwhile

#### Scenario: A write that fails
- **WHEN** writing the case's file fails
- **THEN** the file is as it was, and nothing is left beside it

### Requirement: Entities inside a graph are refused
Copying and Paste SHALL be refused, with a message that names the file and says to write its entities as a list, when a file they would read holds entities inside `"@graph"`: for copying the case, the files it includes or the included file, and the main model's files; for Paste the case and the files it includes. Nothing SHALL be written.

#### Scenario: A paste beside a graph
- **WHEN** the case's file, or one it includes, holds its entities inside `"@graph"`, and Paste is chosen on the case
- **THEN** nothing is written, and the message names that file and `"@graph"`

#### Scenario: A copy beside a graph
- **WHEN** an entity of a case is copied, and the case's file, one it includes or a main model file holds its entities inside `"@graph"`
- **THEN** nothing is copied, and the message names that file and `"@graph"`

### Requirement: Entities written in a relationship are refused
Copying and Paste SHALL be refused, as for `"@graph"`, when a file they would read holds an entity written in the object of a relationship, a sub-attribute's included; the message SHALL name the file, the entity it is in and the one written there. A reference and a value of a Property, JsonProperty or VocabProperty SHALL NOT count.

#### Scenario: An entity in a relationship
- **WHEN** a file the case includes has an entity whose relationship has `{"id": "urn:inside:1", "type": …}` as its object, and an entity is copied from the case or pasted into it
- **THEN** nothing is copied or written, and the message names the file, the entity and the relationship's object

#### Scenario: Values that hold objects
- **WHEN** an entity has a Property, JsonProperty or VocabProperty whose value is an object with an `id` and a `type`, or a relationship's object is only a reference `{"@id": …}`
- **THEN** it is copied and pasted as any other
