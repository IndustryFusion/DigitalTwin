## Purpose
Defines how the SemForge editor says which type a value of an example has, and
how a modeller makes it another on purpose without knowing JSON-LD.

## ADDED Requirements

### Requirement: The type is said where the spelling does not tell it
A page that shows entities SHALL say, beside a Property's value that is spelled like a number or is `true` or `false`, the type the value has as JSON-LD reads it: a plain whole number below 10^21 is an integer, however it is written; a plain number with a fraction, or of 10^21 and more, a double; a declared value what it is declared as; a quoted one a text. Beside a value that is spelled otherwise it SHALL say nothing.

#### Scenario: One spelling, four types
- **WHEN** a case holds the values `50`, `"50"`, a declared `xsd:double` 50 and a declared `xsd:decimal` 50
- **THEN** its page says integer, text, double and decimal

#### Scenario: A whole number with a point
- **WHEN** a case holds the plain number `50.0`
- **THEN** its page says integer

#### Scenario: A very large plain number
- **WHEN** a case holds the plain number `1000000000000000000000` (10^21)
- **THEN** its page says double

#### Scenario: An earlier observation
- **WHEN** an attribute has an earlier observation of the value 49.0 beside its current one
- **THEN** the earlier one says integer, and only the current one offers to change the type

#### Scenario: A text that looks like one
- **WHEN** a case holds the value `"red"`
- **THEN** its page says no type beside it

### Requirement: The type of a value can be chosen
The type said beside a value that is not a superseded observation SHALL be a control that offers: as the shape says, double, integer, decimal, text, true/false and vocabulary term, the present one marked; a present type none of these is SHALL be named instead. The command palette SHALL NOT offer it. Choosing one SHALL write the value with that type and leave what it says unchanged, in the file the value is in; a file that other cases include SHALL be asked about first, as on editing the value.

#### Scenario: Each type
- **WHEN** the value 50.0 of an `xsd:double` attribute is made a double, an integer, a decimal and a text
- **THEN** it is each of these and still says 50 or 50.0, its page says the type, and the datatype constraint fires for all but the double

#### Scenario: True or false
- **WHEN** the text `true` is made true/false
- **THEN** the value is the boolean `true`

#### Scenario: A vocabulary term
- **WHEN** the text `owl:Thing` is made a vocabulary term
- **THEN** the value names that term

#### Scenario: Chosen on the page
- **WHEN** the type beside a value is clicked and Double is picked
- **THEN** the value is a declared double, and the page shows it so

#### Scenario: A type none of the choices is
- **WHEN** the type beside a value declared `xsd:int` is clicked
- **THEN** no choice is marked as the present one, and the question names `int`

#### Scenario: A text with a language
- **WHEN** the value `{"@value": "rot", "@language": "de"}` is made a text
- **THEN** it is the plain text `rot`

#### Scenario: Not picked
- **WHEN** the type beside a value is clicked and nothing is picked
- **THEN** the file is unchanged

### Requirement: The row menu offers the type
The row menu of each Property's value that is a number, a text, `true` or `false` or a vocabulary term SHALL offer the same choice, unless it is a superseded observation; the menu of a value that is a list, an object or null SHALL NOT.

#### Scenario: Offered in the menu
- **WHEN** the row menu of a Property whose value is 50.0 is opened
- **THEN** it offers the type of the value, and choosing a type there writes it as the page's control does

#### Scenario: A structure is not offered
- **WHEN** the row menu of a Property whose value is a JSON object is opened
- **THEN** it does not offer the type of the value

### Requirement: As the shape says
Choosing *as the shape says* SHALL write what the value says in the one datatype the attribute's shape names for it, read with the shapes' prefixes, and where the shape names none or a choice of several, as an edit of the value does. The shape SHALL be the one an edit of the value follows. A vocabulary term SHALL stay one when no datatype is named.

#### Scenario: Back to a double
- **WHEN** the value of an `xsd:double` attribute was made a text and *as the shape says* is chosen
- **THEN** it is a declared `xsd:double` again and no datatype violation is raised

#### Scenario: A text of digits
- **WHEN** the value of an `xsd:string` attribute is the integer 50 and *as the shape says* is chosen
- **THEN** it is the text `50`

#### Scenario: A term without a datatype
- **WHEN** *as the shape says* is chosen for a vocabulary term of an attribute whose shape names no datatype
- **THEN** the value is unchanged

### Requirement: An integer type of the shape
As the shape says, an XSD integer type other than `xsd:integer` SHALL take a whole number only and be declared with that type, since a plain number is an `xsd:integer`; whether it is in that type's range SHALL NOT be checked by this choice.

#### Scenario: An integer type
- **WHEN** the value of an attribute whose shape says `sh:datatype xsd:int` is the text `50`, and *as the shape says* is chosen
- **THEN** it is `{"@value": 50, "@type": "xsd:int"}`; the text `50.5` would be refused as not a whole number

#### Scenario: Out of the range of its type
- **WHEN** *as the shape says* is chosen for the value 300 of an attribute whose shape says `sh:datatype xsd:unsignedByte`
- **THEN** it is written as `{"@value": 300, "@type": "xsd:unsignedByte"}`; whether 300 is in range is not checked here

### Requirement: A value that cannot be of the type is refused
A choice the value cannot follow SHALL be refused with a message that says why, and the file SHALL be unchanged: a number type for what is no number, a double for what a double cannot hold, an integer for a number with a fraction, true/false for anything but `true` and `false`, a vocabulary term for what is neither a prefixed name nor an IRI, any type for a value that is a list, an object or null, and for another member than a Property's value.

#### Scenario: A fraction as an integer
- **WHEN** integer is chosen for the value 50.5
- **THEN** it is refused as not a whole number, and the value is still 50.5

#### Scenario: A word as a number
- **WHEN** double is chosen for the text `red`, `NaN` or `1_000`
- **THEN** it is refused as not a number, and the text is unchanged

#### Scenario: A structure
- **WHEN** text is chosen for a value that is a JSON object or a list, by a request that does not come from the menu
- **THEN** it is refused, and the value is unchanged

### Requirement: Nothing is lost on the way
Changing a number's type SHALL keep its digits: a whole number of up to 1000 digits SHALL stay exact as an integer, a decimal or a text, and an integer or a decimal that would be written out with more digits SHALL be refused. An integer of 10^21 and more SHALL be written as a declared value whose `@value` is its digits as text, since JSON-LD reads a JSON number that large as a double.

#### Scenario: A long number
- **WHEN** the text `9007199254740993` is made an integer, and then a decimal
- **THEN** the integer is 9007199254740993 and the decimal says 9007199254740993

#### Scenario: An integer of 10^21
- **WHEN** the text `1e21` is made an integer
- **THEN** the value is `{"@value": "1000000000000000000000", "@type": "xsd:integer"}`

#### Scenario: Too many digits
- **WHEN** the text `1e1000` is made an integer or a decimal
- **THEN** it is refused as having more than 1000 digits, and the text is unchanged
