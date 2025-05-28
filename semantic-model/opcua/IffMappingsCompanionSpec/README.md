# IFF Mapping OPC UA Companion Spec

## Introduction
### Overview

The integration of proprietary information models, often referred to as *proprietary models*, poses significant challenges for Machine Builders. These models typically differ from the IFF Semantic Data Model, follow distinct life cycles, and lack standardization, making the onboarding process for IFF both complex and labor-intensive. A considerable amount of manual effort is required to identify and map the relevant parts of these proprietary models to the IFF framework.

To address this issue, IFF-compliant OPC UA Servers introduce an additional "passive" information model alongside their proprietary data model. This passive model serves as a *binding* layer, linking the *proprietary model* to the IFF Semantic Data Model. During the onboarding process, a gateway can connect to the machine, retrieve the specific IFF Bindings, and dynamically map the proprietary model to the IFF framework. The *IFF Mapping Companion Specification* defines the foundational ObjectTypes, ReferenceTypes, and Objects necessary to facilitate this binding, streamlining the integration process and reducing manual effort.

Below is an illustration of the concept:

```
+------------------------------+
|    Proprietary  Model        |
+------------------------------+
        |       ^
        v       |
+-------------------------------+     +----------------------------+
|      Binding Model            | <-- | IFF Mapping Companion Spec |
|-------------------------------|     +----------------------------+
|    Binding Data Service       |
+-------------------------------+ 
            |
            v
+-------------------------------+
|   IFF Semantic Data Model     |
+-------------------------------+
```
This diagram highlights the role of the binding layer in connecting proprietary models to the IFF framework.

### Proprietary Model

The *Proprietary Model* refers to an already existing OPC UA Server implementation of the Machine Builders. It contains a datamodel which fits multiple customers. For instance, the fictive model `http://mycompany.com/UA/ProprietaryModel/` is defined in this [Nodeset2](./example/company_proprietarymodel.nodeset2.xml) file.
This model defines an ObjectType `ProprietaryDataObjectType` which contains three variables:
1) `TemperatureF`, which provides the machine temperature in Fahrenheit
2) `StatusCode`, which provides an Integer value describing the Machine State
3) `StatusString`, which provides an own description of the Status.

The machine defines an Object `ProprietaryDataObject1` which can be browsed and exposes the variables through the OPC UA Server.

### IFF Semantic Data Model

The IFF Semantic Data model is using JSON-LD, OWL and SHACL to define and validate the data with respect to ontologies and knowledge graphs (see [IFF Data Model](../../datamodel/README.md)).
An example of such a machine reprentation can be given as JSON-LD object:

```json

[
    {
        "type": "http://www.industry-fusion.org/schema#Plasmacutter",
        "id": "urn:iff:plasmacutter:1",
        "@context": [
            "https://industryfusion.github.io/contexts/staging/opcua/v0.2/context.jsonld"
        ],
        "http://www.industry-fusion.org/schema#TemperatureC": {
            "type": "Property",
            "value": 30
        },
        "http://www.industry-fusion.org/schema#State": {
            "type": "Property",
            "value": "RUNNING"
        }
    }
]
```

### IFF Mapping Companion Spec

The *IFF Mapping Companion Spec* is providing ontology terms to describe the mapping from the *Proprietary Model* to the *IFF Semantic Data Model*. For instance, it gives the tools at hand which allow to say, take OPC UA Variable `TemperatureF` and apply a Celsius transform to it and forward it as `http://www.industry-fusion.org/schema#TemperatureC` to the *IFF Semantic Data Model*. Transformations can be described with the SPARQL query language which is pretty flexible and can even provide data aggregations. 


### Binding Model and Binding Data Service

The Binding [Data Service](../../dataservice/README.md) is an ontology which allows to combine and transform arbitrary data sources at runtime. One can for instance define that a specific attribute in the *IFF Semantic Data Model* can be created by retrieving several variables (not necessarily from OPC UA) and applying a SPARQL transformation. This allows to transform arbitrary data sources into the semantic data space.
To configure the *Data Service* a configuration is needed which must for instance provide the details on how to retrieve a specific OPC UA Variable from the OPC UA Namespace. This configuration is called *Binding Model*. 

## OPCUA Information Model
### Overview
The following table is summarizing the basic building blocks of the *IFF Mapping Companion Spec*:

OPCUA Type | BrowseName | Description|
-----|------------|------------|
ObjectType| ModelInfoType | Contains the general information like the target entity type in the *IFF Semantic Data Model*. Example: `http://www.industry-fusion.org/schema#Plasmacutter`
ObjectType| AttributeBindingType | The respective attributes of the *IFF Semantic Data Model*, the entity type it is bound to and the tranformation logic. Example: Attribute `http://www.industry-fusion.org/schema#TemperatureC`
ObjectType| AttributeParameterType | The variables of the *Proprietary Model* which must be taken into account for the transfomration. Example: To transform to `http://www.industry-fusion.org/schema#TemperatureC` the `TemperatureF` OPC UA Variable is needed.
ObjectType| IFFMappingsFolderType | An instance of this type is defined in the *IFF Mapping Companion Spec* in order to support a directory based discovery mechanism.
Object | IFFMappingsFolder | Can always be found by `nsu=https://industry-fusion.org/UA/Mapping/;i=42`. It contains the instances of `AttributeBinding` Objects as generic placeholders with the pattern `Attribute_{name}`. In addition it must contain one instance of `ModelInfoType` with name `ModelInfo`
ReferenceType | HasVariable | Is referencing a variable in the *Proprietary Model*, e.g. for `TemperatureF` value it could be `nsu=http://mycompany.com/UA/ProprietaryModel/;i=2004`
DataType| NGSILDAttribute | Enumaration of the supported NGSI-LD types, `Property`, `Relationship`, `JsonProperty`, `ListProperty`|
### OPC UA ObjectTypes

#### ModelInfoType

| References | Node Class | BrowseName | DataType | TypeDefinition | Other |
|------------|------------|------------|----------|----------------|-------|
|HasComponent| Variable | EntityType | String   | BaseDataVariableType | M |

* **EntityType**: Name of the Entity Type in the *IFF Semantic Data Model*, e.g. `http://www.industry-fusion.org/schema#Plasmacutter`


#### AttributeBindingType
| References | Node Class | BrowseName | DataType | TypeDefinition | Other |
|------------|------------|------------|----------|----------------|-------|
| HasComponent | Variable | AttributeName | String | BaseDataVariableType | M |
| HasComponent | Variable | LogicExpression | String | BaseDataVariableType | O |
| HasComponent | Variable | NGSLDAttributeType | NGSILDAttribute | BaseDataVariableType | M|
| HasComponent | Variable | EntitySelector | String | BaseDataVariableType | O|
| HasComponent | Object | AttributeParameter_\<no\> |  | AttributeParameterType | MP |

* **AttributeName**: Name of the Attribute of the *IFF Semantic Data Model*, e.g. `http://www.industry-fusion.org/schema#TemperatureC`
* **LogicExpression**: Expression to transform the variables in SPARQL. This must provide only the `WHERE` clause of the SPARQL query. The follwing variables can be defined in the query:
    * ?value: Property value
    * ?type: Datatype of variable in [XSD ontology](http://www.w3.org/2001/XMLSchema#) with restriction to datatypes defined in [JSON-LD](https://www.w3.org/TR/json-ld11/), e.g. `xsd:Integer`, `xsd:double`, `xsd:boolean`, `xsd:string`, `rdf:JSON`.
    * ?object: Relationship value
    * ?datasetId: NGSI-LD datasetId to reference Attributes in an array
    * ?trustLevel: Value between 0 `no-trust` and 1 `trust` from the connector point of view. e.g. if values are missing or not plausible, the connector can still forward but let the Digital Twin know how much it trusts the value.

    If this expression is omitted and there is only one AttributeParameter associated, the value of the OPC UA Variable is mapped directly to the IFF Attribute respectively.
    Example: Transform a Fahrenheit value to Celsius: `WHERE {BIND (((?var1 - 32)/9 * 5) as ?value)}`
* **NGSILDAttributeType**: Name of the NGSI-LD Attribute, e.g. `Property`
* **EntitySelector**: Reserved for future use when mapping must be applied to subcomponents.
* **AttributeParameter_\<no\>**: Reference to at least one AttributeParameter. The \<no\> parameter must be unique in the whole nodeset-file (not only for a specific AttributeType).


#### AttributeParameterType
| References | Node Class | BrowseName | DataType | TypeDefinition | Other |
|------------|------------|------------|----------|----------------|-------|
| HasComponent | Variable | LogicVariable | String | BaseDataVariableType | M |
| HasVariable | Reference | | | HasVariable | M |

* **LogicVariable**: name of variable which is referenced in the `LogicExpression`of the parent `AttributeBindingType`
* **HasVariable**: Reference to the Variable in the *Proprietary Model*

#### IFFMappingsFolderType
| References | Node Class | BrowseName | DataType | TypeDefinition | Other |
|------------|------------|------------|----------|----------------|-------|
| HasComponent | Object | Attribute_\<name>| | AttributeBindingType | MP|
| HasComponent | Object | ModelInfo | | ModelInfoType | M |

### OPC UA ReferenceTypes
#### HasVariable

This Reference points to an OPC UA Variable in the *Proprietary Model*.

| Attributes | Value |
|------------|-------|
| BrowseName | HasVariable|
| InverseName | - |
| Symmetric | False |
| IsAbstract | False |
| SubType | NonHierarchicalReferences |

### OPC UA Instances

#### IFFMappingsFolder

This Instance is the entry object for discovery of Attributes and ModelInfo. It always has the NodeId `i=42`in the Namespace of the **IFF Mapping Companion Spec*.

| Attributes | Value |
|------------|-------|
| BrowseName| IFFMappingsFolder|
| HasTypeDefinition | IFFMappingFolderType|

### Namespaces
The namespace of this specification is `https://industry-fusion.org/UA/Mapping/`

## Example

In this section, we will walk through an example. The example consists of the following files:

* [iffmapping.nodeset2.xml](./iffmapping.nodeset2.xml) The official Nodeset of this Companion Specification
* [company_proprietarymodel.nodeset2.xml](./example/company_proprietarymodel.nodeset2.xml) A simple *Proprietary Model* from a Machine
* [company_iffbindings.nodeset2.xml](./example/company_iffbindings.nodeset2.xml) The Nodeset which provides the *Binding Model* of the *Proprietary Model*
* [iff_instances.jsonld](./example/iff_instances.jsonld) An example for an *IFF Semantic Data Model*

First, the Nodesets and all their dependen ontologies must be translated to the Web Ontology Language (OWL), a common reprentation of the semantic space. To do this conveniently a Makefile is provided in the [example](./example/) folder.
It is assumed that the python build environment for opcua is setup.
Execute the following command in a BASH SHELL (BASH1)

```shell
# BASH1
cd example
make all
```

As a result, when the make jobs are executed successfully there are newly created files:

* [iffmapping.ttl](./example/iffmapping.ttl) OWL version of `iffmapping.nodeset2.xml`
* [company_proprietarymodel.ttl](./example/company_proprietarymodel.ttl) OWL version of `company_proprietarymodel.nodeset2.xml`
* [company_iffbindings.ttl](./example/company_iffbindings.ttl) OWL version of `company_iffbindings.nodeset2.xml`
* [core.ttl](./example/core.ttl) OWL version of core OPC UA specification
* [instances.jsonld](./example/instances.jsonld) The JSON-LD representation of the *Proprietary Model*
* [shacl.ttl](./example/shacl.ttl) Derived SHACL rules for the *Proprietary Model*
* [entities.ttl](./example/entities.ttl) Derived OWL ontology from the *Proprietary Model*
* [bindings.ttl](./example/bindings.ttl) Derived *Model Bindings* for the *Proprietary Model*
* [bindings_iffmodel.ttl](./example/bindings_iffmodel.ttl) Derived *Model Bindings* for the *IFF Semantic Data Model*

In order to use and test the bindings, two new BASH SHELLs (BASH2, BASH3) has to be opened in the [dataservice](../../dataservice/) folder and make sure that you setup the local pyhton environment.

In BASH2, a simple test server can be started which takes the *Proprietary Model* and serves the respective Nodes:

```shell
# BASH2
cd tests/servers
python3 ./nodeset_server.py --nodeset ../../../opcua/IffMappingsCompanionSpec/example/company_proprietarymodel.nodeset2.xml
```
If successful, one should see:

```shell
[2025-05-27 18:16:09] Server initialized at endpoint: opc.tcp://0.0.0.0:4840/
[2025-05-27 18:16:09] Importing Nodeset file: ../../../opcua/IffMappingsCompanionSpec/example/company_proprietarymodel.nodeset2.xml (strict mode)
[2025-05-27 18:16:09] Successfully imported Nodeset file: ../../../opcua/IffMappingsCompanionSpec/example/company_proprietarymodel.nodeset2.xml
Endpoints other than open requested but private key and certificate are not set.
[2025-05-27 18:16:09] Server running at opc.tcp://0.0.0.0:4840/
[2025-05-27 18:16:09] Registered namespaces: []
[2025-05-27 18:16:09] Loaded Nodesets: ['../../../opcua/IffMappingsCompanionSpec/example/company_proprietarymodel.nodeset2.xml']

```

Now, in BASH3 start the binding server only in `dry-run` model to run it independently of the IFF-Agent. Normally the data would by forwarded to the Agent but for testing purposes this can be switched off:

```shell
# BASH3
python3 startDataservice.py -d ../opcua/IffMappingsCompanionSpec/example/ ../opcua/IffMappingsCompanionSpec/example/bindings.ttl
```

If succesful, one should see:

```shell
Parsing binding ../opcua/IffMappingsCompanionSpec/example/bindings.ttl
Found attributes: http://demo.machine/entity/hasStatusCode, http://mycompany.com/UA/ProprietaryModel/i1101
Found attributes: http://demo.machine/entity/hasStatusString, http://mycompany.com/UA/ProprietaryModel/i1101
Found attributes: http://demo.machine/entity/hasTemperatureF, http://mycompany.com/UA/ProprietaryModel/i1101
Found mappings: http://demo.machine/entity/hasStatusCode, nsu=http://mycompany.com/UA/ProprietaryModel/;i=2005, var1, https://industryfusion.github.io/contexts/ontology/v0/base/OPCUAConnector
Found mappings: http://demo.machine/entity/hasTemperatureF, nsu=http://mycompany.com/UA/ProprietaryModel/;i=2004, var1, https://industryfusion.github.io/contexts/ontology/v0/base/OPCUAConnector
Found mappings: http://demo.machine/entity/hasStatusString, nsu=http://mycompany.com/UA/ProprietaryModel/;i=2006, var1, https://industryfusion.github.io/contexts/ontology/v0/base/OPCUAConnector
Start dataservice for attribute http://demo.machine/entity/hasStatusCode
Requesting map http://demo.machine/bindings/map_1MKHPUHQJBHSVUEO from http://demo.machine/bindings/binding_23KYWJ8KU7VOY2U3
Start dataservice for attribute http://demo.machine/entity/hasStatusString
Requesting map http://demo.machine/bindings/map_RLNO0X2SGPRBQBW7 from http://demo.machine/bindings/binding_03XU6PQ054O61L8T
Start dataservice for attribute http://demo.machine/entity/hasTemperatureF
Requesting map http://demo.machine/bindings/map_YS66W8OO7GVBJZON from http://demo.machine/bindings/binding_EAVDHQTANX35BLWA
2025-05-27 18:28:41,523 - external_services.opcuaConnector - INFO - Connection established to OPC UA server opc.tcp://localhost:4840/
sent [{ "n": "http://demo.machine/entity/hasStatusCode","v": "1", "t": "Property", "i": "http://mycompany.com/UA/ProprietaryModel/i1101"}]
sent [{ "n": "http://demo.machine/entity/hasStatusString","v": "RUNNING", "t": "Property", "i": "http://mycompany.com/UA/ProprietaryModel/i1101"}]
sent [{ "n": "http://demo.machine/entity/hasTemperatureF","v": "100.0", "t": "Property", "i": "http://mycompany.com/UA/ProprietaryModel/i1101"}]

```

The last three lines show that the dataservice reads out the 3 defined variables defined in the *Proprietary Model*, translates them to the semantic model and tries to send it to the IFF Process Data Twin (which is excluded due to the dry-run switch `-d`)
The DataService repeats this but since this is only a static demo server, it always get the same result.

Now, we want to use the same OPC UA Server, but this time, we read out the *IFF Semantic Model Data* as described in the respective *IFF Bindings*. For this, we stop the Server and restart them with the `iff_bindings.ttl`:

```shell
# BASH3
python3 startDataservice.py -d ../opcua/IffMappingsCompanionSpec/example/ ../opcua/IffMappingsCompanionSpec/example/iff_bindings.ttl
```
If successfuly, one should see:

```
Warning: No knowledge file found.
Parsing binding ../opcua/IffMappingsCompanionSpec/example/bindings_iffmodel.ttl
Found attributes: http://www.industry-fusion.org/schema#TemperatureC, urn:iff:plasmacutter:1
Found mappings: http://www.industry-fusion.org/schema#TemperatureC, nsu=http://mycompany.com/UA/ProprietaryModel/;i=2004, var1, https://industryfusion.github.io/contexts/ontology/v0/base/OPCUAConnector
Start dataservice for attribute http://www.industry-fusion.org/schema#TemperatureC
Requesting map https://industry-fusion.org/UA/Bindings/bindings/map_ADGY3FIMYAVUU5KZ from https://industry-fusion.org/UA/Bindings/bindings/binding_Q9A1B63LJ0ZURS0D
Warning: Could not derive any value binding from connector data: {'https://industry-fusion.org/UA/Bindings/bindings/map_ADGY3FIMYAVUU5KZ': {'logicVar': 'var1', 'updated': False, 'connector': 'https://industryfusion.github.io/contexts/ontology/v0/base/OPCUAConnector', 'logicVarType': rdflib.term.URIRef('http://opcfoundation.org/UA/Double'), 'connectorAttribute': 'nsu=http://mycompany.com/UA/ProprietaryModel/;i=2004'}}
2025-05-27 19:14:39,516 - external_services.opcuaConnector - INFO - Connection established to OPC UA server opc.tcp://localhost:4840/
sent [{ "n": "http://www.industry-fusion.org/schema#TemperatureC","v": "37.77777777777777777777777778", "t": "Property", "i": "urn:iff:plasmacutter:1"}]

```

Note that the binding describes how to map the `TemperatureF` field from the *Proprietary Model* to the *IFF Semantic Data Model*. 100° Fahrenheit corresponds to 37.778° Celsius and is mapped to `http://www.industry-fusion.org/schema#TemperatureC` of entity `urn:iff:plasmacutter:1`.