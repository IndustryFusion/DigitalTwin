# Design

## Context

`owl2instances.py` runs in two passes over the instance ontology written by `nodeset2owl.py`:

1. **Type pass.** Starting at the root type (given with `-t`, found through the Machinery folder, or all types of the
   main namespace with `--type-all` / `--maximalshacl`), it writes a node shape per type it reaches and declares the
   attributes of those types in the ontology (`owl:ObjectProperty` with `rdfs:domain`). For every child it continues
   with the child's declared *type*; since #985 (`opcua/instance-declaration-shapes`) it also builds a declaration
   shape from what a declaration adds and scans the types of the added members.
2. **Entity pass.** Starting at the root entities, it walks the real instance nodes along hierarchical,
   `Organizes` and non-hierarchical references and writes one entity per object node, typed with the node's own type
   definition. It reads the shapes of pass 1 to name attributes, recognise placeholders and assign `datasetId`s.

The shapes are written to `shacl.ttl` between the passes. A type that only pass 2 meets gets no shape and no
attribute declarations. After #985 these are:

- the type of an instance that differs from its declaration's type, e.g. a subtype with members of its own (common for
  placeholder instances);
- the type of an object that only an `Organizes` or a non-hierarchical reference reaches: the type pass gives such a
  reference a property with `sh:class` and does not scan the target's type;
- the types of members a declaration adds more than one relationship deep, which #985 reports but does not scan.

Main writes no shape for them, so their mandatory members are never checked (a test model with a member-adding
subtype and an organized object: pyshacl reports the instances conformant on main). The relationships a declaration
adds (the Machinery building blocks' folder to its state machines) are declared nowhere in the ontology, and nothing
reports such a gap.

A prototype of D1 and D2 was run on a large OPC UA demo package whose instances use Machinery state machines that
had no shape. With the prototype every type of its instances has a node shape, every attribute is declared with a
covering domain, only the shapes of the previously missing types were added, `instances.jsonld` is identical, and
pyshacl still reports the instances conformant.

## Goals / Non-Goals

**Goals:**
- Shapes for every type the instances use, built by the existing type scan, so a shape is the same however its type
  is reached.
- Ontology classes and attribute declarations for every type and attribute the instances use.
- No shapes for types the instances do not use.
- A report of what is still not covered.

**Non-Goals:**
- Rules for members an instance declaration adds (#985) or that only an instance adds.
- Changing the instances, entity ids or attribute names.
- Changing the shapes of variables.

## Decisions

### D1: Scan the types of the instance nodes before the shapes are written

Before the shapes are written, walk the instance nodes from the same root entities the entity pass uses, along the
same references (hierarchical children without ignored references, `Organizes`, non-hierarchical references without
ignored ones), also through variables that are children, whose children and non-hierarchical references the entity
pass follows too (a variable that a reference points to is ignored there and here), and collect the type of every
object node. Each collected type that needs a shape and has none yet is
scanned with the existing type scan, which also declares the type as a class with its superclasses and declares its
attributes. The root entities are therefore determined before the shapes are written instead of after;
`--shacl-only` stops after the shapes as before, now with the types of the instance nodes included.

A collected type needs a shape of its own only if it, or a type between it and its nearest supertype with a node
shape, defines a member: a hierarchical child other than a Method (which never gives a rule), an `Organizes` or a
non-hierarchical reference, or an interface. Otherwise the supertype's shape already validates its entities through
`rdfs:subClassOf`, and a second, full shape would only report every violation twice. Types with members of their own
are scanned first: they get a shape in any case, and their scans may give further types one. The types without are
decided after them, supertypes first, so the shape that may cover such a type exists by then. If no type of the chain
defines a member (plain `BaseObjectType` objects), there is no rule to check and the pre-pass writes no shape; the
type pass's own shapes are unchanged by this.

Alternatives:
- *No pre-pass, rely on the type pass since #985.* Covers only the types a declaration adds; the three cases in
  Context stay without shapes, and a test model of them passes validation although mandatory members are missing.
  Rejected.
- *Scan the types of the written entities after the entity pass, then write the shapes.* Fewer types (only nodes that
  become entities), but the entity pass would have run without the shapes of these types: placeholder children of
  such a type would get the default `datasetId` and no path match, and a second entity pass would be needed. Rejected.
- *No shape for any type whose members give no rule*, decided by the scan's result or by repeating its conditions.
  Other members than Methods can give no rule (an object of a type without rules, a placeholder variable without a
  value constraint, a reference to a variable). Removing a scanned shape again means undoing the state of the scans,
  and the entity pass looks members up in the shape of the exact type, so a type without its shape would no longer
  find its supertype's placeholders. Such a type keeps its shape; the cost is that violations of inherited rules may
  be reported by both shapes. Rejected.
- *Shapes for all types of all imported namespaces.* Simple, but bloats `shacl.ttl` and every Flink job built from it
  with types no instance uses. Rejected by the issue.

Consequence: a node that the entity pass later drops (an optional object without content) still contributes its
type. That is bounded by the nodes of the instances, so "nothing for unused types" holds. And once a type has a
shape, the entity pass reads its members from it as for any shaped type: placeholder `datasetId`s follow it, and an
optional child without content appears, with the parent's relationship to it, if the new shape requires a member of
it. A model all of whose instance types already had shapes is unchanged.

### D2: Declare every attribute the entity pass writes

When the entity pass writes an entity, every attribute it carries that has no `rdfs:domain` among the entity's type
and its supertypes, neither in the written ontology nor in the loaded ones, is declared with the entity's type as
domain, in the same form the type pass uses. Attributes already declared for the type or a supertype are left
alone, so the existing declarations do not change. Reference attributes, which any object may carry, are declared
once with the domain `BaseObjectType` instead of once per type that uses them, because several domains are an
intersection in OWL, by the type pass as well: the node reference attribute (`-nr`), which no ontology declares, and the keys of `Organizes`
and non-hierarchical references (reference types, `rdfs:subPropertyOf` another reference). Those keys are prefixed
with the instance ontology's prefixes, so they are expanded with those where the context does not know the prefix. The public laser example shows the gap this closes: it uses the Machinery
building blocks pattern, and the relationships from its folders to the state machines are declared nowhere on main.

Alternative: declare every attribute with the entity's own type unconditionally. Adds redundant domains for every
subtype. Rejected.

### D3: One coverage warning after the outputs are written

After the outputs are written, compare the instances with the shapes and the ontology and write one warning through
the existing warning mechanism (label `UNCOVERED_INSTANCE_TERMS`, suppressible with `-sw` like the others), grouped
per type. The exit status does not change.

- A type is *not covered by a shape* if no node shape targets it and it, or a type between it and its nearest
  supertype with a node shape, defines a member other than a Method, or its definition is unknown; this is the same rule D1 uses to
  decide that a type needs a shape, so the warning names exactly what D1 could not provide.
- An attribute is *undeclared* if no `rdfs:domain` among the entity's type and supertypes covers it.
- An attribute is *constrained* if a node shape targeting the entity's type or a supertype has a property shape for
  it, or if a declaration shape constrains it that a relationship of another entity applies to this entity
  (`sh:node` on `ngsi-ld:hasObject` of that relationship's property shape, as #985 writes it).
- The node reference attribute is exempt: no shape has a rule for it, and it is declared by D2.

Members #985 leaves unvalidated (more than one relationship deep) are named as attributes of the entities that carry
them, next to #985's own `DEEP_DECLARATION_ADDITIONS`, which names the declarations once per owning type.

Alternative: fail the run. Members that only an instance adds are legitimate in OPC UA and have no normative rule;
failing would break existing models. Rejected; a failing mode can follow later if wanted.

## Risks / Trade-offs

- **More shapes, more Flink statements** for models whose instances use such types. Bounded by the types the
  instances use; on the demo package only the shapes of the previously missing types were added.
- **New violations in existing models**: a type that was never validated may now report violations. That is the
  purpose.
- **Multiple `rdfs:domain`s are an intersection in OWL.** The type pass already declares an attribute with one domain
  per type that defines it; D2 adds a domain only where none covers the entity's type, so it follows the existing
  convention without adding to it where not needed. Changing the convention (e.g. a union domain) is out of scope.
- **Coverage warning noise**: models whose instances add members or references of their own, or have declaration
  additions more than one relationship deep, show the warning. It is grouped per type, and suppressible.
