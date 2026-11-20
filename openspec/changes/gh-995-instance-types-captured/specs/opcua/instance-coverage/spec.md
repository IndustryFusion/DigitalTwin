# Delta for OPC UA Instance Coverage

## Purpose

Defines what the shapes and the ontology written by `owl2instances.py` must cover of the instances written in the
same run: every type and every attribute the instances use, no more than that, and a report of anything that is
still not covered.

## ADDED Requirements

### Requirement: Every type of the instances has its shape
For every object type of which the instances contain an entity, the shapes SHALL contain a node shape targeting that type with the rules its definition and supertypes define, however the type is reached: as a declared child's type, as a type a declaration adds, as an instance's own type, or through an `Organizes` or non-hierarchical reference.

#### Scenario: Type added in a folder's declaration
- **WHEN** a type declares a child of type `FolderType` and its declaration adds, with `HasAddIn`, a child of a type that defines a mandatory variable, and the model holds an instance of the type
- **THEN** the shapes contain a node shape targeting the added child's type, requiring that variable

#### Scenario: Instance of a subtype that adds a member
- **WHEN** a type declares a child of type `UnitType`, and the instance's child uses `UnitSubType`, a subtype of `UnitType` that defines a mandatory variable of its own
- **THEN** the shapes contain a node shape targeting `UnitSubType`, requiring that variable

#### Scenario: Type reached only through Organizes
- **WHEN** the instance organizes an object of `ZetaType`, which defines a mandatory variable and which no type references
- **THEN** the shapes contain a node shape targeting `ZetaType`, requiring that variable

#### Scenario: Missing mandatory members found
- **WHEN** the entities of the added child, of the subtype's child and of the organized object each lack their mandatory variable, and the instances are validated with the shapes
- **THEN** validation reports one violation per entity, for that variable

### Requirement: A type without members of its own adds no shape
A type of the instances whose members all come from a supertype with a node shape SHALL be covered by that shape and SHALL NOT get a node shape of its own, and a type that with its supertypes defines no member SHALL NOT get a node shape for being used by the instances.

#### Scenario: Subtype without own members
- **WHEN** a child is declared with a type that has a node shape, and the instance uses a subtype of it that defines no member
- **THEN** the shapes contain no node shape targeting the subtype, and the supertype's shape validates the entity

#### Scenario: Type without rules
- **WHEN** the instance organizes an object of `BaseObjectType`, which defines no member, and no type declares a child of `BaseObjectType`
- **THEN** the shapes contain no node shape targeting `BaseObjectType`

### Requirement: The shape of a type does not depend on the path to it
The node shape of a type SHALL be the same whether the type is the root type of the run, the type definition of a child, or only reached through an instance declaration or an instance node.

#### Scenario: Same shape on both paths
- **WHEN** the shapes are written once with the added child's type as root type, and once from a model in which it only occurs in a folder's declaration
- **THEN** the node shapes targeting that type in both outputs are isomorphic

### Requirement: Every type of the instances is a class with its superclasses
For every object type of which the instances contain an entity, the written ontology or an ontology it imports SHALL declare the type as an `owl:Class` with its supertype as `rdfs:subClassOf`.

#### Scenario: Types reached only through instance nodes
- **WHEN** the instance uses `UnitSubType` for a child declared as `UnitType`, and organizes an object of `ZetaType`
- **THEN** the ontology declares `UnitSubType` as a class with `rdfs:subClassOf` `UnitType`, and `ZetaType` as a class with `rdfs:subClassOf` `BaseObjectType`

### Requirement: Every attribute of the instances is declared
For every attribute that an entity of the instances carries, the written ontology or an ontology it imports SHALL declare the attribute with a domain that the entity's type or one of its supertypes satisfies, including attributes that an instance declaration or the instance itself adds. An attribute already declared so SHALL NOT be declared again. The node reference attribute, which every entity carries when node references are enabled, SHALL be declared once with the domain `BaseObjectType`.

#### Scenario: Attribute of a type reached only through instance nodes
- **WHEN** the entity of the added child, of the subtype's child or of the organized object carries an attribute defined by its type
- **THEN** the ontology declares that attribute with that type, or a supertype defining it, as domain

#### Scenario: Attribute added by a declaration
- **WHEN** the folder's entity carries the relationship to the added child, which `FolderType` does not define
- **THEN** the ontology declares that relationship with `FolderType` or a supertype as domain

#### Scenario: Attribute declared in an imported ontology
- **WHEN** an entity carries an attribute that a loaded ontology already declares with a domain the entity's type or a supertype satisfies
- **THEN** the written ontology adds no declaration for it

#### Scenario: Node reference
- **WHEN** node references are enabled, so that every entity carries the node reference attribute
- **THEN** the ontology declares the node reference with the domain `BaseObjectType` and no other domain

### Requirement: Nothing is added for unused types
The shapes SHALL NOT contain a node shape for a type of an imported ontology that neither the walk from the root type nor any node of the instances reaches.

#### Scenario: Unused companion specification types
- **WHEN** a model imports the Machinery ontology and its instances use none of the Machinery state machine types
- **THEN** the shapes contain no node shape targeting a Machinery state machine type

### Requirement: The instances are unchanged
The instances SHALL be the same as without this capability: the same entities with the same ids, types and attributes.

#### Scenario: Example packages
- **WHEN** the pump, laser and simple examples are generated, compared with the same examples generated by the generator without this capability
- **THEN** their instances are identical, and their shapes are isomorphic, because every type their instances use already has a node shape or is covered by a supertype's

### Requirement: Uncovered types of the instances are reported
After writing its outputs, the generator SHALL report every type of the instances that is not covered by a node shape: no node shape targets it, and it, or a type between it and its nearest supertype with a node shape, defines a member, or its definition is not in the loaded ontologies.

#### Scenario: Type without a definition
- **WHEN** an instance node has a type whose definition is not in the loaded ontologies
- **THEN** the warning names that type as having no shape

#### Scenario: Subtype with members of its own without a shape
- **WHEN** the shapes contain a node shape for `UnitType` but none for `UnitSubType`, which defines a member of its own, and the instances contain a `UnitSubType` entity
- **THEN** the warning names `UnitSubType` as having no shape

### Requirement: Uncovered attributes of the instances are reported
After writing its outputs, the generator SHALL report every attribute of the instances without a declaration whose domain the entity's type or a supertype satisfies, and every attribute that neither a node shape targeting the entity's type or a supertype, nor a declaration shape applied to the entity through a relationship (`opcua/instance-declaration-shapes`), constrains. The base ontology's node reference attribute SHALL NOT be reported.

#### Scenario: Member added only by the instance
- **WHEN** an instance adds a variable that neither its type nor its declaration defines
- **THEN** the ontology declares the attribute, and the warning names it as not constrained by any shape

#### Scenario: Member added by a declaration
- **WHEN** a declaration adds a member beyond its child's type, one relationship below the owning type, and the instance carries it
- **THEN** the warning does not name that member, because the declaration shape applied through the relationship constrains it

#### Scenario: Member added more than one relationship deep
- **WHEN** a declaration adds a member more than one relationship below the owning type, which the declaration shapes do not validate
- **THEN** the warning names that member as not constrained

### Requirement: The coverage report is one warning
The uncovered types and attributes SHALL be reported as one warning with the label `UNCOVERED_INSTANCE_TERMS`, grouped per type, suppressible with `-sw UNCOVERED_INSTANCE_TERMS`; the exit status SHALL be unchanged by it. Members that `opcua/instance-declaration-shapes` reports as not validated SHALL be named in it as well.

#### Scenario: Nothing uncovered
- **WHEN** every type and attribute of the instances is covered
- **THEN** no such warning is written

#### Scenario: Gaps reported once
- **WHEN** the instances have uncovered types and attributes
- **THEN** one `UNCOVERED_INSTANCE_TERMS` warning names them grouped per type, and the generator exits with the same status as without them
