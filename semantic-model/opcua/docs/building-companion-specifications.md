# Convert Companion Specifications

Companion specifications and their dependencies must be converted to ensure that all dependencies are fulfilled. The specifications can be built for *local* testing with *local* dependencies or for *global* use with IRIs. The main difference is that for *local* testing, the dependencies are referencing the local filesystem and can only be used on the current *local* system whereas the *globallly* built specifications can be imported or used from everywhere with Internet access.

In OWL, dependencies are managed by `owl:imports` triples. A *global* import contains an IRI like so:

    owl:imports <https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl> ;

In contrast, a *local* import is referencing the local directories in a File URI, for instance:

     owl:imports </home/user/src/IndustryFusion/DigitalTwin/semantic-model/opcua/core.owl.ttl>

For convenience, a Makefile is provided to create the "usual suspect" companion specifications (note nodeset version: `NODESET_VERSION=UA-1.05.03-2023-12-15`):

    make -f translate_default_nodesets.make

creates the *local* version of the specifications.

## Convert Specific Companion Specifications

Rather than reconstructing a NodeSet2.xml's raw.githubusercontent.com URL by hand, `translate_default_nodesets.make` can print `export VAR=value` lines for all of them (and the base ontology), which you source directly into your shell:

    source <(make -f translate_default_nodesets.make -s print-nodesets)

This defines `BASE_ONTOLOGY` and one `<NAME>_NODESET_URL` variable per companion spec (`CORE_NODESET_URL`, `DI_NODESET_URL`, `MACHINERY_NODESET_URL`, ...) -- see the README's [nodeset2owl.py section](../README.md#get-the-nodeset-source-urls-into-your-shell) for details.

`nodeset2owl.py` cannot yet auto-detect dependencies for you, but it does refuse to proceed with a clear, upfront error if a namespace referenced by the target NodeSet2.xml isn't covered by the ttls passed via `-i`, rather than failing obscurely partway through parsing -- see its usage below. A conversion must still add the dependencies manually, though. Every specification is dependend on the base ontology:

    <https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl>

For instance, converting the core OPCUA specification looks as follows:


    NODESET_VERSION=UA-1.05.03-2023-12-15
    CORE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Schema/Opc.Ua.NodeSet2.xml
    BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
    python3 nodeset2owl.py ${CORE_NODESET} -i ${BASE_ONTOLOGY} -p opcua -o core.owl.ttl

The `DI` specification is translated as follows:

    NODESET_VERSION=UA-1.05.03-2023-12-15
    DI_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/DI/Opc.Ua.Di.NodeSet2.xml
    BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
    CORE_ONTOLOGY=core.owl.ttl
    python3 nodeset2owl.py  ${DI_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -p devices -o devices.owl.ttl

And the `Machinery` specification is converted like so:

    NODESET_VERSION=UA-1.05.03-2023-12-15
    CORE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Schema/Opc.Ua.NodeSet2.xml
    BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
    MACHINERY_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Machinery/Opc.Ua.Machinery.NodeSet2.xml
    CORE_ONTOLOGY=core.owl.ttl
    DEVICES_ONTOLOGY=devices.owl.ttl
    python3 nodeset2owl.py ${MACHINERY_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} -p machinery -o machinery.owl.ttl

In general, to determine the dependencies, the `<Models>` section of the target Nodeset must be analyzed. In the Pumps specification it looks e.g. like this

```
 <Models>
    <Model ModelUri="http://opcfoundation.org/UA/Pumps/" Version="1.0.0" PublicationDate="2021-04-19T00:00:00Z">
      <RequiredModel ModelUri="http://opcfoundation.org/UA/" Version="1.04.7" PublicationDate="2020-07-15T00:00:00Z" />
      <RequiredModel ModelUri="http://opcfoundation.org/UA/DI/" Version="1.02.2" PublicationDate="2020-06-02T00:00:00Z" />
      <RequiredModel ModelUri="http://opcfoundation.org/UA/Machinery/" Version="1.0.0" PublicationDate="2020-09-25T00:00:00Z" />
    </Model>
  </Models>

```
and this suggest that the nodeset is (besides the base specification) dependends on `core.owl.ttl`, `devices.owl.ttl` and `machinery.owl.ttl`. The conversation would then look like:

```
NODESET_VERSION=UA-1.05.03-2023-12-15
PUMPS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Pumps/Opc.Ua.Pumps.NodeSet2.xml
BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
python3 nodeset2owl.py  ${PUMPS_NODESET} -i ${BASE_ONTOLOGY} core.owl.ttl devices.owl.ttl machinery.owl.ttl -p pumps -o pumps.owl.ttl

```

## Extract SHACL and JSON-LD from instances



## Global Specifications

IndustrsFusion Foundation is offering a set of `usual` suspects here: 

    https://industryfusion.github.io/contexts/staging/opcua/v0.1/
