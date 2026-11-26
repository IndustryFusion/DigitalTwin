## MODIFIED Requirements

### Requirement: Pages open their entities as a graph
The entity bar of the Main model page and of a test case page SHALL offer the views **Graph** and **All**, in this order. A page SHALL open on Graph unless All was the view last shown on it. All SHALL show every entity of the page as a card, file by file. When a page is opened at an entity or attribute, or a violation in its list is clicked, it SHALL show All with that card or row in view; revealing an entity SHALL show Graph.

#### Scenario: First opening of the Main model page
- **WHEN** the Main model page is opened for the first time
- **THEN** the entity bar shows Graph selected and All beside it, and the graph of the entities is shown

#### Scenario: Opened at an entity
- **WHEN** the Main model page is opened from the row of entity `urn:workpiece:1` in Entities & Test Cases
- **THEN** All is shown and the card of `urn:workpiece:1` is in view and marked

#### Scenario: A violation in the list
- **WHEN** a violation of attribute `hasWidth` of an entity is clicked in the violation list while Graph is shown
- **THEN** All is shown and the row `hasWidth` of that entity's card is in view and marked

#### Scenario: Revealed in the graph
- **WHEN** Reveal in graph view is chosen on the row of `urn:workpiece:1` while All was the page's last view
- **THEN** Graph is shown with the path to `urn:workpiece:1`
