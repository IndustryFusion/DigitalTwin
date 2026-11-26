# shacl2flink/sparql-expressions Specification

## Purpose
Defines which SPARQL expressions of a package shacl2flink compiles, what a
compiled expression answers, and what is reported about one that cannot be
compiled.

## Requirements

### Requirement: Every expression that cannot be compiled is reported
A build SHALL report every `sh:select` and `sh:construct` of the package that it cannot compile, in one run, together with the shapes it cannot compile. The build SHALL then stop with an error, without a stack trace, and write no validation.

#### Scenario: Two expressions of two shapes
- **WHEN** a package is built that holds one expression that compiles and two that do not, of different shapes
- **THEN** the build fails and reports both, each with its shape, target, message, file, line, reason and query, and does not report the first
- **AND** no validation is written

#### Scenario: A rule
- **WHEN** the `sh:construct` of a rule cannot be compiled
- **THEN** it is reported like a constraint

#### Scenario: A failure nobody foresaw
- **WHEN** the compiler fails on an expression for a reason it does not handle
- **THEN** the expression is reported like the others, as a defect of the compiler

### Requirement: A report leads to the expression
The report of an expression SHALL name the shape, the target class, the constraint's message, the file and line of the query where the file holds it as written, the reason, the pattern that is the reason where there is one, and the query without its prefixes.

#### Scenario: The place
- **WHEN** an expression is reported
- **THEN** the report names its shape, target and message, and the line of the file at which the query starts

#### Scenario: The pattern that is the reason
- **WHEN** one pattern of a query cannot be translated
- **THEN** the report shows that pattern

### Requirement: The check needs no build
There SHALL be a command that reports the same for a shapes file without building the package, and that fails when there is a report. It SHALL also report about one expression that is given to it and in no file, and SHALL offer the report in a machine-readable form.

#### Scenario: A shapes file
- **WHEN** the command runs on a shapes file with one expression that cannot be compiled
- **THEN** it reports that expression and fails

#### Scenario: Nothing to report
- **WHEN** every expression of the file can be compiled
- **THEN** the command says so and succeeds

#### Scenario: A draft
- **WHEN** the command is given a query, its kind and its target class
- **THEN** it reports about that query only

### Requirement: An attribute is recognised by the pattern that reads it
An expression SHALL read the value of an attribute as `?entity <attribute> [ ngsild:hasValue ?v ]`, its target as `?entity <attribute> [ ngsild:hasObject ?o ]` and its time as `[ ngsild:observedAt ?t ]` together with one of them. This SHALL hold whether or not a shape declares the attribute, and whether or not that shape has a target class.

#### Scenario: An attribute declared by a shape without a target class
- **WHEN** a query reads a relationship that only a shape without a target class declares
- **THEN** it compiles, and finds the entities that have the relationship

#### Scenario: An attribute no shape declares
- **WHEN** a query reads the value of an attribute that no shape declares
- **THEN** it compiles, and an IRI and a literal are each found as what they are

### Requirement: An attribute may be read in several ways
The attribute instance MAY be named by a variable, MAY hold several payloads, and MAY be skipped by a path; a constant MAY stand for the variable of a value or a target. Each SHALL answer what the form with one variable in each instance answers.

#### Scenario: A named instance
- **WHEN** a query says `?entity <attribute> ?a . ?a ngsild:hasValue ?v`
- **THEN** it answers what `?entity <attribute> [ ngsild:hasValue ?v ]` answers

#### Scenario: Several at once
- **WHEN** a query says `?entity <attribute> [ ngsild:hasValue ?v ; ngsild:observedAt ?t ]`
- **THEN** it answers what the two patterns on the same attribute answer

#### Scenario: The time in a pattern of its own
- **WHEN** a query reads the value and, in another pattern on the same attribute of the same entity, the time
- **THEN** both are of the same instance

#### Scenario: A path
- **WHEN** a query says `?entity <attribute>/ngsild:hasValue ?v`
- **THEN** it answers what `?entity <attribute> [ ngsild:hasValue ?v ]` answers

#### Scenario: A constant
- **WHEN** a query says `?entity <attribute> [ ngsild:hasValue <constant> ]`, or `ngsild:hasObject` with an IRI
- **THEN** it finds the entities whose attribute has that value or target

#### Scenario: A constant target that does not exist
- **WHEN** a query says `?entity <attribute> [ ngsild:hasObject <iri> ]`, and no entity has that IRI
- **THEN** it finds the entities whose attribute has that target

#### Scenario: A time is there
- **WHEN** a query reads the time of an attribute, and the instance has none
- **THEN** there is no solution

### Requirement: A target that is read is an entity
A variable for the target of a relationship SHALL stand for an entity that exists, as a deleted target is one that a constraint has to notice.

#### Scenario: The target was deleted
- **WHEN** a query says `?entity <attribute> [ ngsild:hasObject ?target ]`, and the target does not exist
- **THEN** there is no solution

### Requirement: The predicate of an attribute may be a variable
`?entity ?attribute [ ngsild:hasValue ?v ]` SHALL read every Property of the entity, and `?entity ?attribute [ ngsild:hasObject ?o ]` every Relationship, with the name of the attribute as the variable's value. The name SHALL be usable like any IRI: compared, and looked up in the knowledge, before or after the attribute is read.

#### Scenario: Any attribute with a value
- **WHEN** a query reads `$this ?attribute [ ngsild:hasValue ?v ]` and filters on `?v`
- **THEN** it finds the entities with any Property of such a value

#### Scenario: By name
- **WHEN** it filters on `?attribute` with `=`, `IN` or `NOT IN`
- **THEN** only the attributes of those names count

#### Scenario: By the knowledge
- **WHEN** the query says something about `?attribute` that the knowledge holds for some attributes
- **THEN** only those attributes count

#### Scenario: Any relationship to the target
- **WHEN** a query says `?other ?relationship [ ngsild:hasObject $this ]`
- **THEN** it finds the entities that another entity refers to by any relationship

### Requirement: A compiled expression answers what SPARQL answers
A constraint SHALL report an entity exactly when the query, with `$this` bound to it, has a solution, for every supported form and whatever the first pattern of the query is. The offline checks and Flink SHALL agree.

#### Scenario: OPTIONAL first
- **WHEN** a query starts with an `OPTIONAL` and compares what it reads with what a later pattern reads
- **THEN** it answers the same as with the `OPTIONAL` last

#### Scenario: Only a NOT EXISTS
- **WHEN** a query consists of one `FILTER NOT EXISTS`
- **THEN** it finds the entities of the target class for which the pattern has no solution

#### Scenario: The same attribute inside
- **WHEN** a query reads an attribute and, in an `EXISTS` or `NOT EXISTS`, the same attribute with another condition
- **THEN** the inner pattern looks for an instance of its own

#### Scenario: OPTIONAL with a FILTER
- **WHEN** an `OPTIONAL` holds a pattern and a `FILTER` that fails
- **THEN** the entity stays, without what the `OPTIONAL` would give

#### Scenario: OPTIONAL with several patterns
- **WHEN** an `OPTIONAL` reads two attributes of an entity that has one of them
- **THEN** the entity stays, without either

#### Scenario: Conditions
- **WHEN** a query combines conditions with `&&`, `||`, `!`, `BOUND`, `IN` or `NOT IN`
- **THEN** they hold as SPARQL says

#### Scenario: The knowledge
- **WHEN** a query reads the knowledge with `<a>/<b>`, `^<a>` or `rdfs:subClassOf*`
- **THEN** it answers what these paths say, for every class that the knowledge names

#### Scenario: A variable without a value
- **WHEN** a condition compares a variable that an `OPTIONAL` gave no value, also negated
- **THEN** that comparison holds neither way, and `!bound(?v) || ?v > 5` holds for the entity

#### Scenario: Another name
- **WHEN** a query gives a value, or a number it computes, another name with `BIND`
- **THEN** it is compared under that name as what it is

#### Scenario: An IRI from the knowledge
- **WHEN** a query reads an IRI from the knowledge and then asks, also in an `EXISTS` or `OPTIONAL`, for an attribute with that IRI as its value
- **THEN** the attributes with that value are found

#### Scenario: One value in two places
- **WHEN** a query reads one variable from two attributes
- **THEN** there is a solution only where both hold the same value

#### Scenario: A certain entity
- **WHEN** a query names an entity by its IRI and reads an attribute of it
- **THEN** the attribute of that entity is read

#### Scenario: A value a rule writes
- **WHEN** a rule writes a value of an attribute that is an IRI in one shape and a literal in another
- **THEN** it is written as what the value is

#### Scenario: An entity compared
- **WHEN** a query compares an entity with an IRI or with another entity
- **THEN** they are equal exactly when they are the same

#### Scenario: On Flink
- **WHEN** queries of these forms run as constraints on Flink, on entities written through the context broker
- **THEN** the alerts are those of the entities SPARQL finds

### Requirement: Numbers are compared as numbers
In `<`, `<=`, `>` and `>=`, and in `=`, `!=`, `IN` and `NOT IN` with a numeric constant or a cast to a number, a value SHALL be compared as the number its text is: an optional sign, digits with an optional decimal point, and an optional exponent. A string whose text is a number SHALL be compared as that number, since the platform sends both alike.

#### Scenario: Two values
- **WHEN** a query asks for `?v > ?w`, and an entity has the values 9 and 10
- **THEN** it is not found, and with the values 10 and 9 it is

#### Scenario: A constant
- **WHEN** a query asks for `?v = 7`, and an entity has the declared double `"7.0"`
- **THEN** it is found

#### Scenario: A constant in a pattern
- **WHEN** a query says `?entity <attribute> [ ngsild:hasValue 7 ]`, and the value is the declared double `"7.0"`, or `"10"` and the value is the plain number 10
- **THEN** the entity is found, as with `FILTER(?v = 7)` and `FILTER(?v = "10")`: the platform keeps no datatype for a plain value

### Requirement: A text is not compared with a number
A value whose text is no number SHALL make a comparison with a number false, `!=` included. Two values whose texts are no numbers SHALL be compared as texts.

#### Scenario: A text
- **WHEN** a query asks for `?v > 5` or `?v != 5`, and the value is the text `abc`
- **THEN** the entity is not found

#### Scenario: Two texts
- **WHEN** a query asks for `?v > "abc"`, and the value is the text `abd`
- **THEN** the entity is found

#### Scenario: A text that a program might read as a number
- **WHEN** the value is the text `5d`, `0x10` or ` 5 `
- **THEN** it is no number, on the offline checks and on Flink

### Requirement: What is not supported is refused by name
An expression that uses something that is not supported SHALL NOT be compiled, and the reason SHALL name it.

#### Scenario: An attribute read otherwise
- **WHEN** a query reads an attribute without its instance, a variable predicate without an attribute instance, a sub-attribute, another member of an instance, one instance of two attributes, or two values or two targets of one attribute of an entity outside of an `EXISTS` or `NOT EXISTS`
- **THEN** it is not compiled, and the reason names it

#### Scenario: Parts of SPARQL
- **WHEN** a query uses `UNION`, `MINUS`, `VALUES`, a sub-select, or a path or function that is not supported
- **THEN** it is not compiled, and the reason names it

#### Scenario: Forms that would answer otherwise
- **WHEN** a query gives an entity another name with `BIND`, uses one variable for a value of an attribute and a literal of the knowledge outside a blank node, reads an attribute again after an `OPTIONAL` that reads it, names an entity by its IRI in an `OPTIONAL` or a group, or holds a constant inside a blank node of the knowledge
- **THEN** it is not compiled, and the reason names it

#### Scenario: Loose ends
- **WHEN** a query uses a variable nothing binds, patterns that are not connected with the target, an `OPTIONAL` whose patterns are connected with each other only through something outside of it, an `OPTIONAL` with a `FILTER` around patterns on attributes that are read before it, or a blank node as a subject that nothing points at
- **THEN** it is not compiled, and the reason names it

### Requirement: The supported forms are documented
The documentation of shacl2flink SHALL list the supported forms and those that are not, how numbers are compared, that this differs from a comparison of texts, and how an expression is checked without a build.

#### Scenario: Reading the documentation
- **WHEN** an author reads the documentation of SPARQL expressions
- **THEN** it says which forms compile, how numbers are compared and how to check an expression
