# Proposal

Issue: #995

## Why

The OPC UA tools write the instances of a model together with the shapes (`shacl.ttl`) and the ontology
(`entities.ttl`) that describe them. Today the shapes and the attribute declarations come only from a walk along the
type definitions, starting at the root type. A type that the instances use, but which the walk never reaches as the
type definition of a child, gets no shape, and the attributes of its entities are declared only by chance or not at
all. The standard Machinery building blocks are such a case: a machine type declares `MachineryBuildingBlocks` as a
plain folder and adds the state machines `MachineryItemState` and `MachineryOperationMode` to it; the instances
contain both state machines, and nothing validates them. A package built this way looks complete while part of it is
never checked.

Since #985 (`opcua/instance-declaration-shapes`) the type walk also scans the types of the members a declaration adds,
so those state machines have their shapes and are validated. Two gaps remain: the attributes that a declaration or
an instance adds beyond the type (the folder's relationships to the state machines) are declared nowhere in the
ontology, and nothing reports a part of the instances that the shapes or the ontology still do not cover.

## What Changes

- The spec states what the type walk does since #985: every object type of which the instances contain an entity
  has its node shape with the rules its type definition and supertypes define, wherever the type occurs in the
  model, and the shape of a type is the same whichever way it is reached. No code changes for this; tests hold it.
- Every attribute that an entity of the instances carries is declared in the ontology, with a domain that the
  entity's type or one of its supertypes satisfies. This includes attributes that an instance declaration or the
  instance itself adds beyond the type.
- The output does not grow beyond that: a type of an imported companion specification that no node of the instances
  uses, and that the type walk does not reach, gets no shape.
- The generator reports every type and every attribute of the instances that the shapes or the ontology still do not
  capture, instead of passing silently.
- The instances themselves do not change.

## Capabilities

### New Capabilities

- `opcua/instance-coverage`: what the shapes and the ontology written by the OPC UA tools must cover of the
  instances written with them, the limit on what they add, and the report of anything not covered.

### Modified Capabilities

None.

## Impact

- **opcua**: `owl2instances.py` declares the attributes of the entities it writes and reports what is not covered.
  Models whose instances carry such attributes gain declarations in `entities.ttl`; their shapes and instances are
  unchanged.
- **shacl2flink**: no change; the shapes it compiles are the same.
- **SemForge SDK**: no code change; it shows the added declarations like any other.
- **Contracts**: no contract between components changes. `contracts/opcua-live-data` (attribute forms and entity
  identity) and `contracts/kms-package` (package layout) are untouched.
- **Relation to #985** (`gh-985-instance-declaration-shapes`, merged): #985 validates the members an instance
  declaration adds beyond its type and gives the types of those members their shapes; this change declares the added
  attributes in the ontology, and its report counts what #985's declaration shapes constrain as covered.

## Out of Scope

- SHACL rules for members that an instance declaration adds beyond its type (that the folder above must contain the
  two state machines): that is #985.
- SHACL rules for members that only an instance adds, which no type or declaration defines: no normative rule
  exists for them. They are declared in the ontology and named in the report.
- Shapes for every type of the imported companion specifications.
- Variable types: the shapes of variables and their properties are unchanged.
- The form of the instances and of existing shapes.
