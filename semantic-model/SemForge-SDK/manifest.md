# SemForge Manifest

## 1. Purpose

This project provides an SDK and development platform for creating, refining, validating, testing, and evolving semantic data models built around:

- NGSI-LD / JSON-LD instance data
- RDF / OWL semantic models
- SHACL constraints
- SHACL-SPARQL rules
- executable positive and negative examples

The project treats semantic modelling as an interactive, test-driven engineering activity rather than as the manual editing of isolated ontology and constraint files.

The central idea is simple:

> Example data, ontology semantics, constraints, validation rules, and expected outcomes should evolve together inside one versioned semantic package.

The SDK is intended to support semantic data infrastructures such as the IndustryFusion Foundation DigitalTwin/SemForge architecture, while remaining generic enough for other domains.

---

## 2. Core Principles

### 2.1 SDK first

The primary product is an SDK.

The command-line interface, VS Code integration, notebooks, language server, graphical views, and other tools are clients of the same core SDK.

No editor or UI shall contain semantic behaviour that is unavailable through the SDK.

### 2.2 Interactive semantic development

Interactive modelling is a central requirement of SemForge. Users must be able to import or create NGSI-LD examples, inspect their structure, inspect the corresponding OWL and SHACL artifacts, and iteratively add, refine, remove, or replace constraints while immediately evaluating the effect on good and bad examples.

SemForge provides two synchronized interaction modes over the same project state.

#### Raw mode

Raw mode exposes NGSI-LD / JSON-LD, RDF / OWL, SHACL, and SHACL-SPARQL / SPARQL directly. Experts can inspect and edit these standards artifacts without an abstraction layer getting in the way.

#### Cooked mode

Cooked mode presents a convenient semantic engineering UI over the same artifacts. It provides structured, navigable views for entity types and instances, recursively nested NGSI-LD attributes and paths, OWL classes/properties/axioms, SHACL shapes and property shapes, SHACL-SPARQL rules, positive and negative examples, expected violations, and validation results.

A user should be able to select an entity type, navigate through a nested attribute structure, inspect the constraints applying at a selected node or path, edit those constraints, and immediately rerun affected examples.

Raw and cooked mode are two synchronized views of the same semantic artifacts. Editing `sh:minCount` in raw SHACL must update the cooked constraint view. Editing cardinality in the cooked view must update the SHACL representation.

The objective is not to hide NGSI-LD, OWL, SHACL, or SPARQL, but to let users move freely between standards-level representations and convenient engineering structures without losing information.

### 2.3 Import and add, not import and infer

Imported NGSI-LD data is evidence and source material.

The SDK may derive candidate structures or constraints from examples, but derived information must remain distinguishable from explicitly declared semantics.

Observed structure must never silently become normative semantics.

For example:

```python
Machine.temperature.observed.datatypes
Machine.temperature.constraints
```

must remain conceptually distinct.

### 2.4 Positive and negative examples are first-class artifacts

A semantic package contains examples that are expected to conform and examples that are expected to violate specific constraints.

Examples are executable specifications.

A negative example should preferably describe not only that validation must fail, but why it must fail.

Example:

```python
semforge.add_bad(
    "examples/bad/missing-filter.jsonld",
    violates="machine.filter.required"
)
```

### 2.5 Regression testing is intrinsic

Every semantic change must be testable against the package's examples.

Changes that cause previously valid examples to fail or previously invalid examples to pass must be visible as semantic regressions.

The SDK should support comparison of validation behaviour across model versions.

### 2.6 OWL and SHACL have different responsibilities

The SDK must not blur open-world ontology semantics and closed-world validation semantics.

OWL is used for semantic modelling. Configured OWL consistency checks are used as sanity checks before the OWL part of a SemForge package is exported.

SHACL is used for explicit validation constraints.

SHACL-SPARQL is used where SHACL Core is insufficient.

The SDK may expose a unified authoring API, but generated artifacts must preserve these semantic distinctions.

### 2.7 Escape hatches are mandatory

High-level APIs must not prevent experts from accessing the underlying technologies.

Users must be able to add or edit:

- RDF triples
- OWL axioms
- SHACL shapes
- SHACL-SPARQL constraints
- SPARQL queries
- raw JSON-LD / NGSI-LD
- implementation-specific validation extensions

The SDK should make common cases convenient without making uncommon cases impossible.

### 2.8 Provenance must be inspectable

Users should be able to determine why a semantic statement or constraint exists.

Where practical, the SDK should track whether a model element originated from:

- imported ontology
- imported SHACL
- imported example data
- derived proposal
- explicit SDK declaration
- manually authored RDF
- external extension

Example:

```python
Machine.temperature.why()
```

may report its declaration source, supporting examples, generated SHACL, and related rules.

---

## 3. Semantic Package

The primary unit of development and distribution is a semantic package.

A package may contain:

```text
machine-semforge/
├── manifest.md
├── semforge.yaml
├── contexts/
│   └── context.jsonld
├── ontology/
│   └── model.ttl
├── constraints/
│   └── shapes.ttl
├── rules/
│   └── constraints.sparql
├── examples/
│   ├── machine-basics/
│   │   ├── minimal-machine.jsonld
│   │   └── missing-identity.jsonld
│   ├── filter-cases/
│   │   ├── running-filter.jsonld
│   │   └── stopped-filter.jsonld
│   └── integration/
│       └── complete-machine.jsonld
├── expectations/
│   └── validation.yaml
└── tests/
```

The exact serialization layout may evolve, but the package concept is stable.

A package must be:

- versionable in Git
- inspectable without proprietary tools
- executable through the SDK
- usable from CI
- usable interactively
- portable between supported development environments

---

## 4. Core Domain Model

The SDK should expose at least the following conceptual objects.

### 4.1 SemForge Package

Represents the complete semantic development unit.

Responsibilities include:

- loading and saving package state
- managing namespaces and contexts
- managing semantic types and properties
- registering examples
- executing validation
- running regression tests
- exposing provenance
- compiling semantic artifacts
- calculating semantic diffs

### 4.2 Semantic Type

Represents an entity or concept such as:

```python
Machine = semforge.type("Machine")
```

A type may expose:

- OWL class semantics
- inherited semantics
- observed NGSI-LD structures
- SHACL constraints
- relationships
- associated examples
- associated rules

### 4.3 Property / Relationship

Properties must be inspectable and editable independently.

Example:

```python
Machine.temperature.required()
Machine.temperature.datatype(float)
Machine.temperature.between(-20, 120)
```

Relationships should support target-type constraints and graph navigation.

Example:

```python
Machine.hasFilter.target(Filter)
Machine.hasFilter.required()
```

### 4.4 Constraint

A constraint is a named, identifiable semantic validation rule.

Constraints should have stable IDs where possible so that:

- negative examples can expect specific violations
- validation reports remain traceable
- regressions can be associated with semantic changes
- tooling can navigate between declaration and failure

### 4.5 Rule

Rules represent constraints that may span several nodes, relationships, values, or semantic conditions.

Example:

```python
semforge.rule("FilterRunningWhileMachineActive")     .target(Machine)     .when(Machine.state == "active")     .require(Machine.hasFilter.state == "running")
```

The SDK may compile such rules to an appropriate target, including:

- SHACL Core
- SHACL property paths
- SHACL-SPARQL
- SPARQL
- future streaming validation targets

### 4.6 Example

Examples are explicitly classified as expected-valid or expected-invalid.

Negative examples should optionally define expected:

- constraint IDs
- focus nodes
- paths
- severities
- messages

### 4.7 Example organization and test scope

Examples must be organizable in arbitrary user-defined subdirectories.

SemForge must not require directory names to correspond to entity types, constraint IDs, rule names, or any other semantic structure. Directory layout is an organizational concern, comparable to how unit-test suites are commonly structured in software projects.

For example:

```text
examples/
├── machine-basics/
├── filter-cases/
├── customer-scenarios/
├── regression-2026-09/
└── integration/
```

SemForge must use explicit test metadata and expectations to determine what an example is intended to test. Folder names may be used for selection and grouping, but must not define semantic meaning.

The test runner should support selecting any subtree or explicitly selected set of examples, for example:

```bash
semforge test examples/filter-cases
semforge test examples/regression-2026-09
```

Examples may be intentionally minimal and need not satisfy all constraints of the complete semantic package.

SemForge must distinguish at least:

- **focused tests**, which evaluate selected constraints or rules against a deliberately limited graph;
- **full conformance tests**, which evaluate the complete applicable constraint set.

A focused positive example therefore means that the tested semantic feature is expected to conform. It does not necessarily mean that the example is a globally complete or valid representation of the entity.

This allows engineers to create small, understandable semantic unit tests around a type, a few attributes, a nested attribute path, or a specific rule without constructing a complete production entity for every test case.

---

## 5. Validation Model

The platform should distinguish several validation activities.

### 5.1 Instance validation

Validate NGSI-LD / JSON-LD instance data against SHACL and related package constraints.

### 5.2 Ontology consistency checks

Execute configured RDF/OWL consistency checks of the OWL ontology.

Ontology consistency must be executed as a sanity check before the OWL part of the ontology is exported.

These checks are not instance validation and must not be presented as equivalent to SHACL constraint checking.

### 5.3 Semantic package validation

Validate the semantic package itself for problems such as:

- unresolved references
- conflicting declarations
- invalid SHACL
- invalid SPARQL constraints
- namespace errors
- broken test expectations
- unsupported compilation constructs

### 5.4 Regression validation

Execute expected-good and expected-bad examples and compare results with declared expectations.

Regression execution may cover the complete package or a user-selected subset of examples, directories, constraints, rules, or semantic features.

A regression report should make behavioural changes explicit.

Example:

```text
Semantic regression detected

Constraint changed:
  Machine.serialNumber
  minCount: 1 -> 0

Affected example:
  examples/bad/missing-serial.jsonld

Expected:
  INVALID because machine.serialNumber.required

Actual:
  VALID
```

---

## 6. Derivation from Examples

The SDK may inspect positive examples and derive candidate model information such as:

- encountered types
- encountered properties
- encountered relationships
- observed datatypes
- observed multiplicities
- observed target types
- observed value ranges
- observed optionality

Derived information is advisory.

The SDK must distinguish:

```text
observed
proposed
declared
```

A user may accept, modify, reject, or supersede proposed constraints.

The project explicitly rejects the assumption that repeated observations automatically define semantic requirements.

---

## 7. Semantic Diff

Semantic change analysis is a core feature.

The SDK should be able to compare two package states and describe changes at a semantic level rather than only as textual diffs.

Examples include:

- property became required
- datatype changed
- allowed value removed
- class hierarchy changed
- relationship target changed
- constraint weakened
- constraint strengthened
- rule removed
- negative example no longer fails
- positive example no longer conforms

Example:

```bash
semforge diff v1.2.0 v1.3.0
```

The result should combine model changes with affected examples.

---

## 8. Tooling Architecture

SemForge is centered on one semantic interpretation model.

```text
                         SemForge Core
                              |
             +----------------+----------------+
             |                |                |
            CLI          Editor Service      CI/API
                              |
                         VS Code UI
                              |
                    +---------+---------+
                    |                   |
                 Raw mode           Cooked mode
```

### 8.1 SemForge Core

The core contains the canonical interpretation of NGSI-LD entities and recursively nested attributes, OWL model elements, SHACL constraints, SHACL-SPARQL rules, examples and expectations, validation results, provenance, and semantic diffs.

The implementation language is an internal concern. Python may be practical because mature RDF and SHACL libraries exist there, but SemForge does not require users to work in a generic Python runtime.

### 8.2 CLI

The CLI exposes core operations for automation and CI:

```bash
semforge init
semforge inspect
semforge derive
semforge validate
semforge test
semforge explain
semforge diff
semforge export
```

### 8.3 Editor service

The editor needs a clean interface to SemForge Core for diagnostics, semantic navigation, references across NGSI-LD/OWL/SHACL, constraint inspection and editing, completion, example references, and regression feedback.

LSP (Language Server Protocol) is the standardized protocol editors such as VS Code use to communicate with language-aware backend services. It covers features such as diagnostics, completion, hover, references, and go-to-definition.

LSP is an implementation option, not a conceptual requirement. SemForge-specific interactive operations that do not map naturally to LSP may use a dedicated local API.

### 8.4 VS Code

VS Code is the preferred initial interactive environment. The extension should provide raw and cooked interaction, including structured entity/nested-attribute browsing, ontology browsing, constraint/rule browsing, interactive constraint editing, immediate execution against selected good/bad examples, navigation between representations, validation results, semantic diffs, and regression/test views.

The VS Code layer must not become the semantic engine.

### 8.5 No generic notebook requirement

Jupyter is not a first-class architectural requirement.

SemForge already defines explicit domain structures for entities, nested attributes, ontology elements, constraints, rules, examples, and validation results. The primary interactive experience should expose those structures directly rather than requiring users to construct workflows in a generic Python notebook.

A programmatic API may still exist for automation, extensions, and embedding, but the product does not depend on Jupyter.

---

## 9. Standards

The project should prefer standards over proprietary representations.

Primary standards include:

- RDF
- RDFS
- OWL
- SHACL
- SHACL-SPARQL
- SPARQL
- JSON-LD
- NGSI-LD

Project-specific metadata should be limited to capabilities not represented adequately by those standards, such as:

- example expectations
- provenance of derived proposals
- package configuration
- compilation settings
- regression metadata

---

## 10. NGSI-LD

NGSI-LD is treated as a first-class instance representation, not merely as generic JSON.

SemForge must understand Entity, Property, Relationship, GeoProperty, relevant ListProperty and JsonProperty structures, JSON-LD contexts, identifiers, types, dataset identifiers, timestamps, and nested attributes.

### 10.1 Arbitrarily nested attributes

SemForge must not assume a fixed attribute depth.

NGSI-LD attributes may themselves contain attributes, which may again contain further attributes. The SemForge interpretation model must therefore be recursive and capable of representing arbitrary nesting depth.

```text
Entity
└── Attribute
    ├── value/object
    └── Attribute
        ├── value/object
        └── Attribute
            └── ...
```

The cooked UI must allow users to navigate these structures naturally and address constraints at any depth. Constraints may apply to a top-level attribute, a nested attribute, an arbitrarily deep attribute path, or relationships between nodes reached through such paths.

No API, UI component, derivation mechanism, or validation abstraction may rely on a hard-coded maximum nesting level.

NGSI-LD data must be convertible to the RDF representation required for SHACL validation and ontology consistency checks without losing the semantics of nested attributes or their paths.

---

## 11. Extensibility

The project should support extension points for:

- custom validators
- custom rule compilers
- additional ontology consistency checkers
- domain-specific model APIs
- serialization formats
- semantic importers
- streaming validation backends
- external semantic registries
- graphical model views

A future IndustryFusion integration may compile suitable validation rules to streaming execution environments such as Flink SQL.

Such compilation should be implemented as an extension of the semantic model, not hard-coded into the SDK core.

---

## 12. Non-Goals

The project is not intended to:

- replace RDF databases
- replace OWL reasoners
- replace SHACL engines
- create a proprietary ontology language
- infer authoritative semantics automatically from arbitrary data
- hide RDF, OWL, SHACL, or SPARQL from expert users
- make VS Code a mandatory runtime dependency
- treat LLM-generated semantics as automatically trustworthy

LLMs may later assist with authoring, explanation, rule proposal, or example generation, but generated semantic artifacts must remain explicit, inspectable, testable, and subject to the same validation process as human-authored artifacts.

---

## 13. Initial Developer Experience

A minimal target workflow is:

```python
from semforge import SemForge

semforge = SemForge.create("machine-model")

semforge.add_good("examples/good/machine.jsonld")
semforge.add_bad(
    "examples/bad/missing-serial.jsonld",
    violates="machine.serialNumber.required"
)

semforge.derive()

Machine = semforge.type("Machine")

Machine.serialNumber.required()
Machine.serialNumber.datatype(str)

Machine.temperature.optional()
Machine.temperature.datatype(float)
Machine.temperature.between(-20, 120)

report = semforge.test()

print(report)
```

The same project should support:

```bash
semforge test .
```

and eventually provide equivalent feedback directly inside VS Code.

---

## 14. Definition of Success

The project succeeds when semantic modelling feels like normal software engineering.

A developer should be able to:

1. start from real NGSI-LD examples
2. inspect the structures already present
3. add or refine ontology semantics
4. add simple SHACL constraints through an SDK
5. add complex SHACL or SHACL-SPARQL rules
6. add expected-good and expected-bad examples
7. execute all examples as regression tests
8. understand why a validation rule exists
9. identify which examples are affected by a semantic change
10. review semantic changes through meaningful diffs
11. use the same project from VS Code, CLI, CI, and programmatic integrations
12. access the underlying RDF, OWL, SHACL, SPARQL, and NGSI-LD artifacts at any time

The long-term objective is to make semantic data engineering reproducible, interactive, testable, and maintainable at the same level expected from conventional software development.
