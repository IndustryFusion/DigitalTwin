# Design

## Context

`owl2instances.py` runs in two passes over the instance ontology written by `nodeset2owl.py`:

1. **Type pass.** Starting at the root type (given with `-t`, found through the Machinery folder, or all types of the
   main namespace with `--type-all` / `--maximalshacl`), it writes a node shape per type it reaches and declares the
   attributes of those types in the ontology (`owl:ObjectProperty` with `rdfs:domain`).
2. **Entity pass.** Starting at the root entities, it walks the real instance nodes along hierarchical,
   `Organizes` and non-hierarchical references and writes one entity per object node. It reads the shapes of pass 1
   to name attributes, recognise placeholders and assign `datasetId`s.

When #995 was filed, the type pass continued only with each child's *type*, so a type that occurs only inside an
instance declaration (the Machinery building blocks: a `FolderType` child to which the declaration adds the state
machines) got no shape. Since #985 (`opcua/instance-declaration-shapes`), the type pass also builds a declaration
shape from what a declaration adds, and the types of the added members are scanned like any other type: they get
their node shapes. What #985 does not do is declare the *attributes* that a declaration adds (the folder's
relationships to the state machines) in the ontology, and nothing reports a part of the instances that is still not
covered.

Measured on main after #985, with and without a pre-pass that scans the type of every instance node (the first draft
of this change): `shacl.ttl` is the same for all 26 owl2instances test cases (including this change's own case, a
folder whose declaration adds a state machine type) and for the pump, laser and simple example packages.

## Goals / Non-Goals

**Goals:**
- Ontology declarations for every attribute the instances carry.
- A report of what the shapes or the ontology still do not cover, so a gap is visible instead of silent.
- The shape requirements of `opcua/instance-coverage` (every type of the instances has its shape, independent of the
  path to it, nothing for unused types), which the type pass meets since #985, held by tests.

**Non-Goals:**
- Rules for members an instance declaration adds (#985) or that only an instance adds.
- Changing the instances, entity ids or attribute names.
- Changing the shapes of variables.

## Decisions

### D1: No pre-pass over the types of the instance nodes

The first draft scanned, before the shapes were written, the type of every instance node reached from the root
entities, and gave each type without a shape its own. After #985 that pre-pass adds no shape on any test case or
example package (see Context), so it is not part of this change. It would also have moved the determination of the
root entities before the shapes are written, a change to the order of `owl2instances.py` with no effect left to
justify it.

The type requirements stay in the spec and are tested (the declaration case checks the shape of the added type, the
path independence, the missing mandatory variable and, on the pump case, that no unused shape is written). If a model
reaches a type in a way the type pass does not follow, D3 names that type as having no shape; a pre-pass can be
added then, for that case.

### D2: Declare every attribute the entity pass writes

When the entity pass writes an entity, every attribute it carries that has no `rdfs:domain` among the entity's type
and its supertypes, neither in the written ontology nor in the loaded ones, is declared with the entity's type as
domain, in the same form the type pass uses. Attributes already declared for the type or a supertype are left
alone, so the existing declarations do not change; the node reference attribute, which the base ontology declares
for `BaseObjectType`, gets no declaration. The public laser example shows the gap this closes: it uses the same
Machinery building blocks pattern, and the relationships from its folders to the state machines are declared
nowhere on main.

Alternative: declare every attribute with the entity's own type unconditionally. Adds redundant domains for every
subtype. Rejected.

### D3: One coverage warning after the outputs are written

After the outputs are written, compare the instances with the shapes and the ontology and write one warning through
the existing warning mechanism (code `UNCOVERED_INSTANCE_TERMS`, suppressible with `-sw` like the others), grouped
per type: types without a node shape, attributes without a covering domain, and attributes that are not constrained.
An attribute counts as constrained if a shape targeting the entity's type or a supertype has a property shape for it,
or if a declaration shape constrains it that a relationship of another entity applies to this entity (`sh:node` on
`ngsi-ld:hasObject` of that relationship's property shape, as #985 writes it). Members that #985 leaves unvalidated,
more than one relationship deep, are therefore named, next to #985's own `DEEP_DECLARATION_ADDITIONS` warning. The
exit status does not change.

Alternative: fail the run. Members that only an instance adds are legitimate in OPC UA and have no normative rule;
failing would break existing models. Rejected; a failing mode can follow later if wanted.

## Risks / Trade-offs

- **Multiple `rdfs:domain`s are an intersection in OWL.** The type pass already declares an attribute with one domain
  per type that defines it; D2 adds a domain only where none covers the entity's type, so it follows the existing
  convention without adding to it where not needed. Changing the convention (e.g. a union domain) is out of scope.
- **Coverage warning noise**: models whose instances add members of their own, or have declaration additions more
  than one relationship deep, show the warning. It is grouped per type, and suppressible.
- **A type the type pass does not reach** would show up only in the warning, not as a shape (D1). That is the
  intended trade: no code for a case none of the measured models has.
