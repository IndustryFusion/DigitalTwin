# Tools

## Protégé

[Protégé](https://protege.stanford.edu/) is a free, open-source platform that provides a growing user community with a suite of tools to construct domain models and knowledge-based applications with ontologies [7].
Download and install the version for your platform. Once it is installed, you can use Protégé to browse and analyse the OWL files which have been created in the sections before. Start it and open the `pumpexample.owl.ttl` file (*File=>Open*) of the [pump example](./simple-example.md#advanced-example-build-the-pump-example). You see that all dependent companion specifications are imported, together with the meta ontology `uardf.ttl`, which declares the node classes (`uardf:Object`, `uardf:Variable`, ...) and identification properties (`uardf:nodeId`, `uardf:browseName`, ...) of the OPC UA nodes. In order to have a more compact visualization select *render by prefix* in the *View* menu.
One can then browse the ontology, e.g. the opcua object types. In order to see them, select the *Entities* Tab. Then you can browse through the class hierarchy as shown below:

![Image](./images/class-hierarchy.png)

In this example the `pumps:PumpType` is selected. It is then possible to click through the graph and subcomponents and query fields and structures.

Note that an OPC UA instance is an individual of its node class (e.g. `uardf:Object`) and refers to its TypeDefinition with `uardf:hasTypeDefinition`, it is not an `rdf:type` member of the type class. Therefore Protégé lists the pump instance under `uardf:Object` and shows `pumps:PumpType` as value of `uardf:hasTypeDefinition` (the screenshot below was taken with the earlier `rdf:type` representation). Translate the nodesets with `nodeset2owl.py --enforce-opcua-type-semantic` if the instances shall be members of their type classes.

![Image](./images/pump-instance.png)

There are different query options, like SPARQL, DL-Queries and searches for regular expression.


## Fuseki (SPARQL query)
 TBD

