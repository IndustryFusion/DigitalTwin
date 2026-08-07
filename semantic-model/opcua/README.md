# Tools to translate from OPC/UA Information Model to Semantic Web standards

## Setup

To setup the python environment start a python3 virtual environment with `Python 3.11` and install the dependencies with:

`make setup`

### HermiT-based consistency checking (`check_consistency.py`)

`make test` runs `check_consistency.py` with no arguments at the end, which
runs the real HermiT DL reasoner against the already-built Virtual-Types
ontology of every default nodeset (`core.vt.owl.ttl`, `di.vt.owl.ttl`,
`ia.vt.owl.ttl`, `pumps.vt.owl.ttl`, ...) that `translate_default_nodesets.make`
produces earlier in the same `make test` run, checking each one for
contradictory OPC UA type constructions (an override that narrows a
component/DataType/ValueRank/VariableType to something incompatible with its
supertype's declaration). It also backs the `tests/owl2vt/test.bash`
e2e scenarios that assert a *specific* override IS (or is NOT) flagged as
unsatisfiable.

`check_consistency.py` takes the already-built `*.vt.owl.ttl` file(s), not the
semantic-bridge `*.owl.ttl` (nodeset2owl.py output) they were generated from:
it only loads and merges (following each file's own `owl:imports`), it does
not regenerate anything. It rejects a semantic-bridge `*.owl.ttl` (e.g.
`core.owl.ttl`) with a clear error if passed one instead of the pure-OWL
`*.vt.owl.ttl` it was built into (`core.vt.owl.ttl`) -- a semantic-bridge file
has none of the Virtual Type classes/restrictions HermiT actually needs to
reason over, and would otherwise silently report a meaningless "consistent"
verdict rather than actually validating anything.

Due to license conflicts, `owlready2` (needed by `check_consistency.py` to
locate the bundled HermiT.jar) is NOT installed automatically and NOT
listed in requirements.txt/requirements-dev.txt: it is LGPL-3.0-or-later (and
bundles the HermiT.jar reasoner, also LGPL-3.0), incompatible with this
repo's default Apache-2.0 dependency set. `check_consistency.py` detects its
absence at import time and exits with instructions; `make test` will fail at
that step until you install it yourself:

    pip install owlready2==0.51

A `java` runtime on PATH is also required (HermiT itself runs as a `java`
subprocess). To check a single file instead of the whole corpus, pass it
explicitly: `python3 check_consistency.py core.vt.owl.ttl`.

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

    make -f translate_default_nodesets.make

### Get the NodeSet Source URLs Into Your Shell

`translate_default_nodesets.make` knows the raw.githubusercontent.com URL of every
companion spec NodeSet2.xml it can build, plus the base ontology URL. Rather than
reconstructing one of these paths by hand, source them straight into your shell with
the `print-nodesets` target:

    source <(make -f translate_default_nodesets.make -s print-nodesets)

This exports `BASE_ONTOLOGY` and one `<NAME>_NODESET_URL` variable per companion spec
(`CORE_NODESET_URL`, `DI_NODESET_URL`, `PUMPS_NODESET_URL`, ...). For example, to fetch
the raw Pumps NodeSet2.xml:

    curl -s "$PUMPS_NODESET_URL" | less

Run `make -f translate_default_nodesets.make -s print-nodesets` on its own (without
`source <(...)`) to see the full list of variable names it defines.

### Examples

The commands below assume you've sourced `print-nodesets` as shown above.

Create core.owl.ttl:

    python3 nodeset2owl.py ${CORE_NODESET_URL} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o core.owl.ttl


Create devices.owl.ttl:

    python3 nodeset2owl.py  ${DI_NODESET_URL} -i ${BASE_ONTOLOGY} core.owl.ttl -v http://example.com/v0.1/DI/ -p devices -o devices.owl.ttl

Create ia.owl.ttl:

    python3 nodeset2owl.py  ${IA_NODESET_URL} -i ${BASE_ONTOLOGY} core.owl.ttl devices.owl.ttl -v http://example.com/v0.1/IA/ -p ia -o ia.owl.ttl

Create machinery.owl.ttl:

    python3 nodeset2owl.py ${MACHINERY_NODESET_URL} -i ${BASE_ONTOLOGY} core.owl.ttl devices.owl.ttl -v http://example.com/v0.1/Machinery/ -p machinery -o machinery.owl.ttl


Create pumps.owl.ttl:

    python3 nodeset2owl.py  ${PUMPS_NODESET_URL} -i ${BASE_ONTOLOGY} core.owl.ttl devices.owl.ttl machinery.owl.ttl -v http://example.com/v0.1/Pumps/ -p pumps -o pumps.owl.ttl

create pumpexample.owl.ttl:

    python3 nodeset2owl.py  ${PUMPEXAMPLE_NODESET_URL} -i ${BASE_ONTOLOGY} core.owl.ttl devices.owl.ttl machinery.owl.ttl pumps.owl.ttl -n http://yourorganisation.org/InstanceExample/ -v http://example.com/v0.1/pumpexample/ -p pumpexample -o pumpexample.owl.ttl



## owl2instances.py

Create SHACL, entities.ttl, json-ld and bindings.ttl from an OPCUA instance model.

```console
usage: owl2instances.py [-h] -t TYPE [-j JSONLD] [-e ENTITIES] [-s SHACL] [-k KNOWLEDGE] [-b BINDINGS] [-c CONTEXT] [-d] [-m] -n NAMESPACE [-i ID] [-xe ENTITY_NAMESPACE] [-xc CONTEXT_URL] [-xp ENTITY_PREFIX] instance

parse nodeset instance and create ngsi-ld model

positional arguments:
  instance              Path to the instance nodeset2 file.

optional arguments:
  -h, --help            show this help message and exit
  -t TYPE, --type TYPE  Type of root object, e.g. http://opcfoundation.org/UA/Pumps/
  -j JSONLD, --jsonld JSONLD
                        Filename of jsonld output file
  -e ENTITIES, --entities ENTITIES
                        Filename of entities output file
  -s SHACL, --shacl SHACL
                        Filename of SHACL output file
  -k KNOWLEDGE, --knowledge KNOWLEDGE
                        Filename of SHACL output file
  -b BINDINGS, --bindings BINDINGS
                        Filename of bindings output file
  -c CONTEXT, --context CONTEXT
                        Filename of JSONLD context output file
  -d, --debug           Add additional debug info to structure (e.g. for better SHACL debug)
  -m, --minimalshacl    Remove all not monitored/updated shacl nodes
  -n NAMESPACE, --namespace NAMESPACE
                        Namespace prefix for entities, SHACL and JSON-LD
  -i ID, --id ID        ID prefix of object. The ID for every object is generated by "urn:<prefix>:nodeId"
  -xe ENTITY_NAMESPACE, --entity-namespace ENTITY_NAMESPACE
                        Overwrite Namespace for entities (which is otherwise derived from <namespace>/entity)
  -xc CONTEXT_URL, --context-url CONTEXT_URL
                        Context URL
  -xp ENTITY_PREFIX, --entity-prefix ENTITY_PREFIX
                        prefix in context for entities
```

Extract ngsi-ld prototype:

    python3 ./owl2instances.py -t http://opcfoundation.org/UA/Pumps/PumpType -n http://yourorganisation.org/InstanceExample/ pumpexample.owl.ttl


Check the SHACL compliance:

    pyshacl -df json-ld entities.jsonld -s shacl.ttl -e knowledge.ttl


## nodeset-dump.py
Dump OPC UA server nodeset to XML-File

    usage: nodeset-dump.py [-h] [--server-url SERVER_URL] [--start-node START_NODE] [--output-file OUTPUT_FILE] [--namespaces [NAMESPACES ...]] [--excluded [EXCLUDED ...]] [-d] [-v] [-s] [-b]

    Dump OPC UA server nodeset to XML.

    options:
    -h, --help            show this help message and exit
    --server-url SERVER_URL
                            OPC UA server URL (default is opc.tcp://localhost:4840/freeopcua/server/)
    --start-node START_NODE
                            Node ID to start browsing from (default is the Root node, i=84)
    --output-file OUTPUT_FILE
                            Output XML file name (default is nodeset2.xml)
    --namespaces [NAMESPACES ...]
                            List of Namespaces to collect nodes from.
    --excluded [EXCLUDED ...]
                            List of Nodes to exclude from export.
    -d, --debug           Set debug flag.
    -v, --values          Export values.
    -s, --single          Export single node.
    -b, --backward        Consider forward and backward references.

### Example

    python3 ./nodeset-dump.py --namespaces http://examples.com/url1

## validate.py

Validate shacl.ttl, entities.ttl, instances.jsonld combination or single ontology.


```console
usage: validate.py [-h] [-s SHACL] [-e EXTRA] [-df DATA_FORMAT] [-d] [-m MODE] [-st] [-x] [-ni] [-so] [-ns] data

SHACL Validation with Shape and Focus Context

positional arguments:
  data                  Path to RDF data file to validate

options:
  -h, --help            show this help message and exit
  -s SHACL, --shacl SHACL
                        Path to SHACL shapes file
  -e EXTRA, --extra EXTRA
                        Path to extra ontology file
  -df DATA_FORMAT, --data-format DATA_FORMAT
                        Data file format (e.g., turtle, json-ld, xml). If not provided infered from data-file name (.jsonld, .ttl).
  -d, --debug           Debug output
  -m MODE, --mode MODE  Modes: "instance" to validate instance, "ontology" to validate ontology files.
  -st, --strict         Use strict, non accelerated SPARQL query.
  -x, --extended        Use eXtended output with detailed context.
  -ni, --no-imports     No imports of dependent ontologies.
  -so, --sparql-only    Only apply sparql-rules
  -ns, --no_sparql      Only apply sparql-rules

```

This tool is operating in two modes:

1) **instance** (default) takes shacl.ttl, instances.ttl and entities.ttl and executes a shacl evaluation equivalent to
`pyshacl -s shacl.ttl -e entities.ttl -df json-ld instances.jsonld`

2) **ontology** takes an ontology file and shacl.ttl and checks it against shacl constraints.


The tool will provide more context information when used with `-x` switch.
### Example

Validate `instances.jsonld` against entities.ttl` and `shacl.ttl` with extended output:

        python3 validate.py -x instances.jsonld

