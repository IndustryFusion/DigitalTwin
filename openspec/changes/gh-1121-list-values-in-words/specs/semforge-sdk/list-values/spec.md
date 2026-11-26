## Purpose
Defines how the SemForge editor shows and edits the values of `sh:in` and
`sh:hasValue`: in plain words, one value per row, without Turtle.

## ADDED Requirements

### Requirement: Values are shown as they read
The attribute editor and the parameters of a type page's row SHALL show the values of `sh:in` and `sh:hasValue` without quotes, brackets, escapes, datatypes and language tags, a term by its local name, several separated by a middle dot. A pattern and its flags SHALL be shown without quotes.

#### Scenario: A list of texts
- **WHEN** a value has `sh:in ( "Executing" "NONE" )`
- **THEN** the attribute editor shows `Executing · NONE`

#### Scenario: Typed, tagged and escaped items
- **WHEN** a list holds `"2026-01-01"^^xsd:date`, `"rot"@de` and `"say \"hi\""`
- **THEN** they are shown as `2026-01-01`, `rot` and `say "hi"`

### Requirement: One value per row
*One of* SHALL be edited with one row per value: a value can be added (by a button, or Enter in the last row), changed and taken out. *Exactly* SHALL have one row, and more than one value for it SHALL be refused. An empty row SHALL be no value, a value that is there already SHALL not be written twice, and a list without a value SHALL NOT be written.

#### Scenario: A second value
- **WHEN** `NONE` is added to the list that holds `Executing`
- **THEN** the shapes file holds `sh:in ( "Executing" "NONE" )`

#### Scenario: A value taken out
- **WHEN** `Executing` is taken out of that list
- **THEN** the shapes file holds `sh:in ( "NONE" )`

#### Scenario: Empty and repeated rows
- **WHEN** the rows are `NONE`, an empty one and `NONE`
- **THEN** the shapes file holds `sh:in ( "NONE" )`

#### Scenario: Exactly
- **WHEN** *exactly* is set to the text `Executing`
- **THEN** the shapes file holds `sh:hasValue "Executing"`

### Requirement: A text is what was typed
A value of the kind text SHALL be written so that it reads as what was typed, whatever characters it has.

#### Scenario: Characters Turtle uses
- **WHEN** the texts `with, comma`, `( "odd" )`, `say "hi"`, `a:b`, `12`, `true`, `back\slash`, `Grün` and an emoji are entered
- **THEN** each is one text in the list and is shown as it was typed

### Requirement: The kind of a value
A row SHALL say the kind of its value: text, number, true/false or vocabulary term. For a new value it SHALL follow from the datatype the value's shape names, else from what is typed: a term the value's vocabulary classes offer, a number, `true` or `false`, else a text. The user SHALL be able to choose another, and what is typed afterwards SHALL not change it.

#### Scenario: A number typed
- **WHEN** `5` is typed into a new row and the value's shape names no datatype
- **THEN** the value is a number

#### Scenario: A number where the shape asks for a text
- **WHEN** `5` is typed into a new row and the value's shape says `sh:datatype xsd:string`
- **THEN** the value is the text `5`

#### Scenario: A number where the shape asks for a double
- **WHEN** the values `1` and `20.5` are added where the value's shape says `sh:datatype xsd:double`
- **THEN** both are written as `xsd:double`

#### Scenario: A term offered
- **WHEN** the value's shape names a vocabulary class and one of its values is picked in a new row
- **THEN** the value is that term

### Requirement: A value that was not touched stays the same
Editing a list SHALL keep every value that was not changed the same RDF term, its datatype and language included, and every value SHALL keep its place.

#### Scenario: Items of every kind
- **WHEN** a list holds a number, a decimal, a boolean, a term, a text of digits, a language-tagged text and a date, and a text is added
- **THEN** the list holds the same terms in the same order, and the text

### Requirement: A value that is not of its kind is refused
A row of the kind number that is no number, of true/false that is neither, and of vocabulary term that is neither a prefixed name nor an IRI SHALL be refused with a message, and the shapes file SHALL be unchanged.

#### Scenario: A word as a number
- **WHEN** `many` is entered as a number
- **THEN** it is refused as not a number, and the shapes file is unchanged

#### Scenario: A word as a term
- **WHEN** `Executing` is entered as a vocabulary term
- **THEN** it is refused, and the message names the kind text

### Requirement: A Turtle list typed is a list
Where a list is typed into a text field, text in the form of a Turtle list SHALL be read as that list.

#### Scenario: Turtle typed
- **WHEN** `( "Executing" "NONE" )` is entered into the text field of a list
- **THEN** the list holds the two texts
