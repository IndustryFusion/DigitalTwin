# Spec Delta

## MODIFIED Requirements

### Requirement: The details are a second container, shown on request
The views **Constraints by Type**, **SHACL Shapes as Written** and **Knowledge (Ontology)** SHALL be in a second container named **SemForge Details**. The container SHALL be hidden, its icon included, until the user runs **Show details**, offered in the Package view's title bar and the command palette, or Search… (semforge-sdk/view-search). **Hide details**, offered in the overflow menu of each of its views, SHALL hide it again. The last choice SHALL be kept per workspace across window reloads.

#### Scenario: Details hidden by default
- **WHEN** a workspace in which neither Show details nor a search was ever run is opened
- **THEN** SemForge Details and its icon are not shown, and the Package view's title bar offers Show details

#### Scenario: Showing and hiding the details
- **WHEN** the user runs Show details, and later Hide details from the overflow menu of Constraints by Type
- **THEN** SemForge Details opens with its three views after the first, and is gone with its icon after the second

#### Scenario: The choice survives a reload
- **WHEN** the user runs Show details and reloads the window
- **THEN** SemForge Details is still available, and Show details is no longer offered in the Package view's title bar

#### Scenario: A search shows the details
- **WHEN** SemForge Details is hidden and the user runs Search…
- **THEN** SemForge Details is shown, as after Show details

### Requirement: A view says what it is in a hover
Each of the five views SHALL offer an ⓘ action in its title bar whose tooltip says what the view shows and what a click on a row opens; running it SHALL show the same text as a notification. A view SHALL NOT show this text as a message above its rows. The space above the rows SHALL be used only when the language server is not running, when there is no package, when a request failed, while a validation runs, or while a search is kept.

#### Scenario: A healthy package
- **WHEN** a package loads without error, no validation is running and no search is kept
- **THEN** no view shows a message above its rows, and hovering the ⓘ of the Package view shows a text that starts with "This package:"

#### Scenario: The language server is not running
- **WHEN** the language server is not running
- **THEN** the Package view shows a message that says so and how to diagnose it

#### Scenario: A search is kept
- **WHEN** a search for `hasStrength` is kept, a view has rows that fit and no validation is running
- **THEN** the message above that view's rows says the text searched for and how many rows fit, and is gone when the search is cleared

### Requirement: Title bars hold what creates
A view's title bar SHALL show as buttons only its actions that create, the package selection, Show details, the ⓘ and, on the four views that show the model, Search… and, while a search is kept, Clear the search. Refreshing a view, and opening the package health and package settings pages, SHALL be in the view's overflow menu. "New attribute…" SHALL be offered in the title bar of Knowledge (Ontology) only.

#### Scenario: The Package view's title bar
- **WHEN** the Package view is shown with SemForge Details hidden
- **THEN** its title bar shows Select package, Show details, the ⓘ and the SemForge menu, and its overflow menu offers Open package health, Open package settings and Refresh package

#### Scenario: New attribute offered once
- **WHEN** SemForge Details is shown
- **THEN** New attribute… is a button in the title bar of Knowledge (Ontology) and not in that of Constraints by Type

#### Scenario: Clear the search offered while searching
- **WHEN** no search is kept, and then one is
- **THEN** Entities & Test Cases, Constraints by Type, SHACL Shapes as Written and Knowledge (Ontology) show Search… in both cases and Clear the search only in the second, and the Package view shows neither
