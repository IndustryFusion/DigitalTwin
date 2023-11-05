# Digital Twin Datamodel

The following motivates, descibes and defines version 0.1 of the Datamodel. It is in alpha stage and subject to changes.

## JSON-LD (Linked Data)

JSON-LD, which stands for "JavaScript Object Notation for Linked Data," is a powerful data serialization format that extends the capabilities of traditional JSON. Its strength lies in its ability to represent structured data in a way that is both human-readable and machine-understandable. JSON-LD is particularly well-suited for the web and semantic data integration for several key reasons:

 * **Semantic Structure:** JSON-LD allows you to add context to your data, defining the meaning of each piece of information. This semantic structure enables machines to understand the data and its relationships, fostering interoperability and knowledge sharing.

 * **Linked Data:** JSON-LD is designed to facilitate the linking of data across the web. It enables you to reference and interconnect data from various sources and domains, forming a comprehensive and coherent information ecosystem.

 * **SEO and Searchability:** Search engines like Google understand and favor JSON-LD for structuring data. Implementing JSON-LD can improve your website's visibility in search results by providing search engines with valuable information about your content.

 * **Interoperability:** JSON-LD supports the integration of data from diverse sources, making it an ideal choice for data exchange, data sharing, and data synchronization between applications, platforms, and services.

 * **Easy to Read:** JSON-LD retains the simplicity and human-readability of traditional JSON, making it accessible for both developers and non-technical users. Its natural syntax encourages widespread adoption.

 * **Standards-Based:** JSON-LD is based on W3C standards and recommendations, ensuring a well-defined and widely accepted approach to structuring and sharing linked data on the web.

In summary, JSON-LD is a versatile and powerful tool for structuring data with semantic meaning, linking data across the web, improving search engine visibility, fostering interoperability, and promoting data exchange. It plays a crucial role in the modern web ecosystem and is a valuable asset for businesses and organizations looking to harness the full potential of their data.

## JSON-LD Forms

Since JSON-LD represents graph data, it can become very explicit and details. However, In many cases aspects of a graph can also be simplified and described implicitly.

The following shows a so called *compacted* JSON-LD expression. It contains a *context* and a minimized key *name*:

```
{
  "@context": {
    "name": "http://schema.org/name"
  },
  "@id": "https://iri/max.mustermann",
  "name": "Max Mustermann"
}
```

This is an implicit representation of a *expanded* form
```
[{
  "@id": "https://iri/max.mustermann",
  "http://schema.org/name": [{"@value": "Max Mustermann"}]
}]
```

Note that in the Expanded form, the *context* is missing, but everything is now provided with *namespaces* and *@value* which indicates that "Max Mustermann" is a *literal*, i.e. string, number or boolean.
The expanded form can easiliy be transformed into a *Semantic Web* graph representation:

```meermaid
A(https://iri/max.mustermann) -- http://schema.org/name --> B("Max Mustermann")
```

which can also be serialized as turtle graph:

```
@prefix schema: <http://schema.org/> .
<http://iri/max.mustermann/> schema:name "Max Mustermann" .
```

## NGSI-LD (Next Generation Service Interface for Linked Data)

[NGSI-LD](https://www.etsi.org/deliver/etsi_gs/CIM/001_099/009/01.07.01_60/gs_CIM009v010701p.pdf) is an open standard developed by the European Telecommunications Standards Institute (ETSI) as part of the NGSI (Next Generation Service Interface) framework. It extends the capabilities of JSON-LD to enable a powerful, standardized approach to managing and exchanging context information for the Internet of Things (IoT) and smart city applications.

Key features and concepts of NGSI-LD:

* **Linked Data Model:** NGSI-LD is based on the principles of Linked Data, making it a part of the Semantic Web ecosystem. It allows the representation of real-world entities and their attributes as linked data resources.

 * **Entity-Attribute-Value (EAV):** NGSI-LD follows an Entity-Attribute-Value (EAV) model where entities (e.g., IoT devices or physical objects) have attributes (e.g., temperature, location) with associated values (e.g., 25°C, GPS coordinates).

 * **Context Information:** NGSI-LD is designed for sharing context information about entities. This context information can include real-time data, historical data, metadata, and relationships between entities.

* **Interoperability:** One of the main goals of NGSI-LD is to enable interoperability between different IoT platforms, systems, and services. It provides a common data representation format and query language for IoT context information.

* **Standardized APIs:** NGSI-LD specifies a set of standardized APIs for querying, updating, and subscribing to context information. This helps developers create applications that can work with a variety of data sources and platforms.

* **Scalability:** NGSI-LD is designed to handle vast amounts of context information generated by IoT devices, sensors, and other sources, making it suitable for smart city and industrial IoT applications.

* **Semantic Descriptions:** Similar to JSON-LD, NGSI-LD uses semantic descriptions (context) to define the meaning of data attributes. This enables data to be easily understood and used by both humans and machines.

* **Real-Time Updates:** NGSI-LD supports real-time updates and notifications, making it ideal for applications that require immediate access to changing context information.

NGSI-LD is a significant advancement in the field of IoT, as it provides a standardized approach for managing and exchanging context data, enabling more efficient and interoperable IoT solutions. It leverages the power of Linked Data to create a dynamic and interconnected IoT ecosystem. NGSI-LD is already used heavily in smart city applications


## NGSI-LD forms

Since NGSI-LD is extending JSON-LD, it inherits the capability of creating different forms like *expanded* or *compacted*. In addition, it provides a simplification called *concise* form and a more explicit form, called *normalized* form.

NGSI-LD reuqires from every entity to have at least *id* and *type*. All other data is either a *property* or a *relationship*:
```
{
    "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      {
        "@vocab": "https://industry-fusion.org/base/v0.1/"
      }
    ],
    "id": "urn:x:1",
    "type": "cutter",
    "hasFilter": {
      "type": "Relationship",
      "object": "urn:filter:1"
    },
    "machine_state": {
      "type": "Property",
      "value": "Testing"
    }
}

```

The *type* field is here redundant, that is why NGSI-LD defines a *concise* form which is reducing redudancy:

```
{
    "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      {
        "@vocab": "https://industry-fusion.org/base/v0.1/"
      }
    ],
    "id": "urn:x:1",
    "type": "cutter",
    "hasFilter": {
      "object": "urn:filter:1"
    },
    "machine_state": "Testing"
}
```

Since NGSI-LD is JSON-LD compliant, it can be *compacted* and *extended*. Note that both forms, *normalized* and *concise* NGSI-LD, are already *compacted* JSON-LD forms. The expanded *normalized* form of the above example looks like

```
[
  {
    "https://industry-fusion.org/base/v0.1/hasFilter": [
      {
        "https://uri.etsi.org/ngsi-ld/hasObject": [
          {
            "@id": "urn:filter:1"
          }
        ],
        "@type": [
          "https://uri.etsi.org/ngsi-ld/Relationship"
        ]
      }
    ],
    "@id": "urn:x:1",
    "https://industry-fusion.org/base/v0.1/machine_state": [
      {
        "@type": [
          "https://uri.etsi.org/ngsi-ld/Property"
        ],
        "https://uri.etsi.org/ngsi-ld/hasValue": [
          {
            "@value": "Testing"
          }
        ]
      }
    ],
    "@type": [
      "https://industry-fusion.org/base/v0.1/cutter"
    ]
  }
]
```

## Validation with JSON-Schema and SHACL

Validation of JSON objects is typically done with [JSON-Schema](https://json-schema.org/). A plain JSON object structure can therefore be validated. However, as described above, JSON-LD represent a graph and has different forms. For instance, the following two expressions are equivalent in JSON-LD but cannot be schemed with JSON-Schema:

Expression 1

```
[{
    "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      {
        "@vocab": "https://industry-fusion.org/base/v0.1/"
      }
    ],
    "id": "urn:x:1",
    "type": "cutter",
    "hasFilter": {
      "type": "Relationship",
      "object": "urn:filter:1"
    },
    "machine_state": {
      "type": "Property",
      "value": "Testing"
    }
},
{
      "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      {
        "@vocab": "https://industry-fusion.org/base/v0.1/"
      }
    ],
    "id": "urn:y:1",
    "type": "filter",
    "machine_state": {
      "type": "Property",
      "value": "Testing"
    }
}
]
```

Expression 2

```
{
    "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      {
        "@vocab": "https://industry-fusion.org/base/v0.1/"
      }
    ],
    "id": "urn:x:1",
    "type": "cutter",
    "hasFilter": {
      "type": "Relationship",
      "object": {
        "id": "urn:y:1",
        "type": "filter",
        "machine_state": {
          "type": "Property",
          "value": "Testing"
        }   
      }
    },
    "machine_state": {
      "type": "Property",
      "value": "Testing"
    }
}
```

In addition, JSON-schema is not able to properly process *Namespaces*.

Therefore, a proper validation must consider the Graph structure of JSON-LD. A standard, which allows to define Constraints within a Graph is [SHACL](https://www.w3.org/TR/shacl/).


## JSON-LD Validation with JSON-Schema

As shown in the last section, it is impossible to use JSON-Schema to validate JSON-LD objects properly. However, as a compromise, many non-linked data related attributes can be validated if one is applying a propoer normalization. Therefore, we use the JSON-Schema in the following to validate a *concise* NGSI-LD form with a pre-defined *context*.

In the following, we describe the validation schema.
We use the default *contex* https://industryfusion.github.io/contexts/v0.1/context.jsonld. An example for a *concise* form with this *conext* can be seen in the following. It contains an *ECLASS* type, one *ECLASS* property and attributes (properties and relationships) `machine_state` and `hasFilter` from the default vocabulary. The object has an ID expressed as URN:

```
{
    "@context": "https://industryfusion.github.io/contexts/v0.1/context.jsonld",
    "machine_state": "Testing",
    "hasFilter": {
        "object": "urn:filter:1"
    },
    "eclass:0173-1#02-AAH880#003": "10",
    "id": "urn:x:1",
    "type": "eclass:0173-1#01-AKJ975#017"
}
```

In order to validate it with a JSON-Schema, first the base object must be described:

```
 {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/eclass#0173-1#01-AKJ975#017",
        "title": "Plasmacutter",
        "description": "Plasmacutter template for IFF",
        "type": "object",
        "properties": {
           "type": {
            "const": "<compacted type>"
            },
            "id": {
              "type": "string",
              "pattern": "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
            }
        },
        "required": ["type", "id"],
        "allOf": [<urls describing further properties or relationships>]
    }
```

## Translating JSON-Schema to SHACL

## Tools