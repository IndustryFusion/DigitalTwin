# Delta for OPC UA Instance Coverage

## Purpose

Defines what the shapes and the ontology written by `owl2instances.py` must cover of the instances written in the
same run: every type and every attribute the instances use, no more than that, and a report of anything that is
still not covered.

## ADDED Requirements

### Requirement: Every type of the instances has its shape
For every object type of which the instances contain an entity, the shapes SHALL contain a node shape targeting that type with the rules its definition and supertypes define, wherever the type occurs. A type adding no member to a supertype with a node shape SHALL be covered by that shape instead; a type that with its supertypes defines no member SHALL get none.

#### Scenario: Type added in a folder's declaration
- **WHEN** a type declares a child of type `FolderType` and its declaration adds, with `HasAddIn`, a child of a type that defines a mandatory variable, and the model holds an instance of the type
- **THEN** the shapes contain a node shape targeting the added child's type, requiring that variable

#### Scenario: Subtype without own members
- **WHEN** a child is declared with a type that has a node shape, and the instance uses a subtype of it that defines no member
- **THEN** the shapes contain no node shape targeting the subtype, and the supertype's shape validates the entity

#### Scenario: Type without rules
- **WHEN** an instance holds objects of `BaseObjectType`, which defines no member
- **THEN** the shapes contain no node shape targeting `BaseObjectType`, and the warning does not name it

#### Scenario: Missing mandatory member found
- **WHEN** the instance of that added child lacks the mandatory variable, and the instances are validated with the shapes
- **THEN** validation reports one violation, on the entity of the added child, for that variable

### Requirement: The shape of a type does not depend on the path to it
The node shape of a type SHALL be the same whether the type is the root type of the run, the type definition of a child, or only reached through an instance declaration.

#### Scenario: Same shape on both paths
- **WHEN** the shapes are written once with the added child's type as root type, and once from a model in which it only occurs in a folder's declaration
- **THEN** the node shapes targeting that type in both outputs are isomorphic

### Requirement: Every attribute of the instances is declared
For every attribute that an entity of the instances carries, the written ontology or an ontology it imports SHALL declare the attribute with a domain that the entity's type or one of its supertypes satisfies, including attributes that an instance declaration or the instance itself adds. An attribute already declared so SHALL NOT be declared again.

#### Scenario: Attribute of a type reached only through a declaration
- **WHEN** the added child's entity carries an attribute defined by its type
- **THEN** the ontology declares that attribute with the added child's type, or a supertype defining it, as domain

#### Scenario: Attribute added by a declaration
- **WHEN** the folder's entity carries the relationship to the added child, which `FolderType` does not define
- **THEN** the ontology declares that relationship with `FolderType` or a supertype as domain

#### Scenario: Attribute declared in an imported ontology
- **WHEN** every entity carries the node reference attribute, which the base ontology declares with domain `BaseObjectType`
- **THEN** the written ontology adds no declaration for it

### Requirement: Nothing is added for unused types
The shapes SHALL NOT contain a node shape for a type of an imported ontology that neither the walk from the root type nor any node of the instances reaches. The instances SHALL be the same as without this capability.

#### Scenario: Unused companion specification types
- **WHEN** a model imports the Machinery ontology and its instances use none of the Machinery state machine types
- **THEN** the shapes contain no node shape targeting a Machinery state machine type

#### Scenario: Already covered model
- **WHEN** the pump, laser and simple examples are generated
- **THEN** their instances and their shapes are unchanged, because every type their instances use already has a node shape or is covered by a supertype's

### Requirement: Uncovered parts of the instances are reported
After writing its outputs, the generator SHALL report, as one warning naming them, every type of the instances covered by no node shape, every attribute without a declaration covering the entity's type, and every attribute that neither a shape of the entity's type nor a declaration shape applied to the entity through a relationship (`opcua/instance-declaration-shapes`) constrains. Its exit status SHALL be unchanged by the report.

#### Scenario: Member added by a declaration
- **WHEN** a declaration adds a member beyond its child's type, one relationship below the owning type, and the instance carries it
- **THEN** the warning does not name that member, because the declaration shape applied through the relationship constrains it

#### Scenario: Member added more than one relationship deep
- **WHEN** a declaration adds a member more than one relationship below the owning type, which the declaration shapes do not validate
- **THEN** the warning names that member as not constrained

#### Scenario: Type without a definition
- **WHEN** an instance node has a type whose definition is not in the loaded ontologies
- **THEN** the warning names that type as having no shape

#### Scenario: Member added only by the instance
- **WHEN** an instance adds a variable that neither its type nor its declaration defines
- **THEN** the ontology declares the attribute, and the warning names it as not constrained by any shape

#### Scenario: Nothing uncovered
- **WHEN** every type and attribute of the instances is covered
- **THEN** no such warning is written
