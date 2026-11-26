# Spec Delta

## Purpose
Defines how SemForge's views are searched, so that what a model holds is found
where it is worked on, and how a line of a package's file leads back to the
page of what it is about.

## ADDED Requirements

### Requirement: Search filters the four views
**Search…** SHALL be offered in the command palette, by a key and in the title bars of Entities & Test Cases, Constraints by Type, SHACL Shapes as Written and Knowledge (Ontology). While the user types, each of these views SHALL keep only the rows that fit and the rows they are under, and SHALL say the text searched for and how many of its rows fit, or that none does. A click on a row SHALL open what it opens without a search.

#### Scenario: An attribute in all four views
- **WHEN** the kms package is searched for `hasStrength`
- **THEN** each of the four views shows fewer rows than before, at least one of which fits, and says how many fit

#### Scenario: Nothing fits
- **WHEN** no row of a view fits
- **THEN** the view shows no row and says that there is nothing here for the text searched for

### Requirement: The rows a search keeps
A row SHALL fit when every word of the search is in it, in any order and in upper or lower case. A row with rows that fit under it SHALL be opened down to them and keep only them; a row that fits and has none that fit under it SHALL keep the rows under it, closed.

#### Scenario: Words in any order and case
- **WHEN** a type `Machine` has the attribute rows `hasState`, described as `state_ON`, and `hasPower`, described as `number`, and the search is `STATE has`
- **THEN** the type is kept, opened, with the row `hasState` alone under it, and one row fits

#### Scenario: A fitting row without fitting rows
- **WHEN** the search is `machine` and only that type's own row fits
- **THEN** the type is kept with both its attribute rows, closed

### Requirement: A row fits by its statement or its asserts
A row SHALL also fit by what it stands for without showing it, and then SHALL say what was found: in Constraints by Type and SHACL Shapes as Written by the attribute's constraint or the shape's statement, in Knowledge (Ontology) by the statement that declares the term, and a test case by its description and the constraints and resources it asserts.

#### Scenario: A value a shape lists
- **WHEN** the `sh:in` of `hasStrength` in `FilterShape` lists `Executing`, which no other statement has, and the search is `executing`
- **THEN** SHACL Shapes as Written shows `FilterShape` alone, with a description that says the search found `Executing` there, Constraints by Type shows the `hasStrength` row, and in Knowledge (Ontology) nothing fits

#### Scenario: What a case asserts
- **WHEN** the search is `hasCartridge MinCount` and the case `without-cartridge.jsonld` asserts that constraint
- **THEN** the row of that case fits

### Requirement: A count does not make a row fit
A count shown on a row ("3 attribute(s)") SHALL NOT make it fit. An entity's type SHALL make the entity's row fit, but not the rows of its attributes.

#### Scenario: A count
- **WHEN** a type's row is described as "3 attribute(s)", nothing else there says "attribute", and the search is `attribute(s)`
- **THEN** the type's row does not fit

#### Scenario: An entity's type
- **WHEN** the search is `FilterCartridge`
- **THEN** rows of entities of that type fit, and a row of another attribute of such an entity does not

### Requirement: A search is kept until it is cleared
Enter SHALL keep the search, also when the views are refreshed, and Escape SHALL put back the search there was before. An empty search and **Clear the search** SHALL show everything again, with the same rows as without a search. While a search is kept, editing from a row SHALL act as it does without one, whatever rows are hidden.

#### Scenario: Enter and Clear the search
- **WHEN** the user runs Search…, enters `hasStrength`, presses Enter and later runs Clear the search
- **THEN** the views stay filtered until Clear the search, and then show the rows they showed before

#### Scenario: Escape
- **WHEN** a search for `Filter` is kept, and the user runs Search…, types `hasStrength` and presses Escape
- **THEN** the views are filtered to `Filter` again

#### Scenario: An attribute whose row is hidden
- **WHEN** an entity has an attribute with the default instance, a search hides that attribute's row, and the user adds that attribute to the entity
- **THEN** the default instance is treated as taken, as without the search: choosing it asks for the time of another observation

### Requirement: A line of a file leads to its page
**Open in SemForge** SHALL be offered in the title bar and the context menu of editors of `.ttl`, `.jsonld` and `expectations.yaml` files. In a file of a package it SHALL open the page of what the cursor's line is about, at the entity, attribute or value the line names. The line SHALL be that of the text as the editor shows it, saved or not.

#### Scenario: A line of a shape
- **WHEN** the cursor is on the path `hasStrength` within `FilterShape` in `shacl.ttl` and the user runs Open in SemForge
- **THEN** the page of `FilterShape` opens

#### Scenario: A term of the knowledge
- **WHEN** the cursor is on the declaration of `Filter`, of `hasStrength`, of `state_ON`, or of the class of that value
- **THEN** the page of the type `Filter`, the same page with `hasStrength` marked, the vocabulary page of the class with `state_ON` marked, or that vocabulary page opens

#### Scenario: An entity
- **WHEN** the cursor is on an entity in the main model's file, or in a test case's file
- **THEN** the Main model page, or that case's page, opens at that entity

#### Scenario: A file that cases include
- **WHEN** the cursor is in a file that test cases include
- **THEN** the page of the first of those cases opens

#### Scenario: A declaration of a case
- **WHEN** the cursor is on a case's entry in `expectations.yaml`
- **THEN** that case's page opens

#### Scenario: A file with unsaved lines
- **WHEN** lines were inserted above a shape and not saved, and the cursor is on that shape
- **THEN** the page of that shape opens

### Requirement: A line without a page is searched for
Where nothing on the cursor's line has a page, Open in SemForge SHALL search the views for the word at the cursor, and say so when there is none. Without an open file, or in a file of no package, it SHALL say what is missing and open nothing.

#### Scenario: A line without a page
- **WHEN** the cursor is on the word `iffBaseEntities:hasState` in a line that is about nothing with a page
- **THEN** the views are searched for `hasState`

#### Scenario: A file outside any package
- **WHEN** the file is in no package
- **THEN** an error says so and no page opens
