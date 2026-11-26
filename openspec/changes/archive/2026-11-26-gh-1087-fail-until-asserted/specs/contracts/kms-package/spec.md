# contracts/kms-package Delta

## ADDED Requirements

### Requirement: An example that expects a violation asserts one
An example of a package's suite that expects a violation SHALL meet its expectations only when it asserts at least one constraint and every asserted constraint fires. A violation that the example does not assert, and a pinned residue, SHALL NOT take the place of an assert.

#### Scenario: A violation nobody asserted
- **WHEN** an example declares `expect: invalid` without asserts, and one of its entities violates a constraint
- **THEN** the example does not meet its expectations, and the report says that it asserts nothing

#### Scenario: A violation as asserted
- **WHEN** an example declares `expect: invalid` and asserts a constraint on an entity, and that constraint fires on that entity
- **THEN** the example meets its expectations

#### Scenario: A valid example
- **WHEN** an example declares `expect: valid`, asserts nothing and nothing is violated
- **THEN** the example meets its expectations
