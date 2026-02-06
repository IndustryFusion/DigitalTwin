# Overview

This document describes how to map OPCUA data into Semantic Web [6] data, more specifically we describe how to transform OPCUA data into the following 3 standards:
1. The **constraints and rules** are expressed in the SHApes Constraint Language (SHACL) [1] (`shacl.ttl`)
2. The **ontology** data about types, enumerations and other explicit knowledge e is expressed in the Web Ontology Language (OWL)[2] (called  `entities.ttl`, or sometimes `knowledge.ttl` or `ontolgoy.ttl`)
3. Representation of the OPCUA **instance** as JSON-LD [3] or more specifically the NGSI-LD[4] standard (called `instances.jsonld`)

The files are all represented in Resource Description Format[6] serialized in the Turtle[5] or JSON-LD.


# Setup for Linux

Windows is no longer supported. Tutorial is tested only for Linux, Ubuntu 22.04.

## For Linux
Target System Linux, tested on `Ubuntu 22.04`.

In additiona the following must be installed:

- Python3 >= 3.10
- VSCode
- Make, bash, git (for Linux)

Get the code from the IndustryFusion Foundation repo:

```
git clone https://github.com/IndustryFusion/DigitalTwin.git
```

Find the right directory:

```
cd DigitalTwin/semantic-model/opcua/
```

and install the dependencies:

```
make setup
```




