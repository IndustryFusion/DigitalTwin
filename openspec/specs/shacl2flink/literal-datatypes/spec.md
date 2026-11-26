# shacl2flink/literal-datatypes Specification

## Purpose
Defines which values of an NGSI-LD property satisfy an `sh:datatype` of
`xsd:double` or `xsd:integer`, and how `sh:hasValue` compares a value with
its constant, when shacl2flink validates a model, so that the checks give
the verdict a conformant SHACL engine gives on the JSON-LD reading of the
model where the platform can tell, state where they deliberately differ, and
the check on SQLite and the check on Flink agree.

## Requirements

### Requirement: Plain numbers are typed as JSON-LD types them
A plain JSON number SHALL be an `xsd:double` when it has a non-zero fractional part or an absolute value of at least 10^21, and an `xsd:integer` otherwise, however it is written. A plain `xsd:double` SHALL satisfy `sh:datatype xsd:double` and violate `sh:datatype xsd:integer`; a plain `xsd:integer` SHALL satisfy `sh:datatype xsd:integer` and violate `sh:datatype xsd:double`.

#### Scenario: Fraction on a double shape
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the plain value `80.5`
- **THEN** no datatype alert is raised for it

#### Scenario: Whole number on a double shape
- **WHEN** the property has the plain value `80`
- **THEN** a datatype alert is raised for it

#### Scenario: Whole number written with a decimal point on a double shape
- **WHEN** the property has the plain value `80.0`
- **THEN** a datatype alert is raised for it

#### Scenario: Zero on a double shape
- **WHEN** the property has the plain value `0.0`
- **THEN** a datatype alert is raised for it

#### Scenario: Very large number on a double shape
- **WHEN** the property has the plain value `1e21`
- **THEN** no datatype alert is raised for it

#### Scenario: Whole number written with a decimal point on an integer shape
- **WHEN** a property of a shape with `sh:datatype xsd:integer` has the plain value `80.0`
- **THEN** no datatype alert is raised for it

#### Scenario: Fraction on an integer shape
- **WHEN** the property has the plain value `80.5`
- **THEN** a datatype alert is raised for it

### Requirement: A declared type decides
A value with a declared `@type` of `xsd:double` SHALL satisfy `sh:datatype xsd:double` when its text is a number: an optional sign, then digits with an optional decimal point, or a decimal point and digits, then an optional exponent. A value declared `xsd:integer` SHALL violate `sh:datatype xsd:double`, and a value declared `xsd:double` SHALL violate `sh:datatype xsd:integer`.

#### Scenario: Declared double written as a whole number
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

#### Scenario: Declared double zero
- **WHEN** the property has the value `{"@value": 0.0, "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

#### Scenario: Declared double with a fraction
- **WHEN** the property has the value `{"@value": 80.5, "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

#### Scenario: Declared integer on a double shape
- **WHEN** the property has the value `{"@value": 80, "@type": "xsd:integer"}`
- **THEN** a datatype alert is raised for it

#### Scenario: Declared double on an integer shape
- **WHEN** a property of a shape with `sh:datatype xsd:integer` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** a datatype alert is raised for it

### Requirement: Strings are judged by their text
A JSON string without a declared type SHALL satisfy `sh:datatype xsd:double` when its text is a number with a decimal point or an exponent, and `sh:datatype xsd:integer` when its text is an optional sign followed by digits. Any other text SHALL violate both.

#### Scenario: Live value with a decimal point
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the string value `"80.0"`
- **THEN** no datatype alert is raised for it

#### Scenario: Digits only on a double shape
- **WHEN** the property has the string value `"80"`
- **THEN** a datatype alert is raised for it

#### Scenario: Zero as a string on a double shape
- **WHEN** the property has the string value `"0"`
- **THEN** a datatype alert is raised for it

#### Scenario: Digits only on an integer shape
- **WHEN** a property of a shape with `sh:datatype xsd:integer` has the string value `"80"`
- **THEN** no datatype alert is raised for it

#### Scenario: Text that is not a number
- **WHEN** a property of a shape with `sh:datatype xsd:double` has the string value `"eighty"`
- **THEN** a datatype alert is raised for it

### Requirement: SQLite and Flink agree on datatypes
The checks generated for SQLite and for Flink SHALL raise the same datatype alerts and the same `sh:hasValue` alerts for every scenario of this specification.

#### Scenario: The same model on both
- **WHEN** a model with the values of the scenarios above is validated on SQLite and, after it was written to Scorpio, on Flink
- **THEN** both raise datatype alerts for exactly the same properties

#### Scenario: The same sh:hasValue verdicts on both
- **WHEN** a model with the values of the `sh:hasValue` scenarios is validated on SQLite and, after it was written to Scorpio, on Flink
- **THEN** both raise `sh:hasValue` alerts for exactly the same properties

### Requirement: The rule is documented
The shacl2flink documentation SHALL state how plain numbers, declared types and strings satisfy `xsd:double` and `xsd:integer`, that a whole-valued double has to be declared with `@type`, and that strings are judged by their text unlike in a conformant SHACL engine.

#### Scenario: Reading the documentation of sh:datatype
- **WHEN** a modeller reads the entry for `sh:datatype` in the shacl2flink documentation
- **THEN** it says that a plain `80.0` is an integer, that `{"@value": 80, "@type": "xsd:double"}` is the way to write a whole-valued double, and that `"80.0"` as a string satisfies `xsd:double`

### Requirement: The documentation states how sh:hasValue compares
The shacl2flink documentation SHALL state that `sh:hasValue` compares a number constant by its value, a string constant with the text the platform sends and how the platform writes a number, and a boolean constant as a boolean, unlike a conformant SHACL engine, which compares value and datatype.

#### Scenario: Reading the documentation of sh:hasValue
- **WHEN** a modeller reads the entry for `sh:hasValue` in the shacl2flink documentation
- **THEN** it says that `80`, `80.0`, a declared `xsd:double` `80` and the string `"80.0"` all satisfy `sh:hasValue 80.0` and `sh:hasValue 80`, that this differs from a conformant SHACL engine, that a plain `1`, a plain `1.0` and a declared `xsd:double` `1` satisfy `sh:hasValue "1"` while only the string `"1.0"` satisfies `sh:hasValue "1.0"`, and that `sh:hasValue true` is satisfied by a plain `true`, a declared `xsd:boolean` `true` or `1` and the string `"true"` but not by `"True"`, `"1"` or the number `1`

### Requirement: sh:hasValue compares a number by its value
When the constant of `sh:hasValue` is a number, a value SHALL satisfy it when it is the same number, whatever numeric datatype the constant and the value have and whether the value declares a type at all. A plain number, a value declared with a numeric XSD datatype, and a string whose text is a number as defined for a declared `xsd:double` count as numbers. Any other value SHALL violate the constraint.

#### Scenario: Plain whole number
- **WHEN** a property of a shape with `sh:hasValue 80.0` has the plain value `80`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Plain whole number written with a decimal point
- **WHEN** a property of a shape with `sh:hasValue 80` has the plain value `80.0`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Declared double with a whole value
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Declared integer
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the value `{"@value": 80, "@type": "xsd:integer"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A different number
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the plain value `80.5` or the value `{"@value": 80.5, "@type": "xsd:double"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A declared integer against a fraction
- **WHEN** a property of a shape with `sh:hasValue 80.5` has the value `{"@value": 80, "@type": "xsd:integer"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A string holding the number
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the string value `"80.0"` or `"80"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: Text that is not a number
- **WHEN** a property of a shape with `sh:hasValue 80.0` or `sh:hasValue 80` has the string value `"eighty"`
- **THEN** a `sh:hasValue` alert is raised for it

### Requirement: sh:hasValue compares a string by its text
When the constant of `sh:hasValue` is a string, or a literal of any datatype that is neither numeric nor `xsd:boolean` (such as `xsd:gYear`, `xsd:token` or a datatype of the model's own), a value SHALL satisfy it only when the text the platform sends for the value is exactly the constant as written, even when both texts read as the same number. A value without a declared type, or declared `xsd:string`, is compared by its text.

#### Scenario: The same text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the string value `"1.0"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: The same number in another text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the string value `"1"`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A constant of another datatype
- **WHEN** a property of a shape with `sh:hasValue "2020"^^xsd:gYear` has the plain value `2020`, the string value `"2020"` or the value `{"@value": "2020", "@type": "xsd:gYear"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A constant of another datatype against a number
- **WHEN** a property of a shape with `sh:hasValue "1"^^xsd:token`, or with `sh:hasValue "1"` of a datatype of the model's own, has the plain value `1` or `1.0`, or the value `{"@value": 1, "@type": "xsd:double"}`
- **THEN** no `sh:hasValue` alert is raised for it

### Requirement: The text the platform sends for a number and a boolean
The validation SHALL take the text of a plain number as the platform sends it, as JavaScript writes numbers: the shortest digits that identify the number, without a decimal point when it is whole, and with an exponent from 10^21 up (`1e+21`) and below 10^-6 (`1e-7`); `NaN` and the infinities are never sent for a number. It SHALL take a boolean, plain or declared, as the text `true` or `false`.

#### Scenario: A plain number sent as the constant
- **WHEN** a property of a shape with `sh:hasValue "1"` has the plain value `1` or `1.0`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A number sent in another text than the constant
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the plain value `1` or `1.0`, or the value `{"@value": 1, "@type": "xsd:double"}` or `{"@value": 1, "@type": "xsd:integer"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A fraction
- **WHEN** a property of a shape with `sh:hasValue "0.5"` has the plain value `0.5`, the value `{"@value": 0.5, "@type": "xsd:double"}` or the string value `"0.5"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A fraction in another text
- **WHEN** a property of a shape with `sh:hasValue "0.5"` has the string value `".5"`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A large number
- **WHEN** a property of a shape with `sh:hasValue "1e+21"` has the plain value `1e21`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A large number as a string in another text
- **WHEN** a property of a shape with `sh:hasValue "1e+21"` has the string value `"1e21"`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A text that is no number the platform sends
- **WHEN** a property of a shape with `sh:hasValue "NaN"` has the plain value `0`
- **THEN** a `sh:hasValue` alert is raised for it, and none for the string value `"NaN"`

#### Scenario: A boolean sent as the constant
- **WHEN** a property of a shape with `sh:hasValue "true"` has the plain value `true`, the value `{"@value": "1", "@type": "xsd:boolean"}` or the string value `"true"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A boolean against another text
- **WHEN** a property of a shape with `sh:hasValue "1"` has the value `{"@value": "1", "@type": "xsd:boolean"}`, or a property of a shape with `sh:hasValue "true"` has the string value `"True"`
- **THEN** a `sh:hasValue` alert is raised for it

### Requirement: sh:hasValue compares a declared number by its value
The one exception is a value declared with a numeric XSD datatype: it SHALL be compared by its value, and satisfy the constant only when the constant is the text JavaScript writes for a finite number and the value is that number.

#### Scenario: A declared number sent as the constant
- **WHEN** a property of a shape with `sh:hasValue "1"` has the value `{"@value": 1, "@type": "xsd:double"}` or `{"@value": 1, "@type": "xsd:integer"}`
- **THEN** no `sh:hasValue` alert is raised for it

### Requirement: A declared number written as a string is compared by its value
A value declared with a numeric XSD datatype SHALL be compared by its value also when it was written as a string, such as `{"@value": "1.0", "@type": "xsd:double"}`, which the platform sends as the text `1.0`, because the validation of the model before it reaches the platform cannot tell it from the number `1.0`; comparing by value is the only way both validations agree on it.

#### Scenario: A declared number written as a string
- **WHEN** a property of a shape with `sh:hasValue "1"` has the value `{"@value": "1.0", "@type": "xsd:double"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A declared number written as a string against its own text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the value `{"@value": "1.0", "@type": "xsd:double"}`
- **THEN** a `sh:hasValue` alert is raised for it

### Requirement: sh:hasValue compares a boolean as a boolean
When the constant of `sh:hasValue` is an `xsd:boolean`, a value SHALL satisfy it when it is the same boolean: a plain JSON boolean, a value declared `xsd:boolean` whose text is `true` or `1` for true and `false` or `0` for false, or a string without a declared type, or declared `xsd:string`, whose text is exactly `true` or `false`. Any other value SHALL violate it, including strings in another case, the strings `"1"` and `"0"`, and numbers.

#### Scenario: A plain boolean
- **WHEN** a property of a shape with `sh:hasValue true` has the plain value `true`, or a property of a shape with `sh:hasValue false` has the plain value `false`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: The other plain boolean
- **WHEN** a property of a shape with `sh:hasValue true` has the plain value `false`, or a property of a shape with `sh:hasValue false` has the plain value `true`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A declared boolean
- **WHEN** a property of a shape with `sh:hasValue true` has the value `{"@value": true, "@type": "xsd:boolean"}` or `{"@value": "1", "@type": "xsd:boolean"}`, or a property of a shape with `sh:hasValue false` has the value `{"@value": "0", "@type": "xsd:boolean"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: The other declared boolean
- **WHEN** a property of a shape with `sh:hasValue true` has the value `{"@value": "0", "@type": "xsd:boolean"}`, or a property of a shape with `sh:hasValue false` has the value `{"@value": "1", "@type": "xsd:boolean"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: The text of the boolean
- **WHEN** a property of a shape with `sh:hasValue true` has the string value `"true"` or the value `{"@value": "true", "@type": "xsd:string"}`, or a property of a shape with `sh:hasValue false` has the string value `"false"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: The text in another case
- **WHEN** a property of a shape with `sh:hasValue true` has the string value `"True"` or `"TRUE"`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: The digits of a boolean as a string
- **WHEN** a property of a shape with `sh:hasValue true` has the string value `"1"`, or a property of a shape with `sh:hasValue false` has the string value `"0"`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A number
- **WHEN** a property of a shape with `sh:hasValue true` has the plain value `1`, or a property of a shape with `sh:hasValue false` has the plain value `0`
- **THEN** a `sh:hasValue` alert is raised for it

### Requirement: A sh:hasValue constant both validations cannot compare alike is rejected
The build of a shacl2flink package SHALL fail, naming the constant and the shape path, when the constant of `sh:hasValue` is declared with a numeric XSD datatype but its text is not a finite number of that datatype (such as `"abc"^^xsd:integer`, `"NaN"^^xsd:double` or `"INF"^^xsd:double`), or is declared `xsd:boolean` but its text is none of `true`, `false`, `1` and `0`.

#### Scenario: An ill-typed number constant
- **WHEN** a package is built with a shape with `sh:hasValue "abc"^^xsd:integer`
- **THEN** the build fails and names `sh:hasValue "abc"`

#### Scenario: A number constant that is not finite
- **WHEN** a package is built with a shape with `sh:hasValue "INF"^^xsd:double` or `sh:hasValue "NaN"^^xsd:double`
- **THEN** the build fails and names the constraint and its shape path

#### Scenario: An ill-typed boolean constant
- **WHEN** a package is built with a shape with `sh:hasValue "yes"^^xsd:boolean`
- **THEN** the build fails and names the constraint and its shape path

### Requirement: sh:datatype does not depend on sh:nodeKind
The `sh:datatype` a value shape states itself SHALL be checked on SQLite and Flink also when the shape states neither `sh:nodeKind sh:Literal` nor `sh:nodeKind sh:IRI`, whatever connective stands beside it, unless the shape is itself part of a connective; each literal value SHALL get, on its own, the verdict it gets with `sh:nodeKind sh:Literal`, apart from the requirements on declared types below.

#### Scenario: Text on a double shape without a node kind
- **WHEN** a property of a value shape with `sh:datatype xsd:double` and without `sh:nodeKind` has the string value `"abc"`
- **THEN** a datatype alert is raised for it

#### Scenario: A value of the datatype
- **WHEN** the property has the plain value `80.5`
- **THEN** no datatype alert is raised for it

#### Scenario: A declared type
- **WHEN** a property of a value shape with `sh:datatype xsd:integer` and without `sh:nodeKind` has the value `{"@value": 80, "@type": "xsd:double"}`
- **THEN** a datatype alert is raised for it

#### Scenario: One instance of several
- **WHEN** a property of the double shape has the value `80.5` with one datasetId and `"abc"` with another
- **THEN** a datatype alert is raised for the instance with `"abc"` only

#### Scenario: A datatype beside a negation
- **WHEN** a property of a value shape with `sh:datatype xsd:double` and `sh:not` of `sh:hasValue 5`, without `sh:nodeKind`, has the value `"abc"`
- **THEN** a datatype alert is raised for it, and the plain value `5` still raises the alert of `sh:not`

### Requirement: A choice of datatypes without sh:nodeKind
When every branch of an `sh:or` states an `sh:datatype`, on the value shape or on the property shape, no other connective encloses them and no branch states an `sh:path` and no branch or value shape states `sh:nodeKind sh:Literal` or `sh:nodeKind sh:IRI` or is deactivated, a value that is of none of these datatypes SHALL raise an alert, for its own instance only.

#### Scenario: None of the datatypes
- **WHEN** a property of a value shape with an `sh:or` of `xsd:integer` and `xsd:double`, without `sh:nodeKind`, has the string value `"abc"`
- **THEN** an alert is raised for it, and none for the plain values `80` and `80.5`

#### Scenario: Instances of different datatypes
- **WHEN** a property with an `sh:or` of a value shape with `xsd:integer` and one with `xsd:double` has the value `1` with one datasetId and `80.5` with another
- **THEN** no alert is raised for it

#### Scenario: A branch without a datatype
- **WHEN** a property of a value shape with an `sh:or` of `sh:datatype xsd:string` and a branch that states no datatype has an IRI as its value
- **THEN** no datatype alert is raised for it

#### Scenario: A branch with a node kind
- **WHEN** a value shape without `sh:nodeKind` has an `sh:or` of a branch with `sh:nodeKind sh:Literal` and `xsd:integer` and one with `xsd:double` only
- **THEN** the datatype check adds no alert to the verdict of the `sh:or`

### Requirement: Datatypes in an sh:and without sh:nodeKind
Each `sh:datatype` in a branch of an `sh:and`, on the value shape or on the property shape, SHALL raise an alert for a value that is not of it, when no other connective encloses it, its branch has no `sh:path` of its own, and neither the branch nor the value shape states `sh:nodeKind sh:Literal` or `sh:nodeKind sh:IRI` or is deactivated.

#### Scenario: All of the datatypes
- **WHEN** a property of a value shape with an `sh:and` of `xsd:integer` and `xsd:double`, without `sh:nodeKind`, has the plain value `1`
- **THEN** an alert is raised for it

#### Scenario: A branch about a sub-attribute
- **WHEN** a property shape has an `sh:and` of a branch with the path of a sub-attribute whose value shape states `xsd:integer`, and the property has the plain value `80.5` and no such sub-attribute
- **THEN** no datatype alert is raised for the property

### Requirement: rdf:JSON is not judged without sh:nodeKind
`sh:datatype rdf:JSON` of a value shape of `ngsi-ld:hasValue` without `sh:nodeKind` SHALL raise no datatype alert, and an `sh:or` with a branch that states it SHALL raise none for the datatypes of its other branches, since the platform passes a JSON literal on under another type name than the model has. The other branches of an `sh:and` SHALL be judged.

#### Scenario: A JSON literal
- **WHEN** a property of a value shape with `sh:datatype rdf:JSON`, or with an `sh:or` of it and `xsd:string`, without `sh:nodeKind`, has the value `{"@value": {"a": 1}, "@type": "@json"}`
- **THEN** no datatype alert is raised for it

#### Scenario: A JSON literal on another datatype
- **WHEN** a property of a value shape with `sh:datatype xsd:double` and without `sh:nodeKind` has that value
- **THEN** a datatype alert is raised for it

### Requirement: A deactivated shape requires no datatype
A datatype without `sh:nodeKind` SHALL raise no datatype alert when the node shape, property shape or value shape that states it, or an enclosing property shape, has `sh:deactivated true`, or when the datatype stands in an `sh:or` that has a deactivated branch.

#### Scenario: A deactivated property shape
- **WHEN** a property shape with `sh:deactivated true` has a value shape with `sh:datatype xsd:double` and without `sh:nodeKind`, and the property has the string value `"abc"`
- **THEN** no datatype alert is raised for it

#### Scenario: A deactivated branch
- **WHEN** a value shape without `sh:nodeKind` has an `sh:or` of a deactivated branch with `xsd:integer` and one with `xsd:double`, and the property has the string value `"abc"`
- **THEN** no datatype alert is raised for it

### Requirement: A declared type is compared as a whole
Without `sh:nodeKind`, a value declared with a type SHALL satisfy a `sh:datatype` that is none of `xsd:double`, `xsd:integer`, `xsd:boolean` and `xsd:string` only when the declared type is that datatype. A value without a declared type SHALL satisfy such a `sh:datatype`.

#### Scenario: A datatype with a similar name
- **WHEN** a property of a value shape with `sh:datatype xsd:gYearMonth` and without `sh:nodeKind` has the value `{"@value": "2020", "@type": "xsd:gYear"}`
- **THEN** a datatype alert is raised for it

### Requirement: A list of datatypes accepts every datatype in it
A value declared with a datatype that is listed in a choice of datatypes without `sh:nodeKind` SHALL satisfy the choice, also when the list names `xsd:double`, `xsd:integer`, `xsd:boolean` or `xsd:string` beside it. A value without a declared type SHALL satisfy a list that names `rdf:langString`, since the platform passes no type on for a language-tagged string.

#### Scenario: A declared decimal
- **WHEN** a property of a value shape with an `sh:or` of `xsd:integer` and `xsd:decimal`, without `sh:nodeKind`, has the value `{"@value": "80.5", "@type": "xsd:decimal"}`
- **THEN** no datatype alert is raised for it, and one is raised for `{"@value": 80.5, "@type": "xsd:double"}`

#### Scenario: A language-tagged string
- **WHEN** a property of a value shape with an `sh:or` of `xsd:string` and `rdf:langString`, without `sh:nodeKind`, has the value `{"@value": "hallo", "@language": "de"}`
- **THEN** no datatype alert is raised for it

### Requirement: A declared boolean or double in another spelling
Without `sh:nodeKind`, a value declared `xsd:boolean` SHALL satisfy `sh:datatype xsd:boolean` also when its text is `1` or `0`, and a value declared `xsd:double` SHALL satisfy `sh:datatype xsd:double` also when its text is `INF`, `+INF`, `-INF` or `NaN`.

#### Scenario: A declared boolean
- **WHEN** a property of a value shape with `sh:datatype xsd:boolean` and without `sh:nodeKind` has the value `{"@value": "1", "@type": "xsd:boolean"}`
- **THEN** no datatype alert is raised for it

#### Scenario: A declared infinity
- **WHEN** a property of a value shape with `sh:datatype xsd:double` and without `sh:nodeKind` has the value `{"@value": "INF", "@type": "xsd:double"}`
- **THEN** no datatype alert is raised for it

### Requirement: A missing sh:nodeKind constrains no node kind
The datatype check of a value shape without `sh:nodeKind` SHALL raise no datatype or node kind alert for an attribute that is a Relationship, a ListProperty or a JsonProperty, nor for a value whose shape states only the datatype of list elements, and SHALL raise a datatype alert for a property whose value is an IRI or the geometry of a GeoProperty.

#### Scenario: A relationship
- **WHEN** an attribute of a value shape with `sh:datatype xsd:double` and without `sh:nodeKind` is a Relationship, a ListProperty or a JsonProperty
- **THEN** neither a datatype alert nor a node kind alert is raised for it

#### Scenario: A value that is no literal
- **WHEN** a property of a value shape with `sh:datatype xsd:string` and without `sh:nodeKind` has the value `{"@id": "urn:some:iri"}`, or is a GeoProperty
- **THEN** a datatype alert is raised for it

#### Scenario: A stated node kind
- **WHEN** a property of a value shape with `sh:datatype xsd:double` and `sh:nodeKind sh:Literal` has the value `{"@id": "urn:some:iri"}`
- **THEN** a node kind alert is raised for it

#### Scenario: No datatype
- **WHEN** a property of a value shape with neither `sh:datatype` nor `sh:nodeKind` has any value
- **THEN** no datatype alert is raised for it

#### Scenario: Elements of a list
- **WHEN** a property of a `ngsi-ld:hasValue` shape that states `xsd:integer` for the elements of a list only has the value `"abc"`
- **THEN** no datatype alert is raised for it

### Requirement: The documentation says sh:datatype needs no sh:nodeKind
The shacl2flink documentation of `sh:datatype` SHALL state that the check does not need `sh:nodeKind`, which values a shape without `sh:nodeKind` judges, and where a datatype without `sh:nodeKind` is not judged.

#### Scenario: Reading the entry of sh:datatype
- **WHEN** a modeller reads the entry for `sh:datatype` in the shacl2flink documentation
- **THEN** it says that without `sh:nodeKind` the values of `ngsi-ld:hasValue` are judged, that an IRI and a geometry violate every datatype, that Relationships, lists and JSON properties satisfy the shape, and that a datatype inside `sh:not`, inside `sh:xone`, in an `sh:or` with a branch that states none, states a node kind or an `sh:path` or is deactivated, or under a connective of a node shape or of an enclosing attribute is not judged, nor is `rdf:JSON`
