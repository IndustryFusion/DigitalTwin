# Dataservice setup

## Setup and Activate Device

## Use Dataservice to send testdata
Start dataservice with `startDataservice.py`:
    python3 ./startDataservice.py \<ontology-dir\> \<type\> \<binding-name\>

*\<ontology\>* is supposed to be downloadable from a directory containing different *.ttl files, *\<type\>* is the (in the ontology context) namespaced class (e.g. `ex:MyClass` if `ex:` is defined in the ontologies context) and *\<binding-name\>* is the name of a *.ttl file in the *bindings* subdirectory of the ontoloy.

Example:

    python3 ./startDataservice.py  https://industryfusion.github.io/contexts/example/v0.1  iffBaseEntity:Cutter  base_test.ttl
