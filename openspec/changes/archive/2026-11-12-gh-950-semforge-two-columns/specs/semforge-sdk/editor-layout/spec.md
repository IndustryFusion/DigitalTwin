# Delta for SemForge SDK Editor Layout

## Purpose

Defines how the SemForge VS Code extension arranges its views in VS Code,
how each view says what it is, how the pages present the entities of a model
or test case, and how its commands are named and placed, so that the main
working views keep their space and the details stay one action away.

## ADDED Requirements

### Requirement: The main column holds the package and its data
The SemForge side bar SHALL contain exactly two views, in this order: **Package** and **Entities & Test Cases**.

#### Scenario: Opening a package
- **WHEN** a folder with a KMS package is opened and the SemForge side bar is shown
- **THEN** it shows the views Package and Entities & Test Cases and no other view

### Requirement: The details are a second container, shown on request
The views **Constraints by Type**, **SHACL Shapes as Written** and **Knowledge (Ontology)** SHALL be in a second container named **SemForge Details**. The container SHALL be hidden, its icon included, until the user runs **Show details**, which is offered in the Package view's title bar and in the command palette. **Hide details**, offered in the overflow menu of each of its views, SHALL hide it again. The last choice SHALL be kept per workspace across window reloads.

#### Scenario: Details hidden by default
- **WHEN** a workspace in which Show details was never run is opened
- **THEN** SemForge Details and its icon are not shown, and the Package view's title bar offers Show details

#### Scenario: Showing and hiding the details
- **WHEN** the user runs Show details, and later Hide details from the overflow menu of Constraints by Type
- **THEN** SemForge Details opens with its three views after the first, and is gone with its icon after the second

#### Scenario: The choice survives a reload
- **WHEN** the user runs Show details and reloads the window
- **THEN** SemForge Details is still available, and Show details is no longer offered in the Package view's title bar

### Requirement: A view says what it is in a hover
Each of the five views SHALL offer an ⓘ action in its title bar whose tooltip says what the view shows and what a click on a row opens; running it SHALL show the same text as a notification. A view SHALL NOT show this text as a message above its rows. The space above the rows SHALL be used only when the language server is not running, when there is no package, when a request failed, or while a validation runs.

#### Scenario: A healthy package
- **WHEN** a package loads without error and no validation is running
- **THEN** no view shows a message above its rows, and hovering the ⓘ of the Package view shows a text that starts with "This package:"

#### Scenario: The language server is not running
- **WHEN** the language server is not running
- **THEN** the Package view shows a message that says so and how to diagnose it

### Requirement: The Main model page explains its violations in a hover
On the Main model page the explanation of the violation list (that each violation is also in VS Code's Problems panel, and how to step through them) SHALL be the tooltip of an ⓘ beside the link that opens the Problems panel, not a paragraph.

#### Scenario: Main model page with violations
- **WHEN** the Main model page of a model with violations is opened
- **THEN** the violation list is preceded by an ⓘ and an "Open the Problems panel" link, and the explanation appears when hovering the ⓘ

### Requirement: Pages open their entities as a graph
The entity bar of the Main model page and of a test case page SHALL offer the views **Graph** and **All**, in this order. A page SHALL open on Graph unless All was the view last shown on that page. All SHALL show every entity of the page as a card, file by file. When a page is opened at one entity or attribute, or a violation in its list is clicked, the page SHALL show All and bring that entity's card or attribute row into view.

#### Scenario: First opening of the Main model page
- **WHEN** the Main model page is opened for the first time
- **THEN** the entity bar shows Graph selected and All beside it, and the graph of the entities is shown

#### Scenario: Opened at an entity
- **WHEN** the Main model page is opened from the row of entity `urn:workpiece:1` in Entities & Test Cases
- **THEN** All is shown and the card of `urn:workpiece:1` is in view and marked

#### Scenario: A violation in the list
- **WHEN** a violation of attribute `hasWidth` of an entity is clicked in the violation list while Graph is shown
- **THEN** All is shown and the row `hasWidth` of that entity's card is in view and marked

### Requirement: Every entity counts once
The filter's count ("N of M shown") and the jumps to an entity or attribute SHALL consider each entity of the page once, whether Graph or All is shown.

#### Scenario: Filtering while the graph is open
- **WHEN** a page with 3 entities, 2 of which violate, is opened from a violation count, so that only what violates is shown, while Graph is the page's view
- **THEN** the count reads "2 of 3 shown"

### Requirement: Menus name actions without the extension's prefix
Every command of the extension SHALL belong to the category SemForge, so that the command palette shows it as "SemForge: <title>" and menus and title bars show the title alone. No title SHALL start with "SemForge:". Titles SHALL be in sentence case and SHALL NOT start with a symbol such as "+"; a title that adds to an existing item SHALL start with "Add".

#### Scenario: Right-click on an entity
- **WHEN** the user right-clicks an entity in Entities & Test Cases
- **THEN** the menu offers "Add attribute", not "SemForge: Add Attribute"

#### Scenario: Command palette
- **WHEN** the user types "add attribute" in the command palette
- **THEN** the entry reads "SemForge: Add attribute"

#### Scenario: An attribute added to an entity type
- **WHEN** the user right-clicks an entity type in Constraints by Type
- **THEN** the menu offers "Add attribute…", not "+ Attribute"

### Requirement: Title bars hold what creates
A view's title bar SHALL show as buttons only its actions that create, the package selection, Show details and the ⓘ. Refreshing a view, and opening the package health and package settings pages, SHALL be in the view's overflow menu. "New attribute…" SHALL be offered in the title bar of Knowledge (Ontology) only.

#### Scenario: The Package view's title bar
- **WHEN** the Package view is shown with SemForge Details hidden
- **THEN** its title bar shows Select package, Show details, the ⓘ and the SemForge menu, and its overflow menu offers Open package health, Open package settings and Refresh package

#### Scenario: New attribute offered once
- **WHEN** SemForge Details is shown
- **THEN** New attribute… is a button in the title bar of Knowledge (Ontology) and not in that of Constraints by Type

### Requirement: The Package view stays short
When no package is found, only the Package view SHALL show the full explanation of what a package is; every other view SHALL show one line and the actions to create a package and to run the doctor. The Package view's Settings group SHALL start folded.

#### Scenario: A folder without a package
- **WHEN** a folder without a KMS package is opened
- **THEN** the Package view explains what a package is and offers New project…, Create a package here and Run the doctor, and Entities & Test Cases offers Create a package here and Run the doctor without that explanation

#### Scenario: Settings folded
- **WHEN** a package is opened
- **THEN** the Package view shows its Settings group folded and its Contents group unfolded
