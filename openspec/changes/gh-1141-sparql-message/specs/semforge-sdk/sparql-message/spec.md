## Purpose
Defines how the SemForge editor shows, checks and edits the `sh:message` of a
SPARQL constraint, so that the message fits the query the platform compiles it
with.

## ADDED Requirements

### Requirement: The workbench shows the message with an action to edit it
The SPARQL workbench SHALL show, for a SPARQL constraint, its `sh:message` under the query's name with an **Edit message** action, or say "no sh:message" with a **+ Message** action when it has none. For a SPARQL rule it SHALL show no message and no such action.

#### Scenario: A constraint with a message
- **WHEN** the workbench shows a SPARQL constraint whose message is "Cutter running without running filter"
- **THEN** the page says that message and offers **Edit message**

#### Scenario: A constraint without a message
- **WHEN** the workbench shows a SPARQL constraint without `sh:message`
- **THEN** the page says it has no sh:message and offers **+ Message**

#### Scenario: A rule
- **WHEN** the workbench shows a SPARQL rule
- **THEN** it shows no message and offers no action to edit one

### Requirement: The menus open the message's field
The constraint's menu on the shape page, its SPARQL row's menu on the type page and the workbench's own menu SHALL offer **Edit message…**, or **+ Message…** for a constraint without a message, which opens the workbench on that constraint with the field open. A constraint without a message SHALL also have a **+ Message** button on its row of the shape page. None of them SHALL offer it for a SPARQL rule.

#### Scenario: From the shape page
- **WHEN** **Edit message…** is chosen in a SPARQL constraint's menu on the shape page
- **THEN** the workbench opens on that constraint with the field open, holding the message

#### Scenario: From the type page
- **WHEN** a SPARQL constraint's row menu on a type page is opened
- **THEN** it offers **Edit message…**, which opens the workbench with the field open

#### Scenario: A row without a message
- **WHEN** the shape page lists a SPARQL constraint without `sh:message`
- **THEN** its row has a **+ Message** button that opens the workbench with the field open

#### Scenario: No message for a rule
- **WHEN** the menu of a SPARQL rule is opened on the shape page or the type page
- **THEN** it offers neither **Edit message…** nor **+ Message…**

### Requirement: The type page says the message
A SPARQL constraint's row on the type page SHALL say its message, preferring one without placeholders, and a message with placeholders when it has no other.

#### Scenario: A message with variables
- **WHEN** a SPARQL constraint's only message is "Filter {?f} is off"
- **THEN** its row on the type page says "Filter {?f} is off"

### Requirement: The field offers the query's variables
While the message is edited, the field SHALL list the variables the query, as its editor holds it, selects: `$this` first, then the others in their order, `SELECT *` and `(… AS ?x)` as the query's parser reads them. Choosing one SHALL insert `{?name}` at the cursor. After `{?` and the start of a name, the variables that start with it SHALL stay highlighted and Tab SHALL insert the first of them.

#### Scenario: The variables listed
- **WHEN** the message of a constraint whose query is `SELECT $this ?v1 ?f ?v2 WHERE { … }` is edited
- **THEN** the field lists `$this`, `?v1`, `?f` and `?v2`, in this order

#### Scenario: Inserted by a click
- **WHEN** `?f` is chosen with the cursor after "Filter "
- **THEN** the field holds "Filter {?f}"

#### Scenario: Inserted by Tab
- **WHEN** "{?v" is typed and Tab is pressed
- **THEN** `{?v1}` replaces it

### Requirement: The field is saved by Enter and kept across a redraw
In the field, Enter and **Save message** SHALL save, Shift+Enter SHALL insert a new line and Esc SHALL cancel. A draft SHALL survive the page being drawn anew.

#### Scenario: Keys
- **WHEN** Shift+Enter, then Enter is pressed in the field
- **THEN** the first inserts a line break and the second saves the message

#### Scenario: A redraw
- **WHEN** the page is drawn anew while a draft is in the field
- **THEN** the field is open again and holds the draft

### Requirement: The preview is filled from a violating row
While the message is edited, the field SHALL show it filled from a violating row of the workbench's last run: each `{?x}` or `{$x}` by the row's value of `x`, the name compared as written. A placeholder the row has no value for SHALL stay as written and be marked. When no row of the run violates, the preview SHALL say so and how to get one.

#### Scenario: Filled
- **WHEN** the last run over a case had the violating row `this = urn:plasmacutter:1, f = urn:filter:1` and the message is "Filter {?f} is off for {$this}"
- **THEN** the preview says "Filter urn:filter:1 is off for urn:plasmacutter:1"

#### Scenario: A value the row lacks
- **WHEN** the message is "{?F} is off" and the row has `f` but no `F`
- **THEN** the preview shows "{?F}" as written, marked as not filled

#### Scenario: No violating row
- **WHEN** the last run returned no row
- **THEN** the preview says that no row violates and to choose a case that does

### Requirement: A message that does not fit the platform is warned about
A SPARQL constraint's message SHALL be warned about, while it is typed in the field, in the Problems panel and by `semforge check`, when it names a variable the query does not select (naming the selected one when only the case differs), holds `{?}` or `{$}`, writes a selected variable without `?` or `$` (as `{x}`), or holds an apostrophe. These SHALL be warnings: validation and saving SHALL go on.

#### Scenario: A variable the query does not select
- **WHEN** the message "it is {?nope}" is typed for a query that does not select `nope`
- **THEN** the field warns that `{?nope}` is not a variable the query selects, and saved, the Problems panel and `semforge check` warn the same on the message's line

#### Scenario: Only the case differs
- **WHEN** the message names `{?F}` and the query selects `f`
- **THEN** the warning names `{?f}` as the variable the query selects

#### Scenario: Text that looks like a variable
- **WHEN** the message holds `{f}` or `{?}` and the query selects `f`
- **THEN** each is warned about: `{f}` as text, not a variable, and `{?}` as naming none

#### Scenario: An apostrophe
- **WHEN** the message is "it's off"
- **THEN** it is warned about as ending the text in the platform's SQL, and it can still be saved

### Requirement: A constraint without a message is warned about
A SPARQL constraint of a shape with a target class and without `sh:message` SHALL be warned about in the Problems panel and by `semforge check`, on the line of its query, saying that the platform does not compile it.

#### Scenario: No message
- **WHEN** a SPARQL constraint of a shape with a target class has no `sh:message`
- **THEN** the Problems panel and `semforge check` warn that the platform does not compile it, on the line of its query

### Requirement: A query edited away from its message is warned about
A query edited in its editor so that its saved message names a variable it no longer selects SHALL be warned about on its SELECT.

#### Scenario: The query edited away from its message
- **WHEN** the saved message names `{?f}` and the query is edited in its editor to no longer select `?f`
- **THEN** the query's editor warns on its SELECT that the message does not fit

### Requirement: Saving writes only the message
Saving SHALL write the message as the value of that constraint's one `sh:message` in the file that declares it, keeping its language tag or datatype, adding `sh:message` when there was none, and changing nothing else; the result SHALL be checked by parsing before it is written. Unsaved changes of the query SHALL stay in its editor.

#### Scenario: Changed
- **WHEN** the message "Cutter running without running filter" is changed to `Filter {?f} is "off" for {$this}` and saved
- **THEN** `shacl.ttl` differs only in that value, written as `"Filter {?f} is \"off\" for {$this}"`, and the next run's result says the filled message

#### Scenario: Its language kept
- **WHEN** a message written as `"Zu heiß"@de` is changed to "Viel zu heiß"
- **THEN** the file says `"Viel zu heiß"@de`

#### Scenario: Added
- **WHEN** a message is saved for a constraint without one
- **THEN** the constraint has that `sh:message` and the rest of the file is unchanged

#### Scenario: Unsaved query edits
- **WHEN** the query has unsaved changes in its editor and the message is saved
- **THEN** the editor still holds them, unsaved

#### Scenario: A line break and quotes
- **WHEN** a message with a line break and a quote is saved, or given to a new SPARQL constraint
- **THEN** the file parses and the constraint's message is that text

### Requirement: A save over a changed file is refused
Saving SHALL be refused, with the file unchanged, when the message or the query in the file differ from what the page showed.

#### Scenario: Changed in the file meanwhile
- **WHEN** the message or the query was changed in `shacl.ttl` after the page showed them, and the page's message is saved
- **THEN** saving is refused with a message that says it changed in the file, and the file is unchanged

### Requirement: An emptied message is removed after asking
An emptied message SHALL be removed after a confirmation that says the platform then does not compile the constraint; declined, nothing SHALL be written.

#### Scenario: Emptied
- **WHEN** the message is emptied and saved, and the confirmation is accepted
- **THEN** the constraint has no `sh:message`, and the Problems panel warns that it has none

#### Scenario: Declined
- **WHEN** the message is emptied and saved, and the confirmation is declined
- **THEN** the file is unchanged and the field keeps the draft

### Requirement: Several messages or one that is no text are edited in the .ttl
A constraint with more than one `sh:message`, or whose `sh:message` is no text, SHALL NOT be edited from a page: the page SHALL say why and lead to its line in the `.ttl`, and a save request SHALL be refused with the file unchanged.

#### Scenario: Several messages
- **WHEN** a constraint has the messages `"hot"@en` and `"heiß"@de`
- **THEN** the page offers no Edit message, says why and links to its line in the `.ttl`, and a save request is refused with the file unchanged

#### Scenario: No text
- **WHEN** a constraint's `sh:message` is an IRI
- **THEN** the page offers no Edit message and a save request is refused with the file unchanged
