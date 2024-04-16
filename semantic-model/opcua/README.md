# Tools to translate from OPC/UA Information Model to Semantic Web standards

## nodeset2owl.py

This script translates OPCUA nodeset files to OWL (in ttl format).

```console
usage: nodeset2owl.py [-h] [-i [INPUTS [INPUTS ...]]] [-o OUTPUT] [-n NAMESPACE] [-v VERSIONIRI] [-b BASEONTOLOGY] [-u OPCUANAMESPACE] -p PREFIX [-t TYPESXSD] nodeset2

parse nodeset and create RDF-graph <nodeset2.xml>

positional arguments:
  nodeset2              Path to the nodeset2 file

optional arguments:
  -h, --help            show this help message and exit
  -i [INPUTS [INPUTS ...]], --inputs [INPUTS [INPUTS ...]]
                        <Required> add dependent nodesets as ttl
  -o OUTPUT, --output OUTPUT
                        Resulting file.
  -n NAMESPACE, --namespace NAMESPACE
                        Overwriting namespace of target ontology, e.g. http://opcfoundation.org/UA/Pumps/
  -v VERSIONIRI, --versionIRI VERSIONIRI
                        VersionIRI of ouput ontology, e.g. http://example.com/v0.1/UA/
  -b BASEONTOLOGY, --baseOntology BASEONTOLOGY
                        Ontology containing the base terms, e.g. https://industryfusion.github.io/contexts/ontology/v0/base/
  -u OPCUANAMESPACE, --opcuaNamespace OPCUANAMESPACE
                        OPCUA Core namespace, e.g. http://opcfoundation.org/UA/
  -p PREFIX, --prefix PREFIX
                        Prefix for added ontolgoy, e.g. "pumps"
  -t TYPESXSD, --typesxsd TYPESXSD
                        Schema for value definitions, e.g. Opc.Ua.Types.xsd
```

### Create Default Specs
For local testing

     bash ./translate_default_specs_local.bash

### Examples

Create core.ttl:

    python3 nodeset2owl.py ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o core.ttl


Create devices.ttl:

    python3 nodeset2owl.py  ${DI_NODESET} -i ${BASE_ONTOLOGY} core.ttl -v http://example.com/v0.1/DI/ -p devices -o devices.ttl

Create ia.ttl:

    python3 nodeset2owl.py  ${IA_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl -v http://example.com/v0.1/IA/ -p ia -o ia.ttl

Create machinery.ttl:

    python3 nodeset2owl.py ${MACHINERY_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl -v http://example.com/v0.1/Machinery/ -p machinery -o machinery.ttl


Create pumps.ttl:

    python3 nodeset2owl.py  ${PUMPS_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl machinery.ttl -v http://example.com/v0.1/Pumps/ -p pumps -o pumps.ttl

create pumpexample.ttl:

    python3 nodeset2owl.py  ${PUMP_EXAMPLE_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl machinery.ttl pumps.ttl -n http://yourorganisation.org/InstanceExample/ -v http://example.com/v0.1/pumpexample/ -p pumpexample -o pumpexample.ttl



## extractType.py

Coming soon
    