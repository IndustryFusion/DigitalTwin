# Mapping Concept

## Conversion to NGSI-LD(JSON-LD)

In the following the mapping of OPCUA information model to NGSI-LD is described.
This is the information model we use as refernce
```
ParentObject (NodeId: ns=2;i=99)
 ├── ArrayObject_01 (NodeId: ns=2;i=100)
 ├── ArrayObject_02 (NodeId: ns=2;i=200)
 ├── ChildObjectX (NodeId: ns=2;i=101)
 ├── ChildObjectY (NodeId: ns=2;i=102)
 ├── DataVariableX (NodeId: ns=2;i=201, datatype: string)
 │   └── PropertyX (NodeId: ns=2;i=301, value=0)
 ├── DataVariableY (NodeId: ns=2;i=202, datatype: integer)
 │   └── PropertyY (NodeId: ns=2;i=302, value=true)
 ├── DataVariableZ (NodeId: ns=2;i=202, datatype: boolean)
 ├── PropertyZ (NodeId: ns=2;i=103, value="test")
```

## Entity Ids

Every entity is created from an OPC UA node and its id is derived from the node's
canonical ExpandedNodeId (`uardf:nodeId`, see the README's
[Node Identification](../README.md#node-identification-uardf)):

    urn:uaentity:<base64url(ExpandedNodeId) without padding>

The instances of a machine are dynamic nodes, so their ExpandedNodeId contains the
server URI (from `uardf:serverUri`, `uardf:nodeId` has none), e.g.
`svu=urn:example:opcua-server;nsu=http://example.org/;i=99`. The prefix
`urn:uaentity:` can be changed with `owl2instances.py -i`. The id is related to, but
different from the IRI of the node; with `-nr` every entity gets a `base:hasNodeRef` to it.

For readability the examples below abbreviate the ids as `urn:uaentity:<i=99>`, which
stands for `urn:uaentity:` + base64url(`svu=urn:example:opcua-server;nsu=http://example.org/;i=99`).

## Conversion of OPCUA Objects to NGSI-LD:
The type is assumed to be `ParentObjectType`

```
 {
    "id": "urn:uaentity:<i=99>",
    "type": "ParentObjectType",
    "hasChildObjectX":{
            "type": "Relationship",
            "object": "urn:uaentity:<i=101>"
    },
    "hasChildObjectY":{
            "type": "Relationship",
            "object": "urn:uaentity:<i=102>"
    }
 }
 ```

## Conversion of OPCUA Data Variables to NGSI-LD:


```
 {
    "id": "urn:uaentity:<i=99>",
    "type": "ParentObjectType",
    "hasDataVariableX":{
            "type": "Property",
            "value": "string"
    },
    "hasDataVariableY":{
            "type": "Property",
            "value": 0
    },
    "hasDataVariableZ":{
            "type": "Property",
            "value": false
    },
 }
 ```

## Conversion of OPCUA Properties
Properties of Objects are only differentiable from Datavariables by metadata provided by entities.ttl (see below)

```
 {
    "id": "urn:uaentity:<i=99>",
    "type": "ParentObjectType",
    "hasDataVariableX":{
            "type": "Property",
            "value": "string",
            "hasPropertyX": "test"
    },
    "hasDataVariableY":{
            "type": "Property",
            "value": 0,
            "hasPropertyY": 0
    },
    "hasDataVariableZ":{
            "type": "Property",
            "value": false
    },
    "hasPropertyZ": false
 }
 ```
## Conversion of OPCUA Object-arrays

Objects which are part of an array are typcially defined with a template <> definition. E.g. object_<no> means that there could be object_1, object_2, ... browsepath.
The problem of this is that the name convention is not exactly specified, so object_#1, object#2, ... or object_01, object_02, ... is also possible. Moreover, this makes it difficult to write logic which addresses all element in an array because one needs to guess the names with a pattern. Therefore, we treat this case different. A NGSI-LD instance of such an object would look as follows:

```
 {

    "id": "urn:uaentity:<i=99>",
    "type": "ParentObjectType",
    "ArrayObject": [
        {
            "type": "Relationship",
            "object": "urn:uaentity:<i=100>",
            "datasetId": "http://example.org/hasArrayObject_01"
        },
        {
            "type": "Relationship",
            "object": "urn:uaentity:<i=200>",
            "datasetId": "http://example.org/hasArrayObject_02"
        }
    ]
 }
 ```

 Node that you can now access all objects at once, e.g. with a SHACL expression but still you can select one specific object by using the respective `datasetId` reference or the `id` of the specific object. The `datasetId` is the semantic bridge property of the element (derived from its BrowseName, e.g. `http://example.org/hasArrayObject_01` for `ArrayObject_01` in namespace `http://example.org/`).

## Input to the semantic conversion
Besides the companion specifications, there are two files needed:
1. A `nodeset2` file which contains the Type Definitions of the machine.
2. A `nodeset2` file which contains a snapshot of the Instance

As a result, there are the following files created:

## `instances.jsonld`

Contains all entities with respective Properties and Relationships of the machine instances.

## `shacl.ttl`

Contains all SHACL rules which could be derived automatically from the Type definition `nodeset2`.

## `entities.ttl`

Contains all generic semantic information related to the entities which could be derived for Relationships and Properties. It also include the type hierarchy.


```
uaentity:ParentObjectSubType a owl:Class ;
    rdfs:subClassOf uaentity:ParentObjectType .

uaentity:hasDataVariableX a owl:NamedIndividual,
        owl:ObjectProperty ;
    rdfs:domain uaentity:ParentObjectType .

uaentity:hasChildObjectX a owl:NamedIndividual,
        owl:ObjectProperty ;
    rdfs:domain uaentity:ParentObjectType .
```

The kind of a Relationship and the placeholder information are part of the property
shapes in `shacl.ttl`:

```
shacl:ParentObjectTypeShape a sh:NodeShape ;
    sh:property [ a base:SubComponentRelationship ;
            sh:path uaentity:hasArrayObject ;
            sh:property [ sh:class uaentity:ArrayObjectType ;
                    sh:nodeKind sh:IRI ;
                    sh:path ngsi-ld:hasObject ] ;
            base:hasReferenceType opcua:HasComponent ;
            base:isPlaceHolder true ] ;
    sh:targetClass uaentity:ParentObjectType .
```

## `knowledge.ttl`

Contains all information about additional classes e.g. describing enums

# Validation

## Offline Validation

For offline validation one can apply 

    pyshacl -s shacl.ttl -e entities.ttl  -df json-ld instances.jsonld

To demonstrate the need of the entities.ttl, try validation without entities.ttl. Dependent on the models you will see additional errors due to the fact that SHACL validator cannot use the knowledge that one type is a subtype of something else.