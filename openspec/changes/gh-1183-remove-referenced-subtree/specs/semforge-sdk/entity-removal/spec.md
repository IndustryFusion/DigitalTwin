# semforge-sdk/entity-removal Delta

## RENAMED Requirements

- FROM: `### Requirement: Remove with subtree is offered on entity rows`
- TO: `### Requirement: Remove with subtree is offered on entity rows and reference rows`

## MODIFIED Requirements

### Requirement: Remove with subtree is offered on entity rows and reference rows
An entity's row in Entities & Test Cases SHALL offer Remove with subtree… directly below Remove entity…, in a test case's own file, in a file that cases include, and in the main model. A reference row SHALL offer it too: the row of a Relationship's instance, of one of its `datasetId`s, or of a Relationship attribute with one instance; there it removes the entity the row points at. It SHALL NOT be offered on other rows, nor in the command palette.

#### Scenario: From a row
- **WHEN** the user chooses Remove with subtree… on an entity's row and confirms
- **THEN** the entity and its subtree are gone from the file it is written in, and the view no longer shows them there

#### Scenario: Not an entity
- **WHEN** the rows of an entity's type, of a Property, or of a Relationship attribute with several instances are right-clicked, or the command palette is searched
- **THEN** Remove with subtree… is not offered

#### Scenario: From a reference row
- **WHEN** the user chooses Remove with subtree… on the row of one `datasetId` of a Relationship with several instances and confirms
- **THEN** the entity it points at and that entity's subtree are gone, that one instance is gone from the parent, and the other instances and their entities stay

#### Scenario: From the case page
- **WHEN** the user chooses "Remove what … points at, with its subtree" in the row menu of a Relationship's row on a case page and confirms
- **THEN** the same is removed as from that reference row in Entities & Test Cases

## ADDED Requirements

### Requirement: Removing an attribute says how many instances go
Remove… on the row of an attribute with several instances SHALL ask whether to remove all of them, naming their number. The case page's removals SHALL say what each takes: only one reference, or all instances of the attribute.

#### Scenario: Several instances
- **WHEN** the user chooses Remove… on the row of an attribute with 15 instances
- **THEN** the question asks whether to remove all 15 instances of it

#### Scenario: Only this reference
- **WHEN** the row menu of one instance of a Relationship is opened on a case page
- **THEN** its removal of that instance says that only this reference goes and the entity stays
