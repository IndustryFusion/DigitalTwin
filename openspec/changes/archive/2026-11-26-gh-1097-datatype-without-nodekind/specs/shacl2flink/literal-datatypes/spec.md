## ADDED Requirements

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
