# Spec Delta

## Purpose
Defines how SemForge keeps what a user comes back to at hand: the things
pinned and the places visited last, as things of the model rather than lines
of its files.

## ADDED Requirements

### Requirement: Pinned and recent are one list
**Pinned and recent…** SHALL be offered in the command palette, by a key, on SemForge's pages and in the overflow menu of Entities & Test Cases. It SHALL list what is pinned, in the order it was pinned, and after it the places visited last, the newest first, at most 15 of them. What is pinned and the page in front SHALL NOT be listed as recent. Each entry SHALL say what kind of thing it is and, for a thing of another package, that package. Choosing an entry SHALL open its page.

#### Scenario: Pinned before recent
- **WHEN** the shape `FilterShape` and the entity `urn:filter:9` of a case are pinned, and the pages of `Filter` and `Workpiece` were opened afterwards, the latter still in front
- **THEN** the list is FilterShape and `urn:filter:9` as pinned, and then recent places with `Filter` and neither `Workpiece` nor FilterShape

#### Scenario: Opening a pinned entity
- **WHEN** the user chooses the pinned entity `urn:filter:9` of the case `without-cartridge`
- **THEN** that case's page opens at `urn:filter:9`

#### Scenario: Nothing yet
- **WHEN** nothing is pinned and no page was visited
- **THEN** a message says so and how to pin

### Requirement: Pages, rows, attributes and queries can be pinned
A page of an entity type, shape, vocabulary class, test case, the main model or a SPARQL query SHALL be pinned and unpinned by a star at its top right, filled while it is pinned. A row that stands for an entity type, attribute, shape, query, vocabulary class, entity or test case SHALL be pinned and unpinned from its menu, and an attribute and a SPARQL query of a type page from their ⋯ menu.

#### Scenario: The star of a page
- **WHEN** the user pins the page in front and later unpins it
- **THEN** the star is filled after the first and empty after the second, and the list has the page as pinned only in between

#### Scenario: A row
- **WHEN** the user chooses Pin or unpin on the row of an entity twice
- **THEN** the entity is pinned after the first and not after the second

#### Scenario: A row that is no such thing
- **WHEN** pinning is run on a row that stands for none of these, such as a group
- **THEN** nothing is pinned and a message says what can be

### Requirement: Entities are pinned on pages and entries in the list
An entity's id on a page that has a context menu SHALL offer pinning and unpinning there. An entry of the list SHALL be taken out, or a recent one pinned, by its button.

#### Scenario: An id on a test case's page
- **WHEN** an entity's id on a test case's page has a context menu, and Pin or unpin is chosen there
- **THEN** that entity of that case is pinned

#### Scenario: A recent place pinned from the list
- **WHEN** the user uses the pin button of a recent entry
- **THEN** the entry is listed as pinned and no longer as recent

### Requirement: A pin names the thing
A pin SHALL name what it stands for in its package, not a line of a file: a type, shape, vocabulary class or term by its identifier, an attribute by its type and name, a test case by its file, and an entity by its id and the case that holds it, if one does. The same thing SHALL be pinned at most once. When a shape, a test case or a suite is renamed in SemForge, what is pinned or recent of it SHALL name the new one, entities of a renamed case or suite included.

#### Scenario: An edit above
- **WHEN** lines are added above a pinned shape in its file
- **THEN** the pin opens the same shape

#### Scenario: A renamed test case
- **WHEN** a pinned test case is renamed in SemForge
- **THEN** the pin names and opens the renamed case, under its new name

#### Scenario: An entity in a renamed suite
- **WHEN** an entity of a case is pinned and the case's suite is renamed in SemForge
- **THEN** the pin opens the entity in the case in the renamed suite

### Requirement: What is gone says so
An entry whose thing is not in its package any more SHALL be listed as not found when it is pinned, and not be listed when it is recent. Choosing it SHALL offer to search the views for its name or to take it out, and open no page. When the server does not answer, nothing SHALL be said to be gone.

#### Scenario: A deleted case
- **WHEN** a pinned test case is deleted and the user chooses it in the list and then takes it out
- **THEN** it was listed as not found, and is no longer pinned

#### Scenario: A package that is gone
- **WHEN** a pin's package is not there any more
- **THEN** its pins are listed as not found

#### Scenario: No answer
- **WHEN** the language server is not running
- **THEN** the pins are listed, none as not found

### Requirement: Pins are the user's
Pins and recent places SHALL be kept per workspace for the user, across window reloads, and nothing SHALL be written into the package.

#### Scenario: The package is untouched
- **WHEN** something is pinned, visited and unpinned
- **THEN** no file of the package changes
