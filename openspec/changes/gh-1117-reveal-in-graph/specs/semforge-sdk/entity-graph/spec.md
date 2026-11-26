## Purpose
Defines how the SemForge editor finds an entity in the entity graph of the Main
page or a test case page: where Reveal in graph view is offered, which page it
opens, what the graph shows of the path to the entity, and how the path behaves
when there are many, when there is a circle, and when the page is redrawn.

## ADDED Requirements

### Requirement: Reveal in graph view is offered on an entity's id
Reveal in graph view SHALL be offered on the right-click menu of an entity's row and of a violation's row in Entities & Test Cases, of an instance's and a use's row in Knowledge, and of every entity id on the Main, test case, type and shape pages, where a button beside the id SHALL offer it as well, usable by keyboard. It SHALL NOT be in the command palette.

#### Scenario: From a row of the main model
- **WHEN** the user chooses Reveal in graph view on the row of `urn:cartridge:1` under Main
- **THEN** the Main page shows the graph with the path to `urn:cartridge:1`, which is in view

#### Scenario: From a row of a test case
- **WHEN** the user chooses it on the row of `urn:filter:9` in the case `without-cartridge`
- **THEN** that case's page shows the path to `urn:filter:9`

#### Scenario: From an id on a page
- **WHEN** the user presses the button beside an id on the Main page, a relationship's value, a claim, a violation or a card of the graph
- **THEN** the page shows the path to that entity, and the keyboard focus is on the entity's card

#### Scenario: From a type page
- **WHEN** the user presses the button beside an instance on the Filter type page
- **THEN** the Main page shows the path to it

### Requirement: The page that holds the entity opens
A row under a test case SHALL open that case's page, a row under Main, a type page and the Main page the Main page, and an id of a case on a shape page that case's page. A row known only by its file SHALL open the case it is, the Main page for a file of the main model, else the first case that includes it; for another file it SHALL say so and open nothing. A page already showing SHALL show the path without being fetched again, keeping what it was opened at.

#### Scenario: A use in an included file
- **WHEN** the user chooses it on a use in Knowledge written in a file that a case includes
- **THEN** the page of a case that includes the file shows the path

#### Scenario: A file no page shows
- **WHEN** it is chosen for an entity of a file that is neither of the main model nor a case nor included
- **THEN** a warning names the file, and no page opens

#### Scenario: The page is open
- **WHEN** the Main page is open and the user chooses it on another id of that page
- **THEN** the page shows the new path, and the page is not requested from the server

### Requirement: Only the path to the entity is shown
The graph SHALL show only a path from a root of the graph down to the entity: of each card on the way, the row of the relationship it goes on by and the attributes that row is in; the entity's card whole and marked. A root SHALL be what the graph shows as one.

#### Scenario: Only the path
- **WHEN** a plant points at two pumps that both point at a motor, and the motor is revealed
- **THEN** the graph shows the plant with its relationship to the first pump, the pump with its relationship to the motor, and the motor with all its attributes, marked

#### Scenario: Inside a sub-attribute
- **WHEN** the relationship to the entity is a sub-attribute of `hasState`
- **THEN** the card on the way shows `hasState` and the relationship inside it

### Requirement: Several paths are stepped through
The paths SHALL be offered shortest first, stepped through forward and back, with how many there are; at most 20 SHALL be shown, and the count SHALL say "or more" only when there is another path or the search was bounded with paths left to look at. The rest of a card on the way SHALL be shown on request, and Show the whole graph SHALL show the graph as it was before.

#### Scenario: The next path
- **WHEN** the motor of the two pumps is revealed and the user steps forward
- **THEN** the path through the second pump is shown, counted "2 of 2", and the step button keeps the focus

#### Scenario: The rest and the whole graph
- **WHEN** the user asks for the rest of the plant's card, then for the whole graph
- **THEN** the plant's card shows all its attributes, then the graph shows its roots with what was open before; the button for the rest says "show the rest of this card"

### Requirement: Circles end and many entities stay usable
A path SHALL hold no entity twice. An entity of a circle that no other root leads into SHALL be shown by itself, and so SHALL a root. With very many paths the search SHALL stop at its bound and show a shortest path. A page of hundreds of entities SHALL show the path to any of them.

#### Scenario: A circle
- **WHEN** two entities point at each other and at nothing else, and each is revealed
- **THEN** the first is shown by itself, and the second below the first

#### Scenario: Very many paths
- **WHEN** an entity is reached by six layers of twelve entities each pointing at all of the next, and by one short cut
- **THEN** the short cut is shown first, its count saying "or more", within seconds

#### Scenario: Exactly twenty paths
- **WHEN** an entity has exactly twenty paths and a circle beside them that leads nowhere else
- **THEN** the count reads "1 of 20", without "or more"

#### Scenario: Hundreds of entities
- **WHEN** the model of the OPC UA pump slice, twenty times over (400 entities, ids without a scheme), is on the Main page and any of its entities is revealed
- **THEN** the path from its pump down to it is shown, and the entity is in view

### Requirement: The path stays when the page is redrawn
Drawn again -- by a validation, an edit, or its tab shown again with what it was first drawn with -- a page SHALL show what it last showed: path, which of them, cards shown whole, filter, view, scroll, without taking the focus, and SHALL NOT repeat a message or a jump. A path not seen yet SHALL be gone to again. If the entity is gone, the whole graph SHALL be shown. A path left SHALL stay left.

#### Scenario: A validation redraws the page
- **WHEN** the second path to the motor is shown, the rest of a card was asked for, and the page is redrawn
- **THEN** the same path and the same cards are shown, and the focus stays where it was

#### Scenario: Its tab is shown again
- **WHEN** a page opened on the path to the motor was asked since for the path to the drive, and its tab is shown again
- **THEN** the path to the drive is shown, not the one to the motor

#### Scenario: A filter set on a path
- **WHEN** a path is shown, the user filters by id, and the page is redrawn
- **THEN** the filter is still set, and no path is shown

#### Scenario: A reveal that failed
- **WHEN** an id not on the page was revealed, and the page is redrawn
- **THEN** nothing is said again, and the page does not move

#### Scenario: The entity is gone
- **WHEN** the revealed entity is removed and the page is redrawn
- **THEN** the page shows the whole graph

#### Scenario: Opened at an entity, then revealed
- **WHEN** the page was opened at `urn:p1`, the user reveals the motor on it, and the page is redrawn
- **THEN** the path to the motor is shown, not the card of `urn:p1`

### Requirement: The path is left for another question
Choosing Graph or All, filtering, clicking a violation in the list, or opening the page at an entity SHALL leave the path. Revealing SHALL clear the filter.

#### Scenario: A filter
- **WHEN** a path is shown and the user filters by id
- **THEN** the graph shows the matching entities as roots, and no path

### Requirement: An entity not on the page is said
Revealing an id that no entity of the page has SHALL leave the page as it is and SHALL say that the entity is not on the page.

#### Scenario: Not on the page
- **WHEN** an id a relationship points at but no entity of the page has is revealed
- **THEN** a message says it is not on this page, and the page shows what it showed

### Requirement: Ids are matched and shown as written
An id SHALL be found as the page's files write it, and as the package's names spell it out when it has a prefix; also when it has no scheme, is relative, or holds quotes, angle brackets or ampersands. A use in Knowledge SHALL name it as written, in each file as that file writes it. A relationship to a list SHALL offer no reveal. An id SHALL be shown as text and SHALL NOT change the page.

#### Scenario: A prefixed id from Knowledge and a type page
- **WHEN** a case writes an entity as `iffBaseEntities:filter9` and its use in Knowledge, or its id spelled out as a type page has it, is revealed
- **THEN** the case's page shows the path to `iffBaseEntities:filter9`

#### Scenario: A relative id from a type page
- **WHEN** the pump of the OPC UA slice, whose id has no scheme, is revealed from its type page
- **THEN** the Main page shows it, a root by itself

#### Scenario: A relationship to a list
- **WHEN** a relationship's object is a list of two ids
- **THEN** its row offers no Reveal in graph view, and one to `{"@id": "urn:filter:1"}` offers it for `urn:filter:1`

#### Scenario: An id with markup
- **WHEN** an entity's id holds `"><img src=x>` and it is revealed
- **THEN** the path ends at that entity, its id is shown as text, and nothing else is added to the page

### Requirement: Copy is offered on a page's id
The right-click menu of an entity's id on a page SHALL offer Copy entity and Copy with subtree of Entities & Test Cases, copying the entity as the page has it: on the Main or a test case page from the file of its card, on a shape page from its case, else from the main model.

#### Scenario: Copied from a page's id
- **WHEN** the user right-clicks `urn:filter:1` on the Main page, chooses Copy entity, and pastes on a test case's row
- **THEN** the case holds `urn:filter:1` as the main model has it
