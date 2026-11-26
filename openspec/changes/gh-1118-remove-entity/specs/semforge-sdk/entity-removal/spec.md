## Purpose
Defines how an entity is removed in the SemForge editor from the file it is
written in: where that is offered, what is asked, what is removed and what is
refused.

## ADDED Requirements

### Requirement: Remove entity is offered on rows and cards
An entity's row in Entities & Test Cases and its card on a page SHALL offer removing the entity: in a test case's own file, in a file that cases include, and in the main model. Rows that are not an entity's, a type's included, SHALL NOT offer it, and it SHALL NOT be in the command palette.

#### Scenario: From a row
- **WHEN** the user chooses Remove entity… on an entity's row and confirms
- **THEN** the entity is gone from the file it is written in, the other entities of the file and all other files are as they were, and the view no longer shows it there

#### Scenario: From a card
- **WHEN** the user chooses Remove… on an entity's card and confirms
- **THEN** the entity is gone from its file, and the page no longer shows it

#### Scenario: In the main model
- **WHEN** the user chooses Remove entity… on an entity's row under Main
- **THEN** the question says the file is of the main model, and confirmed, the entity is gone from it

#### Scenario: Not an entity
- **WHEN** the rows of an entity's type or attributes are right-clicked, or the command palette is searched
- **THEN** Remove entity… is not offered

### Requirement: The question says what the removal touches
Before it removes an entity, the editor SHALL ask, naming the entity and its file, and SHALL say the ids in that file that still point at it, the cases that assert something on it, the cases that use the file when others than the shown one do, and whether the file is of the main model, is left without an entity, or defines the entity once more. Dismissed, nothing SHALL be written.

#### Scenario: Something points at it
- **WHEN** `urn:cartridge:1` is removed from a file in which `urn:filter:1` points at it
- **THEN** the question names `urn:filter:1` as still pointing at it

#### Scenario: A file several cases use
- **WHEN** an entity is removed from a file that three cases include
- **THEN** the question names the three cases

#### Scenario: Asserted
- **WHEN** an entity is removed that a case asserts something on
- **THEN** the question names the case, and confirmed, the assert is as it was

#### Scenario: Dismissed
- **WHEN** the question is dismissed
- **THEN** no file is changed

### Requirement: References are found however ids are written
What points at the entity, the asserts on it and its other definitions SHALL be found by its IRI, whether an id is written whole, with a prefix of its context, or relative, in relationships of sub-attributes and in those with several objects or a list of them too. Only a relationship's object SHALL count as pointing at it, not a datasetId, a type or a Property's value. When the file's context cannot be had, the question SHALL say that what points at the entity is not known.

#### Scenario: A prefix and a whole IRI
- **WHEN** the entity `p:cut` is removed, and one entity points at it by its IRI, another by `p:cut`, and a third in a sub-attribute with several objects
- **THEN** the question names all three, by their ids as written

#### Scenario: Named, not pointed at
- **WHEN** other entities name the entity as a datasetId, a type or a Property's value, and one has it in a list relationship
- **THEN** the question names only the one with the list relationship

#### Scenario: Asserted by its IRI
- **WHEN** an entity is written with a prefix, and an assert names its IRI
- **THEN** the question names the assert's case

#### Scenario: Written again in another way
- **WHEN** a file defines one entity as `p:a` and again by its IRI, and the first is removed
- **THEN** the question says the file defines it once more, and the second stays

#### Scenario: No context
- **WHEN** an entity is removed from a file whose context does not exist
- **THEN** the question says that what points at it is not known, and confirmed, the entity is gone

### Requirement: The one that was meant is removed
When an id is written more than once in a file, the document the row or card stands for SHALL be removed, and the others SHALL stay. A request that does not say which one SHALL be refused.

#### Scenario: One of two
- **WHEN** a file has two entities of one id, and the first's row is removed
- **THEN** the second stays as it was

#### Scenario: Not said which
- **WHEN** an entity written twice in a file is to be removed by its id alone
- **THEN** it is refused with a message that it is written twice, and the file is as it was

### Requirement: What changed meanwhile is refused
When a file's content is another one than when the row or card was read, or the file or what the question said changed while it was asked, the removal SHALL be refused with a message and the view and page shown anew. While the file has unsaved edits in an editor, opened under any name, it SHALL be refused, also when they were made during the question.

#### Scenario: Changed since it was shown
- **WHEN** a file is changed on disk after an entity's row was read, and that row's entity is to be removed
- **THEN** nothing is asked or removed, and a message says the file has changed

#### Scenario: An older page
- **WHEN** a click arrives from a page that showed another content of the file
- **THEN** nothing is removed

#### Scenario: Another card at that place
- **WHEN** a click arrives for a card whose file, place or id is not that of the card now at its place on the page
- **THEN** nothing is removed, and a message says the page has changed

#### Scenario: Changed during the question
- **WHEN** the file, or an assert of a case that uses it, is changed while the question is open, and it is confirmed
- **THEN** nothing is removed, and a message says so

#### Scenario: Changed while it is written
- **WHEN** the file is changed after the removal was decided and before it is written
- **THEN** the file keeps that change, nothing is removed, and a message says so

#### Scenario: Unsaved edits
- **WHEN** the file is open in an editor with unsaved edits, through a link to it or by itself, on Windows also by a name in another case
- **THEN** nothing is removed, and a message asks to save or discard them

### Requirement: Files are written whole, and only those of the package
A removal SHALL write the whole file or leave it as it was, and SHALL keep a link a link. A file left without an entity SHALL hold an empty list, whether it was a list or one object, and stay declared. A file that is no main model file, declared case or included file of the package, that is not JSON, or that has its entities inside `"@graph"`, SHALL be refused.

#### Scenario: A write that fails
- **WHEN** writing the file fails
- **THEN** the file is as it was, and nothing is left beside it

#### Scenario: A link
- **WHEN** the case's file is a link to another file
- **THEN** the entity is gone from that file, and the link is still one

#### Scenario: The last entity
- **WHEN** the only entity of a case is removed
- **THEN** the file holds an empty list, the case's page shows no entity, and an entity can be added to it again

#### Scenario: Inside a graph
- **WHEN** an entity is to be removed from a file that has its entities inside `"@graph"`
- **THEN** it is refused with a message naming the file, and the file is as it was

#### Scenario: Another file
- **WHEN** a removal names a file that is no model file, test case or included file of the package
- **THEN** it is refused, and the file is as it was
