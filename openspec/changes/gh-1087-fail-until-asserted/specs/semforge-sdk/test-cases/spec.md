# semforge-sdk/test-cases Delta

## ADDED Requirements

### Requirement: New test asks whether the attribute should conform or fail
New test… of an attribute SHALL offer exactly two kinds of test, whatever constraints the attribute has: one that should conform and one that should fail. It SHALL then ask only for the case's name, suggesting one.

#### Scenario: An attribute with a list
- **WHEN** the user runs New test… on an attribute whose value has an `sh:in` list
- **THEN** the two kinds Should conform and Should fail are offered, and nothing else

### Requirement: A failing test starts from valid data without a reason
A test that should fail SHALL be written with the same data as one that should conform, declared `expect: invalid` in its suite's `bad/` folder without an assert, and run once. It SHALL fail, its description SHALL say that it fails until its data is edited and that is asserted, and its case page SHALL open.

#### Scenario: Written and failing
- **WHEN** the user writes a test that should fail for an attribute with an `sh:in` list
- **THEN** the case's value is one the list allows, the case asserts nothing, and it fails

#### Scenario: Finished
- **WHEN** the value of that case is changed to one outside the list, and the `sh:in` constraint that then fires is asserted on the case page
- **THEN** the case passes

#### Scenario: Broken but without a reason
- **WHEN** the value of that case is changed to one outside the list and nothing is asserted
- **THEN** the case still fails, and the only failure says that it asserts nothing

### Requirement: A conforming test uses a value the list allows
A test that should conform, written for an attribute whose value has an `sh:in` list and that no scene provides, SHALL carry a value of that list in the form that compares equal to it: text, number, boolean, typed literal or IRI.

#### Scenario: Lists of each kind
- **WHEN** a test that should conform is written for an attribute with the list `"red", "green"`, `1, 2`, `20.5, 21.5` or `true`, with or without the matching datatype
- **THEN** the case passes

### Requirement: The value picker offers the list
Editing the value of an attribute with an `sh:in` list in a case SHALL offer the items of the list, each written so that it compares equal to the list's item, and SHALL accept any other value typed.

#### Scenario: Picked from the list
- **WHEN** the value of an attribute with the list `"1", "true"` is edited and the item `1` is picked
- **THEN** the text `1` is written and the list is not violated

### Requirement: The test case page says when a reason is missing
The page of a case that expects a violation and asserts nothing SHALL say that the case fails because it has no reason yet, and how to name one.

#### Scenario: No reason yet
- **WHEN** the page of an invalid case without asserts is opened
- **THEN** it says that the case has no reason yet and fails

### Requirement: Any constraint that judges the case can be asserted
The test case page of an invalid case SHALL offer to add an assert, chosen from every constraint the validation judged one of the case's entities by and the case does not assert yet, those that fire first. A constraint that holds now SHALL be offered too; asserted, the case fails until it fires.

#### Scenario: A reason named before it fires
- **WHEN** an assert is added for a constraint that holds in the case
- **THEN** the case fails until its data is edited so that the constraint fires, and passes then

#### Scenario: Already asserted
- **WHEN** a constraint is asserted on an entity of the case
- **THEN** it is not offered for that entity again

### Requirement: Every assert can be removed
The test case page SHALL offer to remove each assert of the case.

#### Scenario: The last assert removed
- **WHEN** the only assert of a passing invalid case is removed on its page
- **THEN** the case asserts nothing and fails

### Requirement: The tests about an attribute are listed with it
The attribute editor SHALL list the test cases about its attribute in the shape that declares it: those in which one of its constraints fires or is asserted, and those that have the attribute. Each entry SHALL say whether the case passes and what it asserts or what fires, open the case's page, and offer to delete the case. The list SHALL follow a validation run that ends while the editor is open, without redrawing the rest of the editor.

#### Scenario: A failing test in the list
- **WHEN** a test that should fail was written for an attribute and its validation has run
- **THEN** the attribute editor lists it as failing, and cases without the attribute are not listed

#### Scenario: Deleted from the attribute editor
- **WHEN** the user deletes a listed case and confirms
- **THEN** its file and its declaration are gone

### Requirement: Deleting a case is a visible action
The test case page SHALL show Clone, Rename and Delete as buttons, and the case lists of the type and shape pages SHALL offer Delete on each case. Each SHALL ask before deleting, as the case's context menu does.

#### Scenario: Deleted from the type page
- **WHEN** the user runs Delete on a case in the type page's list and confirms
- **THEN** the case's file and its declaration are gone
