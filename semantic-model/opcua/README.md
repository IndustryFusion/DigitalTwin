# Tools to translate from OPC/UA Information Model to Semantic Web standards

This file is the CLI reference. For step-by-step tutorials see [docs/](./docs/README.md),
in particular the three validations:

- [Validation Overview](./docs/validation-overview.md) — which of the three to run when
- [Ontology (Graph) Validation](./docs/ontology-validation.md) — `validate.py -m ontology`
- [Instance Validation](./docs/simple-example.md#validation-of-instances) — `validate.py` (default mode)
- [Virtual Type (Logical) Validation](./docs/virtual-type-validation.md) — `validate.py -m vt` / `check_consistency.py`

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
usage: nodeset2owl.py [-h] [-i [INPUTS ...]] [-o OUTPUT] [-n NAMESPACE] [-v VERSIONIRI] [-b BASEONTOLOGY]
                      [-burl BASEONTOLOGYURL] [--uardfOntology UARDFONTOLOGY] [-u OPCUANAMESPACE] -p PREFIX
                      [-t TYPESXSD] [--import-indirect-dependencies] [--disable-semantic-bridge]
                      [--enforce-opcua-type-semantic] [--defaultLocale DEFAULTLOCALE] [-s SERVERURI] [--dynamic-only]
                      [--strict-classification] [--classification-report CLASSIFICATION_REPORT]
                      [--dynamic-imports [DYNAMIC_IMPORTS ...]]
                      nodeset2

parse nodeset and create RDF-graph <nodeset2.xml>

positional arguments:
  nodeset2              Path to the nodeset2 file

options:
  -h, --help            show this help message and exit
  -i [INPUTS ...], --inputs [INPUTS ...]
                        <Required> add dependent nodesets as ttl
  -o OUTPUT, --output OUTPUT
                        Resulting file.
  -n NAMESPACE, --namespace NAMESPACE
                        Overwriting namespace of target ontology, e.g. http://opcfoundation.org/UA/Pumps/
  -v VERSIONIRI, --versionIRI VERSIONIRI
                        VersionIRI of ouput ontology, e.g. http://example.com/v0.1/UA/
  -b BASEONTOLOGY, --baseOntology BASEONTOLOGY
                        Ontology containing the base terms, e.g.
                        https://industryfusion.github.io/contexts/ontology/v0/base/
  -burl BASEONTOLOGYURL, --baseOntologyURL BASEONTOLOGYURL
                        Ontology URL , e.g. https://industryfusion.github.io/contexts/staging/ontology/v0/base.ttl
  --uardfOntology UARDFONTOLOGY
                        Location of the uardf meta ontology (node classes and identification properties,
                        http://opcfoundation.org/rdf/uacore#) which is imported by the output, e.g. a local file or
                        URL.
  -u OPCUANAMESPACE, --opcuaNamespace OPCUANAMESPACE
                        OPCUA Core namespace, e.g. http://opcfoundation.org/UA/
  -p PREFIX, --prefix PREFIX
                        Prefix for added ontolgoy, e.g. "pumps"
  -t TYPESXSD, --typesxsd TYPESXSD
                        Schema for value definitions, e.g. Opc.Ua.Types.xsd
  --import-indirect-dependencies
                        Import not only direct dependencies but also indirect dependencies.
  --disable-semantic-bridge
                        Disable adding semantic bridge between OPC UA and Containment/Domain ontology terms.
  --enforce-opcua-type-semantic
                        Enforce OPC UA type semantics, instead of uardf:hasTypeDefinition. This can create instance
                        validation problems.
  --defaultLocale DEFAULTLOCALE
                        Locale of LocalizedText (DisplayName, Description, values) without Locale.
  -s SERVERURI, --serverUri SERVERURI
                        Server URI (svu) used to identify dynamic nodes, e.g. urn:example:server. Without it, dynamic
                        nodes are not exported.
  --dynamic-only        Export only the server specific (dynamic) part, including references between static and
                        dynamic nodes. Requires --serverUri. Together with the export without --serverUri (static
                        part) it composes the full export. The export gets its own ontology IRI per server: <ontology>
                        + base64url(svu=<serverUri>).
  --strict-classification
                        Classify static/dynamic nodes strictly by the standard rules R3 (NamespaceMetadata rule) and
                        R5 (default fallback: types and instance declarations static, instances dynamic). Disables the
                        heuristic override R1 (instance-with-Variables) and the heuristic fallback R4 (definition
                        fallback), see README.
  --classification-report CLASSIFICATION_REPORT
                        Write the nodes which the heuristics classify differently than the standard rules (static ->
                        dynamic and dynamic -> static) to this TSV file.
  --dynamic-imports [DYNAMIC_IMPORTS ...]
                        With --dynamic-only: additional owl:imports of the dynamic export, which are not read as
                        inputs, e.g. the static export of the same nodeset and the dynamic exports of its
                        dependencies.
```

### Node Identification (uardf)

`nodeset2owl.py` identifies every node with the terms of the upcoming OPC UA RDF
standard, namespace `uardf:` = `http://opcfoundation.org/rdf/uacore#`. The terms are
declared in the meta ontology [uardf.ttl](./uardf.ttl), which every output imports
(`--uardfOntology` changes its location).

- The IRI of a node is `<namespace URI>` + base64url (without padding) of its canonical
  ExpandedNodeId, e.g. core `i=2042` becomes `http://opcfoundation.org/UA/aT0yMDQy`; for
  dynamic nodes the ExpandedNodeId contains the server URI
  (`svu=<server URI>;nsu=<namespace URI>;i=5001`, see below).
- `rdf:type` is the node class: `uardf:Object`, `uardf:Variable`, `uardf:Method`,
  `uardf:View`, `uardf:ObjectType`, `uardf:VariableType`, `uardf:DataType` or
  `uardf:ReferenceType`.
- `uardf:nodeId` is the canonical ExpandedNodeId without server URI: `i=2042` for core
  nodes, `nsu=<namespace URI>;i=1001` for companion specifications and dynamic nodes. The
  server URI of a dynamic node is in `uardf:serverUri` (and in its IRI).
- `uardf:namespaceUri`, `uardf:browseName` (`nsu=<namespace URI>;<name>`), `uardf:name`,
  `uardf:symbolicName`, `uardf:displayName` and `uardf:description` (both `rdf:langString`,
  `--defaultLocale` for texts without locale) describe the node.
- `uardf:hasTypeDefinition` points to the TypeDefinition of Objects and Variables.
  It is deliberately not `rdf:type`; `--enforce-opcua-type-semantic` writes `rdf:type`
  instead.
- Type nodes carry `uardf:definesType` (the OWL class of the type) and `uardf:isAbstract`;
  `uardf:parent` keeps the ParentNodeId structure.
- The semantic bridge properties (e.g. `pumps:hasMotor`) are `owl:ObjectProperty` and
  `rdfs:subPropertyOf uardf:semanticBridgeReferenceType`.

### Static and Dynamic Nodes

A node is *static* when it is the same in every server (types, instance declarations,
well-known nodes) and *dynamic* when it is server specific (e.g. the instances of a
machine). nodeset2owl.py decides it with the following named rules; the first matching rule
decides, in the order R1, R3, R4, R5. R1 is an *override*, which overrules the
NamespaceMetadata (R3); R4 and R5 are *fallbacks*, which only apply where the NamespaceMetadata
does not decide. R3 and R5 are the rules of the OPC UA standard (`--strict-classification`
keeps only these), R1 and R4 are heuristics.

Override (heuristic, it overrules R3):

- **R1 instance-with-Variables override.** An instance (an Object or Variable which is
  neither a type nor an instance declaration) that has Variables is dynamic, together with
  its Variables: adding Variables to an instance expresses the intention of server specific
  data, e.g. every NamespaceMetadata object, core's ServerConfiguration or DI's
  `MaxInactiveLockTime` (a Variable of core's ServerCapabilities). R1 looks at the direct
  Variables of the instance in the nodeset only: transitively it would make static entry
  points such as core's `Objects` folder dynamic, and the Variables declared by the
  TypeDefinition are not considered (an instance whose Variables the nodeset does not contain
  keeps the classification of R3). Definition nodes (see R4) are excluded, e.g. every
  ModellingRule has a NamingRule property.
Standard rule:

- **R3 NamespaceMetadata rule.** The `NamespaceMetadata` of the nodeset decides per namespace
  (StaticNodeIdTypes, StaticNumericNodeIdRange, StaticStringNodeIdPattern).

Fallbacks (only where R3 does not decide):

- **R4 definition fallback** (heuristic). Definition nodes are static: Objects and Variables
  which are definitions rather than data – DataType encodings, dictionary entries,
  ModellingRules and the legacy type dictionaries, i.e. instances of DataTypeEncodingType,
  DictionaryEntryType, ModellingRuleType, DataTypeSystemType, DataTypeDictionaryType,
  DataTypeDescriptionType (and their subtypes), together with the Variables of the type
  dictionaries. They are part of the information model, which refers to them by NodeId
  (HasEncoding, HasDictionaryEntry, HasModellingRule, HasDescription), so they must be the
  same in every server.
- **R5 default fallback** (standard). Types and instance declarations are static, instances
  are dynamic. An instance declaration is a node with a ModellingRule or a node whose
  HasChild parent (ParentNodeId, otherwise the inverse HasChild reference) is a type or an
  instance declaration.

R1 and R5 follow HasChild only, including all its subtypes
(HasComponent, HasProperty, HasOrderedComponent, HasAddIn, ...), also those of companion
specifications, resolved via the ReferenceType hierarchy. Organizes (hierarchical, but no
HasChild), like every other reference which is not HasChild, never influences the
classification: organizing a node does not make it part of the organizer, so a static entry
folder can organize dynamic machines and a node organized by a dynamic instance keeps its own
classification.

`--classification-report <file>` writes the nodes which the heuristic rules
classify differently than the standard rules (with the rule) as TSV.

Dynamic nodes are only exported with a server URI. Without `--serverUri`, nodeset2owl.py
warns and leaves them and all references to them out; this is the *global* version of
a companion specification, which can be shared by everyone. With `--serverUri` the
dynamic nodes get `uardf:serverUri` and an `svu=` in the ExpandedNodeId of their IRI
(`uardf:nodeId` stays without server URI).
`--dynamic-only` exports just the server specific part, which together with the static
export composes the full export. It gets its own ontology IRI per server, the ontology IRI
plus the base64url encoding of `svu=<server URI>` (like a node IRI), and `--dynamic-imports`
adds `owl:imports` to it (e.g. the static file and the dynamic files of the dependencies), so
that the static file and the dynamic files of one or more servers can be loaded together.

`translate_default_nodesets.make` builds this dynamic part next to every static
specification. The file name carries the server URI (every character except `A-Za-z0-9._-`
replaced by `_`), so the parts of several servers can be built and composed side by side:

    make -f translate_default_nodesets.make dynamic                                # urn:example:opcua-server
    make -f translate_default_nodesets.make dynamic SERVER_URI=urn:plant:server2   # another server
    make -f translate_default_nodesets.make core.owl.dynamic.urn_example_opcua-server.ttl

`core.owl.ttl` stays the global, shareable version; `core.owl.dynamic.<server>.ttl` holds the
Server object and everything else that is specific to that server, and imports `core.owl.ttl`.
E.g. loading `di.owl.ttl` with the dynamic DI files of two servers shows one (static) DI
NamespaceMetadata object, which is a component of the `Namespaces` objects of both servers.
The instance examples (e.g. `pumpexample.owl.ttl`) are already translated completely with
`--serverUri` and get no separate dynamic file.

To browse or query an example of the complete model, the static part and the dynamic parts of
all servers built so far (always including `$(SERVER_URI)`) are composed into one file per
specification, `<spec>.owl.all.ttl` (ontology IRI `<ontology>all`), with `compose_owl.py`:

    make -f translate_default_nodesets.make composed          # e.g. core.owl.all.ttl, di.owl.all.ttl, ...
    make -f translate_default_nodesets.make di.owl.all.ttl

A composed file imports the composed files of its dependencies instead of their static files,
so `di.owl.all.ttl` loads `core.owl.all.ttl` (and `uardf.ttl` and the base ontology) and nothing
else. Open it in Protégé, or load it into Fuseki with `python3 start_fuseki.py di.owl.all.ttl`,
which follows the same imports. `COMPOSE_SERVERS="<server> ..."` restricts the composition to
the dynamic parts of these servers.

`compose2` shows a knowledge graph of two servers with the same NodeIds: it builds the dynamic
parts of `$(SERVER_URI)` and `$(SERVER_URI2)` (default `urn:example:opcua-server2`) and
composes the static part with exactly these two:

    make -f translate_default_nodesets.make compose2
    make -f translate_default_nodesets.make compose2 SERVER_URI=urn:plant:a SERVER_URI2=urn:plant:b

In `core.owl.all.ttl` both servers then have e.g. their own Server object: two nodes with the
same `uardf:nodeId "i=2253"`, distinguished by their IRI (base64url of `svu=<server>;i=2253`)
and `uardf:serverUri`, while every static node exists once and is shared by both.

Instance nodesets therefore have to be translated with `--serverUri`, otherwise their
instances are missing and `owl2instances.py` reports that it cannot find any instance
of the requested type. The Makefiles pass `--serverUri $(SERVER_URI)` (default
`urn:example:opcua-server`) for the instance examples.

### Create Default Specs
For local testing

    make -f translate_default_nodesets.make

Single specifications (with their dependencies) are built with `nodeset2owl-<name>`
targets, e.g. `make -f translate_default_nodesets.make nodeset2owl-pumps`.

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

    python3 nodeset2owl.py  ${PUMPEXAMPLE_NODESET_URL} -i ${BASE_ONTOLOGY} core.owl.ttl devices.owl.ttl machinery.owl.ttl pumps.owl.ttl -n http://yourorganisation.org/InstanceExample/ -v http://example.com/v0.1/pumpexample/ -p pumpexample --serverUri urn:example:opcua-server -o pumpexample.owl.ttl



## owl2instances.py

Create SHACL, entities.ttl, json-ld and bindings.ttl from an OPCUA instance model.

```console
usage: owl2instances.py [-h] [-t TYPE] [-so] [-ta] [-eid] [-j JSONLD] [-e ENTITIES] [-s SHACL] [-b BINDINGS]
                        [-c CONTEXT] [-d] [-mi] [-ma] -n NAMESPACE [-i ID] [-xe ENTITY_NAMESPACE] [-xc CONTEXT_URL]
                        [-r] [-sw [SUPPRESS_WARNINGS ...]] [-p] [-vrs] [-sb] [-nr]
                        instance

parse nodeset instance and create ngsi-ld model

positional arguments:
  instance              Path to the instance nodeset2 file.

options:
  -h, --help            show this help message and exit
  -t TYPE, --type TYPE  Type of root object to be extracted, e.g. http://opcfoundation.org/UA/Pumps/
  -so, --shacl-only     Only create SHACL shapes without JSON-LD instances.
  -ta, --type-all       Extract all ObjectTypes of the mainontologies namespace. In additiion, extract all well known
                        instances (i.e. referenced by the "objects" folder)
  -eid, --extract-instance-declarations
                        Extract all instance declarations in order to validate them. This option only works with -ta
                        option enabled.
  -j JSONLD, --jsonld JSONLD
                        Filename of jsonld output file
  -e ENTITIES, --entities ENTITIES
                        Filename of entities output file
  -s SHACL, --shacl SHACL
                        Filename of SHACL output file
  -b BINDINGS, --bindings BINDINGS
                        Filename of bindings output file
  -c CONTEXT, --context CONTEXT
                        Filename of JSONLD context output file
  -d, --debug           Add additional debug info to structure (e.g. for better SHACL debug)
  -mi, --minimalshacl   Remove all not monitored/updated shacl nodes
  -ma, --maximalshacl   Add all types from nodes in the namespace.
  -n NAMESPACE, --namespace NAMESPACE
                        Namespace prefix for entities, SHACL and JSON-LD
  -i ID, --id ID        ID prefix of the entities. The ID of every entity is "<prefix><base64url encoded canonical
                        ExpandedNodeId of its node>", default prefix: urn:uaentity:
  -xe ENTITY_NAMESPACE, --entity-namespace ENTITY_NAMESPACE
                        Overwrite Namespace for entities (which is otherwise derived from <namespace>/entity)
  -xc CONTEXT_URL, --context-url CONTEXT_URL
                        Context URL, default:
                        https://industryfusion.github.io/contexts/staging/opcua/v0.2/context.jsonld
  -r, --recursive-import
                        Import dependencies of dependencies
  -sw [SUPPRESS_WARNINGS ...], --suppress-warnings [SUPPRESS_WARNINGS ...]
                        List of Warnings which are to be suppressed.
  -p, --properties      Consider OPC UA Properties.
  -vrs, --value-rank-subshapes
                        Add ValueRank subshapes (instead of nest the whole expression).
  -sb, --semantic-bridge
                        Add Semantic Bridge in JSON-LD to allow convenient mapping back to OWL (includes --node-
                        references)
  -nr, --node-references
                        Add a reference (base:hasNodeRef) from every entity to the OPC UA node it is created from
```

Every entity id is `urn:uaentity:` (or the `-i` prefix) followed by the base64url encoded
canonical ExpandedNodeId of the node it is created from. It is derived from, but deliberately
different from, the node IRI. With `-nr` (or `-sb`) every entity also gets a `base:hasNodeRef`
to its node.

Extract ngsi-ld prototype:

    python3 ./owl2instances.py -t http://opcfoundation.org/UA/Pumps/PumpType -n http://yourorganisation.org/InstanceExample/ pumpexample.owl.ttl

The prefix given by `-i` must start an IRI. When the entities are used as devices, it should be a URN like the default `urn:uaentity:`: Device IDs are part of the MQTT topics, a `/` in an ID breaks them.

`bindings.ttl` is used by the [dataservice](../dataservice/README.md#opc-ua-example-from-the-pump-nodeset-to-ngsi-ld) to forward the values of an OPC UA server.


Check the SHACL compliance:

    pyshacl -s shacl.ttl -e entities.ttl -df json-ld instances.jsonld

## owl2kms.py

Assemble the output of `nodeset2owl.py` and `owl2instances.py` into a KMS
package (Knowledge, Model, Shapes; see [../kms/README.md](../kms/README.md)), so
an OPC UA machine can be handed over, verified and versioned like any other
package:

```console
python3 owl2kms.py instanceexample.owl.ttl entities.ttl -s shacl.ttl -m instances.jsonld \
    -c context.jsonld -n opcua-pumps [-v 0.1.0] -o ../kms/opcua-pumps
```

- `knowledge/` holds the instance ontology, the entities and every ontology
  they import (`owl:imports`), one file each, so the type system travels with
  the package. An import of a copied file names that ontology's IRI rather than
  its path on the building machine, and the same inputs give the same package
  digest.
- `shacl.ttl`, `model-instance.jsonld` (from `instances.jsonld`) and
  `context.jsonld` come from `owl2instances.py`; the NGSI-LD vocabulary is
  copied into `vocabulary/ngsild.ttl`.
- `kms.yaml` declares `name`, `version` (`0.1.0` by default) and `format: 1`.
- The package holds the model only, no examples: it is a draft, `semforge
  verify --tests` reports 0 % coverage and `semforge publish` refuses it.

Each instance example has a `package` target, writing
`../kms/opcua-pumps`, `../kms/opcua-laser` or `../kms/opcua-simple`
(`KMS_OUT=<dir>` writes elsewhere):

```console
make -f translate_pumpExample.make package
../SemForge-SDK/venv/bin/semforge verify ../kms/opcua-pumps
```

`make kms-packages` builds all three and `make kms-packages-check` verifies
them; the `Build` workflow runs both. Generated packages are never committed:
`semantic-model/kms` ignores `opcua-*`.

## owl2vt.py

Transform a semantic bridge `*.owl.ttl` (nodeset2owl.py output) into an OWL ontology of
Virtual Types (`*.vt.owl.ttl`) for reasoning with HermiT, see
[owl_to_virtualtypes.md](./owl_to_virtualtypes.md) and
[Virtual Type Validation](./docs/virtual-type-validation.md).

```console
usage: owl2vt.py [-h] [-o OUTPUT] [-i [INPUTS ...]] [-b BASEONTOLOGY] [-u OPCUANAMESPACE] [--roots ROOTS]
                 [--no-disjoint-valuerank] [--require-modelling-rule] [-q]
                 input

Transform a Semantic Bridge ttl into an OWL ontology of Virtual Types.

positional arguments:
  input                 Path to the Semantic Bridge ttl file, e.g. core.owl.ttl or di.owl.ttl

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Resulting file.
  -i [INPUTS ...], --inputs [INPUTS ...]
                        Additional already-processed dependency ttl file(s)/URL(s) to import, on top of whatever this
                        file's own owl:imports already declare (which are resolved automatically for file://
                        locations). Use this only if a dependency can't be auto-resolved, e.g. a remote URL not
                        available locally.
  -b BASEONTOLOGY, --baseOntology BASEONTOLOGY
                        Namespace of the base terms, e.g. https://industryfusion.github.io/contexts/ontology/v0/base/
  -u OPCUANAMESPACE, --opcuaNamespace OPCUANAMESPACE
                        OPC UA namespace, e.g. http://opcfoundation.org/UA/
  --roots ROOTS         Comma-separated list of type local names to scope Virtual Type generation to (e.g.
                        "PumpType,MotorType"), instead of every ObjectType/VariableType the input file itself
                        declares. Useful for a first, fast test run before processing the whole file.
  --no-disjoint-valuerank
                        Do not declare the ValueRank symbolic classes pairwise disjoint.
  --require-modelling-rule
                        Skip a declaration entirely (no Virtual Type, no restriction, nothing nested inside it visited
                        either) unless it carries a recognized ModellingRule
                        (Mandatory/Optional/(Mandatory|Optional)Placeholder) -- the strict OPC UA sense of "Instance
                        Declaration". Default off: every Object/Variable child is processed regardless, including e.g.
                        named States/Transitions inside a StateMachineType-derived type, which OPC UA aggregates via
                        HasComponent/HasProperty with no ModellingRule at all. Use this to get a Virtual Type count
                        that lines up 1:1 with a strict Instance Declaration count -- see virtual_type_stats.py's own
                        --include-unruled, which is this flag's inverse.
  -q, --quiet           Suppress per-root progress output.
```

### Example

    python3 owl2vt.py core.owl.ttl -o core.vt.owl.ttl
    python3 owl2vt.py di.owl.ttl -o di.vt.owl.ttl

or `make -f translate_default_nodesets.make core.vt.owl.ttl di.vt.owl.ttl`.

## extractIffBindings.py

Create the bindings of an *IFF Semantic Data Model* from a nodeset which follows the
[IFF Mappings Companion Specification](./IffMappingsCompanionSpec/README.md).

```console
usage: extractIffBindings.py [-h] [-fi FOLDER_ID] [-bv BINDING_VERSION] [-bn BINDING_NAMESPACE] [-b BINDINGS]
                             [-i INSTANCE_FILE] [-n IFFMAPPING_NAMESPACE] [-d]
                             mapping

parse nodeset instance and create ngsi-ld model

positional arguments:
  mapping               Path to the mapping ttl file which contains the IFFMappingsFolder Object.

options:
  -h, --help            show this help message and exit
  -fi FOLDER_ID, --folder-id FOLDER_ID
                        Id of IFFMappingFolder Object. default: 42
  -bv BINDING_VERSION, --binding-version BINDING_VERSION
                        Version of the binding model. default: 0.1
  -bn BINDING_NAMESPACE, --binding-namespace BINDING_NAMESPACE
                        Namespace prefix for binding ontology. default: https://industry-fusion.org/UA/Bindings/
  -b BINDINGS, --bindings BINDINGS
                        Filename of bindings output file. default: bindings_iffmodel.ttl
  -i INSTANCE_FILE, --instance-file INSTANCE_FILE
                        Filename of instances file contating entity Ids. default: iff_instances.jsonld
  -n IFFMAPPING_NAMESPACE, --iffmapping-namespace IFFMAPPING_NAMESPACE
                        Overwrite Namespace for IFF mapping ontology. default: https://industry-fusion.org/UA/Mapping/
  -d, --debug           Help debugging. e.g by setting seed.
```

The `IFFMappingsFolder` is found by its `uardf:nodeId`. Without NamespaceMetadata it is a
dynamic node, so the mapping nodesets have to be translated with `--serverUri`; see the
[example](./IffMappingsCompanionSpec/README.md#example).


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

Validate a shacl.ttl/entities.ttl/instances.jsonld combination, a single semantic-bridge
ontology, or a Virtual-Types `*.vt.owl.ttl` ontology's logical consistency.


```console
usage: validate.py [-h] [-s SHACL] [-e EXTRA] [-df DATA_FORMAT] [-d] [-m MODE] [-st] [-x] [-ni] [-so] [-ns] [-me] data

SHACL Validation with Shape and Focus Context

positional arguments:
  data                  Path to RDF data file to validate

options:
  -h, --help            show this help message and exit
  -s SHACL, --shacl SHACL
                        Path to a SHACL shapes file, or a directory of *.shacl.ttl files to merge. Defaults to
                        shacl.ttl for -m instance (owl2instances.py's output); for -m ontology,
                        defaults to the validation/ontology/ directory (every structural rule file, merged). Pass a
                        single file explicitly to scope -m ontology to one rule.
  -e EXTRA, --extra EXTRA
                        Path to extra ontology file
  -df DATA_FORMAT, --data-format DATA_FORMAT
                        Data file format (e.g., turtle, json-ld, xml). If not provided infered from data-file name
                        (.jsonld, .ttl).
  -d, --debug           Debug output
  -m MODE, --mode MODE  Modes: "instance" to validate instance, "ontology" to validate ontology files, "vt" to check a
                        *.vt.owl.ttl Virtual-Types ontology for logical consistency via the HermiT DL reasoner.
  -st, --strict         Use strict, non accelerated SPARQL query.
  -x, --extended        Use eXtended output with detailed context.
  -ni, --no-imports     No imports of dependent ontologies.
  -so, --sparql-only    Only apply sparql-rules
  -ns, --no_sparql      Only apply sparql-rules
  -me, --merge-entity   Merge entity graph into the data graph (experimental)
```

This tool operates in three modes:

1) **instance** (default) takes shacl.ttl, instances.ttl and entities.ttl and executes a shacl evaluation equivalent to
`pyshacl -s shacl.ttl -e entities.ttl -df json-ld instances.jsonld`

2) **ontology** takes a semantic-bridge `*.owl.ttl` file (e.g. `core.owl.ttl`) and checks it against
structural SHACL constraints -- things like `hasComponent`/`hasProperty`/`ValueRank`/`historizing`/
`modellingRule` being used consistently. `-s` accepts either a single shapes file or a directory,
in which case every `*.shacl.ttl` file directly within it is merged (SHACL shapes are additive, so
this is safe -- each file targets different classes/properties). By default (no `-s` given) it
checks against the whole `validation/ontology/` directory; pass a single file explicitly to scope
the check to just one rule, e.g. `-s validation/ontology/rankValue.shacl.ttl` (this is what
`tests/validation/test.bash` does, to isolate which specific rule fired in each test case).

3) **vt** takes a Virtual-Types `*.vt.owl.ttl` file (owl2vt.py's output) and checks it for logical
consistency with the real HermiT DL reasoner instead of SHACL: whether the OPC UA type restrictions
it encodes are jointly satisfiable, i.e. free of contradictory overrides. This is a thin wrapper
around `check_consistency.py` (see there for the full picture: multi-file batch mode, `--combine`,
CSV export) for validating one file through the same CLI as the other two modes. Requires
`owlready2` (`pip install owlready2==0.51`) and a `java` runtime on PATH -- see `check_consistency.py`'s
own module docstring for why it isn't a default dependency. `-s`/`-e`/`-st`/`-x`/`-so`/`-ns`/`-ni` are
SHACL-specific and ignored in this mode.


The tool will provide more context information when used with `-x` switch (instance mode only).
### Example

Validate `instances.jsonld` against entities.ttl` and `shacl.ttl` with extended output:

        python3 validate.py -x instances.jsonld

Validate a semantic-bridge ontology against every structural rule (equivalent to
`-s validation/ontology`, the default):

        python3 validate.py -m ontology core.owl.ttl

Validate a semantic-bridge ontology against just its ValueRank consistency:

        python3 validate.py -m ontology -s validation/ontology/rankValue.shacl.ttl core.owl.ttl

Check a Virtual-Types ontology for logical consistency:

        python3 validate.py -m vt pumps.vt.owl.ttl

Worked examples for all three modes, including deliberately broken nodesets and
how to read each report, are in
[docs/validation-overview.md](./docs/validation-overview.md).

