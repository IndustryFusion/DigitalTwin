# Design

## Context

See proposal.md for the motivation. nodeset2owl names the attribute of every child after its browse name: the namespace of the browse name (normalized, e.g. a missing trailing `/` is added) plus `has<name>`. A type's member gets the same kind of name, so a child and the member it instantiates have the same attribute name exactly when their QualifiedNames agree.

owl2instances decides which member a child is in two places:
- when it looks up the child's path and modelling rule in the parent type's shape (or a declaration shape): for objects by the local name of the path, for variables effectively by the attribute name, because the shape's class pattern does not match variables;
- when it looks up the declared variable (template) whose data type and value rank the child's value follows: by the plain name.

## Goals / Non-Goals

**Goals:**
- One identity of a member, the QualifiedName, for objects and variables, type members and declaration members, path and template lookup.
- The same notion of namespace as everywhere else in the OPC UA tools (the normalized namespace URI).

**Non-Goals:**
- Changing placeholder membership (`opcua/instance-declaration-shapes`).
- Diagnosing or repairing models whose browse names use the wrong namespace.

## Decisions

### D1 A fixed-name member is identified by its attribute name
A child matches a fixed-name member of the parent's type or declaration only when the member's attribute name equals the child's own attribute name. Both are derived from the QualifiedName with the same normalization, so this compares namespace and name.

Alternatives considered:
- *Name only, for objects and variables*: consistent, but a child of another namespace is silently taken for the member; two members of the same name in different namespaces (allowed by OPC UA) cannot be told apart.
- *Compare the raw browse-name strings*: namespace URIs are spelled with and without a trailing separator in different nodesets; the raw strings would disagree where the rest of the tools see one namespace.

### D2 Placeholders stay namespace-free
A placeholder's instances are matched by their pattern on the name and by type as today, whatever their namespace.

Alternatives considered:
- *Require the placeholder's namespace*: OPC UA allows instances of a placeholder to have any browse name, and companion specifications rely on it (e.g. devices named in a vendor's namespace below a placeholder of another companion specification); this would reject valid models.

### D3 The template follows the same identity
The declared variable whose data type and value rank apply is the parent type's variable reached through the same attribute name as the child.

Alternatives considered:
- *Keep the name-based lookup*: a child that is no member would get the data type and value rank of another namespace's variable.

## Conflicts

None with approved specs. `opcua/instance-declaration-shapes` decides placeholder membership "by name"; D2 keeps that and states that the namespace is not part of it.

## Risks / Trade-offs

- Models whose instances use browse names of another namespace than their types change: their violations move to the entity that lacks the member, and such children get their own attributes. This is the intended correction; models whose browse names agree are unchanged (verified by the unchanged expected files of the existing cases).
- A child that is no fixed member can be taken as an instance of a generic placeholder of the same type, as OPC UA allows.
