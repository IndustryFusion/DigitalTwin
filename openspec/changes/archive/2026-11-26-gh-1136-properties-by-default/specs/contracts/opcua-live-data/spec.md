## MODIFIED Requirements

### Requirement: Bindings vocabulary
Bindings SHALL use one vocabulary, which the generated bindings, the dataservice, the test servers and the binding validation all agree on. Produced by: model tools. Relied on by: dataservice, test servers, binding validation.

#### Scenario: Generated bindings
- **WHEN** the pump example's bindings are generated
- **THEN** they conform to the binding validation, and the dataservice finds all 64 of them
