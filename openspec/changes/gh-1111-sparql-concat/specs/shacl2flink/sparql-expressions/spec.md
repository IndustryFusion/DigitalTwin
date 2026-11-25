## ADDED Requirements

### Requirement: Functions on texts
shacl2flink SHALL compile `CONCAT` and `STR` in SPARQL constraints and rules, also nested in each other and in `IF`, for SQLite and for Flink. The result SHALL be the text SPARQL gives: the arguments in their order, each with all of its characters; `STR` of an IRI is the IRI, of a literal its text. An unbound argument SHALL make the result unbound. A number is written as the platform holds it.

#### Scenario: A message of a constraint
- **GIVEN** a constraint with `sh:message "{?text}"` which binds `?text` to `CONCAT("Max violation: ", STR(?value), " > ", STR(?max))`
- **WHEN** an entity violates it with the value 11 and the maximum 10
- **THEN** the text of its alert contains `Max violation: 11 > 10`

#### Scenario: Delimiters inside a text
- **WHEN** an argument is a text with `<`, `>`, a quote or a brace in it
- **THEN** the result contains it unchanged

#### Scenario: Chosen text
- **WHEN** an argument of `CONCAT` is `IF(BOUND(?min) && ?value < ?min, CONCAT(" < ", STR(?min)), CONCAT(" > ", STR(?max)))`
- **THEN** the result contains the text of the branch whose condition holds

#### Scenario: Unbound argument
- **GIVEN** a variable bound in an `OPTIONAL` only
- **WHEN** it is an argument of `CONCAT` and has no value for an entity
- **THEN** the result is unbound for that entity

#### Scenario: IRI
- **WHEN** `STR` is given an IRI
- **THEN** the result is the IRI as a text, without `<` and `>`

#### Scenario: In a filter and in a rule
- **WHEN** `STR` or `CONCAT` is compared in a `FILTER`, or its result is the value a rule constructs
- **THEN** it is compared, or written, as that text
