## MODIFIED Requirements

### Requirement: sh:hasValue compares a string by its text
When the constant of `sh:hasValue` is a string, or a literal of any datatype that is neither numeric nor `xsd:boolean` (such as `xsd:gYear`, `xsd:token` or a datatype of the model's own), a value SHALL satisfy it only when the text the platform sends for the value is exactly the constant as written, even when both texts read as the same number. A value without a declared type, or declared `xsd:string`, is compared by its text. A plain number is sent as JavaScript writes numbers: the shortest digits that identify the number, without a decimal point when it is whole, and with an exponent from 10^21 up (`1e+21`) and below 10^-6 (`1e-7`); `NaN` and the infinities are never sent for a number. A boolean, plain or declared, is sent as `true` or `false`.

The one exception is a value declared with a numeric XSD datatype: it SHALL be compared by its value, and satisfy the constant only when the constant is the text JavaScript writes for a finite number and the value is that number. This holds also when the value was written as a string, such as `{"@value": "1.0", "@type": "xsd:double"}`, which the platform sends as the text `1.0`, because the validation of the model before it reaches the platform cannot tell it from the number `1.0`; comparing by value is the only way both validations agree on it.

#### Scenario: The same text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the string value `"1.0"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: The same number in another text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the string value `"1"`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A plain number sent as the constant
- **WHEN** a property of a shape with `sh:hasValue "1"` has the plain value `1` or `1.0`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A declared number sent as the constant
- **WHEN** a property of a shape with `sh:hasValue "1"` has the value `{"@value": 1, "@type": "xsd:double"}` or `{"@value": 1, "@type": "xsd:integer"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A number sent in another text than the constant
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the plain value `1` or `1.0`, or the value `{"@value": 1, "@type": "xsd:double"}` or `{"@value": 1, "@type": "xsd:integer"}`
- **THEN** a `sh:hasValue` alert is raised for it

#### Scenario: A declared number written as a string
- **WHEN** a property of a shape with `sh:hasValue "1"` has the value `{"@value": "1.0", "@type": "xsd:double"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A declared number written as a string against its own text
- **WHEN** a property of a shape with `sh:hasValue "1.0"` has the value `{"@value": "1.0", "@type": "xsd:double"}`
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

#### Scenario: A constant of another datatype
- **WHEN** a property of a shape with `sh:hasValue "2020"^^xsd:gYear` has the plain value `2020`, the string value `"2020"` or the value `{"@value": "2020", "@type": "xsd:gYear"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A constant of another datatype against a number
- **WHEN** a property of a shape with `sh:hasValue "1"^^xsd:token`, or with `sh:hasValue "1"` of a datatype of the model's own, has the plain value `1` or `1.0`, or the value `{"@value": 1, "@type": "xsd:double"}`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A text that is no number the platform sends
- **WHEN** a property of a shape with `sh:hasValue "NaN"` has the plain value `0`
- **THEN** a `sh:hasValue` alert is raised for it, and none for the string value `"NaN"`

#### Scenario: A boolean sent as the constant
- **WHEN** a property of a shape with `sh:hasValue "true"` has the plain value `true`, the value `{"@value": "1", "@type": "xsd:boolean"}` or the string value `"true"`
- **THEN** no `sh:hasValue` alert is raised for it

#### Scenario: A boolean against another text
- **WHEN** a property of a shape with `sh:hasValue "1"` has the value `{"@value": "1", "@type": "xsd:boolean"}`, or a property of a shape with `sh:hasValue "true"` has the string value `"True"`
- **THEN** a `sh:hasValue` alert is raised for it

### Requirement: The rule is documented
The shacl2flink documentation SHALL state how plain numbers, declared types and strings satisfy `xsd:double` and `xsd:integer`, that a whole-valued double has to be declared with `@type`, and that strings are judged by their text unlike in a conformant SHACL engine. It SHALL state that `sh:hasValue` compares a number constant by its value, a string constant with the text the platform sends and how the platform writes a number, and a boolean constant as a boolean, unlike a conformant SHACL engine, which compares value and datatype.

#### Scenario: Reading the documentation of sh:datatype
- **WHEN** a modeller reads the entry for `sh:datatype` in the shacl2flink documentation
- **THEN** it says that a plain `80.0` is an integer, that `{"@value": 80, "@type": "xsd:double"}` is the way to write a whole-valued double, and that `"80.0"` as a string satisfies `xsd:double`

#### Scenario: Reading the documentation of sh:hasValue
- **WHEN** a modeller reads the entry for `sh:hasValue` in the shacl2flink documentation
- **THEN** it says that `80`, `80.0`, a declared `xsd:double` `80` and the string `"80.0"` all satisfy `sh:hasValue 80.0` and `sh:hasValue 80`, that this differs from a conformant SHACL engine, that a plain `1`, a plain `1.0` and a declared `xsd:double` `1` satisfy `sh:hasValue "1"` while only the string `"1.0"` satisfies `sh:hasValue "1.0"`, and that `sh:hasValue true` is satisfied by a plain `true`, a declared `xsd:boolean` `true` or `1` and the string `"true"` but not by `"True"`, `"1"` or the number `1`

## ADDED Requirements

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
