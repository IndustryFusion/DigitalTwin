# semforge-sdk/sparql-deployable Specification

## Purpose
Defines what SemForge says about whether a SPARQL constraint or rule of a package
can be deployed, that is compiled by shacl2flink to Flink SQL, in the SPARQL
editor, the Problems panel and the terminal, and that it says so only as
shacl2flink's own check answers.

## Requirements

### Requirement: A query that cannot be deployed is marked while it is written
While a SPARQL constraint or rule is edited, SemForge SHALL run the query through shacl2flink's check of SPARQL expressions, as a constraint's `SELECT` or a rule's `CONSTRUCT`, once for each target class of the edited shape. When the check refuses it for one of them, SemForge SHALL mark the query with one error `not-deployable` that says it cannot be deployed and gives the check's reason and, when the check names one, its pattern. A query the check accepts SHALL have no such mark.

#### Scenario: A variable as predicate
- **WHEN** a constraint's query reads `$this ?attribute ?value .` on a line of its own
- **THEN** that line is marked as an error that says the query cannot be deployed and why

#### Scenario: Parts the compiler refuses
- **WHEN** a query uses `UNION`, `REGEX` or `ngsild:unitCode`
- **THEN** the mark's reason names `UNION`, `REGEX` or `unitCode`

#### Scenario: A rule
- **WHEN** a rule's `CONSTRUCT` reads `$this ?attribute ?value`
- **THEN** it is marked as an error that says the query cannot be deployed and why

#### Scenario: Two target classes
- **WHEN** the edited shape has two target classes and the check refuses the query for one of them only
- **THEN** the query is marked with the reason of that refusal

#### Scenario: Forms that compile
- **WHEN** a query reads an attribute by a variable predicate with its value, through a named attribute instance, or by a property path
- **THEN** it has no `not-deployable` mark

#### Scenario: Fixed while written
- **WHEN** a marked query is changed to one the check accepts
- **THEN** the mark goes

### Requirement: The mark is where the compiler points
The `not-deployable` mark SHALL be on the line of the query's body that holds the most names (variables, prefixed names, IRIs) of the pattern the check names, or of its reason when it names no pattern.

#### Scenario: The line of the pattern
- **WHEN** a query of several lines is refused for the pattern `$this ?attribute ?value` on its third line
- **THEN** the mark is on the third line, not on the line of `SELECT` or of another pattern

### Requirement: The mark never adds to or takes from the other marks
The `not-deployable` mark SHALL be given only when the query has no other error. When the check fails, the query SHALL get no `not-deployable` mark and SHALL keep every other mark.

#### Scenario: A query that does not parse
- **WHEN** a query does not parse
- **THEN** it has its syntax error and no `not-deployable` mark

#### Scenario: The check fails
- **WHEN** the check raises an error for a query
- **THEN** the query has no `not-deployable` mark and the editor's other diagnostics are given

### Requirement: The package's queries that cannot be deployed are named
The capability check SHALL report, for every SPARQL constraint and rule of the package that the check refuses, an error `SF-CAP-006` on its shape that names the shape, whether it is a constraint or a rule, its message and the reason. `semforge check` SHALL list each as `not-deployable` with the file and line of the query, or the shapes file when the check names no line, and exit 1. `semforge export` SHALL refuse a package with such an error.

#### Scenario: In the Problems panel
- **WHEN** a package has one SPARQL constraint with the message "broken one" whose query reads `$this ?attribute ?value`
- **THEN** the capability check reports one `SF-CAP-006` that names its shape and "broken one"

#### Scenario: A rule in the Problems panel
- **WHEN** a package has one SPARQL rule whose `CONSTRUCT` reads `$this ?attribute ?value`
- **THEN** the capability check reports one `SF-CAP-006` on its shape that calls it a rule

#### Scenario: In the terminal
- **WHEN** `semforge check` is run on that package
- **THEN** it lists a `not-deployable` row at the line of the shapes file where the query starts, naming "broken one", and exits 1

#### Scenario: Export
- **WHEN** `semforge export` is run on that package
- **THEN** it refuses, names the constraint, and writes nothing

#### Scenario: Every query can be deployed
- **WHEN** every SPARQL constraint and rule of a package can be compiled
- **THEN** no `SF-CAP-006` and no `not-deployable` row is reported

### Requirement: Where the check is found
SemForge SHALL use the shacl2flink checkout named by the environment variable `SEMFORGE_SHACL2FLINK`; when that is set to something that is not a directory, there SHALL be none. Otherwise it SHALL use the first `shacl2flink` checkout found in the directory of the package or one of its parents, and else in the directory of SemForge's own files or one of its parents.

#### Scenario: Named
- **WHEN** `SEMFORGE_SHACL2FLINK` names a shacl2flink checkout
- **THEN** that checkout's check is used

#### Scenario: Beside the package
- **WHEN** `SEMFORGE_SHACL2FLINK` is not set and a package lies below a directory that holds a `shacl2flink` checkout
- **THEN** that checkout's check is used

### Requirement: Without the check nothing is said
Where no shacl2flink checkout is found, or it cannot be loaded, SemForge SHALL NOT mark or report any query as not deployable, and SHALL NOT say that a query can be deployed. Loading the check SHALL leave no module or import path of it behind that another module of the same name could pick up.

#### Scenario: No checkout
- **WHEN** `SEMFORGE_SHACL2FLINK` names a directory that does not exist
- **THEN** neither the editor, the capability check nor `semforge check` reports a query as not deployable

#### Scenario: A checkout that cannot be loaded
- **WHEN** the checkout's check imports a module that is not installed
- **THEN** there is no check, and no module or import path of the checkout is left behind

### Requirement: SemForge says nothing about Flink of its own
The SPARQL editor SHALL NOT judge by a list of its own whether shacl2flink can compile a query: it SHALL give no finding about a named attribute instance, a property path, or an attribute no shape nests a payload for, offer no fix that adds a shape for shacl2flink, and its hover SHALL NOT say how shacl2flink reads an attribute. A finding about how a query reads the data SHALL NOT say how shacl2flink reads it.

#### Scenario: A named instance and a path
- **WHEN** a query reads `$this ex:hasStrength ?a . ?a ngsild:hasValue ?s` or `$this ex:hasStrength/ngsild:hasValue ?s`
- **THEN** the editor gives no finding about the form

#### Scenario: An attribute no shape nests a payload for
- **WHEN** a query reads an attribute that no shape nests a payload for, and the cursor is on it
- **THEN** there is no finding about it and the hover does not mention shacl2flink

#### Scenario: The attribute instance read instead of its value
- **WHEN** a query reads `$this ex:hasStrength ?a` and uses `?a` for nothing else
- **THEN** the finding says that `?a` names the attribute instance and offers to read its value, without saying how shacl2flink reads it
