Issue: #1004

# Proposal

## Why

A browse name in OPC UA is a QualifiedName: a namespace and a name. When the OPC UA tools generate instances, they decide which member of the parent's type (or of a declaration, see `opcua/instance-declaration-shapes`) a child is. Today they compare only the name for objects, but name and namespace for variables. An object child `2:Link` is taken for the type's member `1:Link`, while a variable `2:Status` below it is not taken for the `1:Status` that the declaration of `Link` adds. Validation then reports a missing member one level too deep, on members that are present in another namespace, and does not report the member that is really missing. The data type and value rank of a variable are likewise taken from the parent type's variable of the same name, whatever its namespace.

## What Changes

- A child is a member that a type or a declaration declares with a fixed name only when the namespace and the name of its browse name both agree with the declared member: for objects and variables alike, for the members of a type and for the members a declaration adds.
- A child that is no declared member keeps its own attribute, named from its own namespace, and the missing member is reported on the entity that lacks it.
- Instances of a placeholder may have browse names in any namespace; their membership is decided by name and type as today.
- A variable's data type and value rank come only from the declared variable with the same QualifiedName.
- The documentation of the OPC UA tools describes the rule.

Models whose instances use browse names of another namespace than their type's declarations now get the violations at the entity that lacks the member, instead of one level below.

## Capabilities

### New Capabilities
- `opcua/member-identity`: which member that a type or a declaration declares a child of an instance is, as the generated instances and shapes see it.

### Modified Capabilities

## Impact

- **opcua**: `owl2instances.py` and the shape library compare members by QualifiedName; the generated instances of models with browse names of another namespace than their type's declarations change (such children keep their own attributes), and so do their KMS packages. Models whose browse names agree with their types are unchanged.
- **Contracts**: no contract between components changes. Attribute names already follow the namespace of the browse name; only which attribute a child gets changes for the affected models.

## Out of Scope

- Changing how placeholder membership is decided by name and type (`opcua/instance-declaration-shapes`).
- Finding a variable's data type and value rank in the parent type's supertypes, or for members declared as properties.
- Repairing models whose browse names use the wrong namespace.
