# semforge-sdk/entity-removal Delta

## ADDED Requirements

### Requirement: Remove with subtree is offered on entity rows
An entity's row in Entities & Test Cases SHALL offer Remove with subtree… directly below Remove entity…, as Copy with subtree sits below Copy entity, in a test case's own file, in a file that cases include, and in the main model. It SHALL NOT be offered on other rows, and it SHALL NOT be in the command palette.

#### Scenario: From a row
- **WHEN** the user chooses Remove with subtree… on an entity's row and confirms
- **THEN** the entity and its subtree are gone from the file it is written in, and the view no longer shows them there

#### Scenario: Not an entity
- **WHEN** the rows of an entity's type or attributes are right-clicked, or the command palette is searched
- **THEN** Remove with subtree… is not offered

### Requirement: The subtree is the one Copy with subtree copies
Remove with subtree… SHALL remove, from the file of the row, the entity and every entity of its subtree written in that file: its children, theirs, and so on, as Copy with subtree takes them. A member of the subtree written in another file SHALL stay there. A member other than the entity itself that an entity outside the subtree points at SHALL stay, and so SHALL what is reached from the entity only through one that stays. An entity without children in the file SHALL be removed alone.

#### Scenario: Children and theirs
- **WHEN** a plasmacutter's filter and the filter's cartridge are its children by their references, and the plasmacutter is removed with its subtree
- **THEN** the plasmacutter, the filter and the cartridge are gone, and the other entities of the file stay in their order

#### Scenario: Written in another file
- **WHEN** a child of the entity is written in a file the case includes
- **THEN** that file is as it was, and the question names the child as kept

#### Scenario: Used by another entity
- **WHEN** a child of the entity is also pointed at by an entity outside the subtree
- **THEN** that child stays, and the question names it as kept

### Requirement: References to removed entities go with them
Unlike Remove entity…, Remove with subtree… SHALL take out, of every entity left in the file, each relationship object that is a removed entity: only that object, the instance when no object is left, and the attribute when no instance is left. Other instances and objects SHALL stay as they were.

#### Scenario: The parent's reference
- **WHEN** an entity with several children, one instance each by datasetId, has one of them removed with its subtree
- **THEN** only that child's instance is gone from the parent, and its other instances stay

### Requirement: A reference to a removed entity is found however it is written
An object SHALL count as a removed entity by its IRI, whether written whole, with a prefix of its context or relative, in sub-attributes, among several objects and in an object list, however the relationship's type and keys are written. An IRI another document of the file still defines SHALL NOT count as removed.

#### Scenario: However it is written
- **WHEN** one entity points at the removed one by its whole IRI, another by a prefix, and a third in a sub-attribute among several objects
- **THEN** all three lose that reference, the third keeps its other object, and an entity pointing at something else is as it was

#### Scenario: An object list
- **WHEN** a relationship's object list names the removed entity and another one
- **THEN** the list keeps the other one

#### Scenario: Still defined
- **WHEN** the removed entity's IRI is defined once more in the file under another spelling, and an entity points at it
- **THEN** that reference stays

### Requirement: The question says what removing the subtree touches
Before it removes, the editor SHALL ask, naming the entity and how many entities go, and SHALL say the other members that go, the references that go, the members kept and why, whether the file is of the main model or left without an entity, the other cases that use the file, and the cases asserting something on a removed entity. Dismissed, nothing SHALL be written.

#### Scenario: Asked first
- **WHEN** the user chooses Remove with subtree… on an entity with two children
- **THEN** the question says three entities go and names the two children and the references that go with them

#### Scenario: Dismissed
- **WHEN** the question is dismissed
- **THEN** no file is changed

### Requirement: Removing a subtree is refused as removing an entity is
Remove with subtree… SHALL be refused as Remove entity… is: when the file changed since the row was read, when it or what the question said changed while it was asked, while the file has unsaved edits, and for a file that is no model file, test case or included file of the package; and when a member of the subtree is written more than once in the file, as which one is meant cannot be told. It SHALL write the whole file or leave it as it was.

#### Scenario: Changed during the question
- **WHEN** the file is changed while the question is open, and it is confirmed
- **THEN** nothing is removed, and a message says so

#### Scenario: Changed since it was read
- **WHEN** the file's content is another than when the row was read
- **THEN** nothing is removed, and a message says the file has changed

#### Scenario: Unsaved edits
- **WHEN** the file is open in an editor with unsaved edits
- **THEN** nothing is removed, and a message asks to save or discard them

#### Scenario: Another file
- **WHEN** a removal with subtree names a file that is no model file, test case or included file of the package
- **THEN** it is refused, and the file is as it was

#### Scenario: Written twice
- **WHEN** a member of the subtree is written twice in the file
- **THEN** it is refused with a message naming it, and the file is as it was
