# Validation Overview

Translating an OPC UA nodeset into Semantic Web data produces three different
artefacts (see [Overview](./overview.md)), and each of them can be *wrong* in a
different way. Accordingly there are three separate validations in this
repository, answering three different questions:

| # | Validation | Question it answers | Input it consumes | Engine | Tutorial |
|---|------------|---------------------|-------------------|--------|----------|
| 1 | **Ontology** (graph) | Is the *nodeset itself* well formed? Are `HasComponent`, `HasProperty`, `ValueRank`, `Historizing` and `ModellingRule` used the way OPC UA Part 3 says they must be? | the Semantic Bridge ontology `*.owl.ttl` (`nodeset2owl.py` output) | SHACL (`pyshacl`) | [Ontology Validation](./ontology-validation.md) |
| 2 | **Instance** | Does a *concrete object* conform to the type it claims to be? Are all Mandatory components present, of the right type and cardinality? | `instances.jsonld` + `shacl.ttl` + `entities.ttl` (`owl2instances.py` output) | SHACL (`pyshacl`) | [Simple Example](./simple-example.md#validation-of-instances) |
| 3 | **Virtual Types** (logical) | Are the *type declarations themselves* jointly satisfiable? Does some subtype override an inherited declaration in a way that no instance could ever satisfy? | the Virtual Types ontology `*.vt.owl.ttl` (`owl2vt.py` output) | HermiT DL reasoner | [Virtual Type Validation](./virtual-type-validation.md) |

All three are reachable through the same CLI, `validate.py`, selected with `-m`:

```
python3 validate.py -m ontology core.owl.ttl        # 1
python3 validate.py instances.jsonld                # 2  (-m instance is the default)
python3 validate.py -m vt core.vt.owl.ttl           # 3
```

## Why three and not one

The three validations are not three flavours of the same check; they operate on
different graphs and, in the case of the third, with a fundamentally different
engine.

**Ontology validation** looks at one node at a time (plus the nodes it directly
references) and asks whether the *modelling* is legal. A `HasProperty` reference
pointing at an `Object` instead of a `Variable`, a `ValueRank` of `-7`, an
`ArrayDimensions` list whose length disagrees with the `ValueRank`: these are
errors in the nodeset that no XML schema catches, because the OPC UA
`UANodeSet.xsd` is happy with any well-formed integer. It runs *before* you have
any instance data at all, and it is the right check to run on a companion
specification you have just written or just downloaded.

**Instance validation** takes the SHACL shapes that `owl2instances.py` derived
from the type definitions and applies them to concrete NGSI-LD entities. This is
the check that runs in the live platform, on the data that actually flows in from
an OPC UA server. It answers "is *this* pump a valid `PumpType`?", not "is
`PumpType` a sensible type?".

**Virtual Type validation** is the odd one out. SHACL is a *constraint* language:
it evaluates a shape against a graph and reports the nodes that fail. It has no
notion of "these two declarations, taken together, describe something that cannot
exist". But that is precisely the interesting failure mode of an OPC UA type
hierarchy: a subtype is only allowed to *narrow* what it inherits, and an
override that narrows to something incompatible produces a type that no server
can ever instantiate. Nothing is malformed; every node passes ontology
validation; every instance would pass instance validation, because no instance
can exist. Finding this requires a Description-Logic reasoner, which is why
`owl2vt.py` first compiles the type hierarchy into an OWL ontology of *Virtual
Types* and `check_consistency.py` then runs HermiT over it.

## Which one should I run?

- Wrote or imported a **companion specification**? Run **ontology validation**.
- Have an **instance nodeset**, or live data from a server? Run **instance
  validation**.
- Designed a **type hierarchy with subtypes that override inherited components**?
  Run **Virtual Type validation**. This is the only one of the three that can
  find contradictions spanning a supertype and its subtype.

Running all three is cheap and they are independent; `make test` in this
directory exercises all of them.

## A note on the base ontology

Every tutorial here builds its nodesets against the same two values, which are
the ones `translate_default_nodesets.make` uses:

```
export BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.3/base.ttl
export BASE_ONTOLOGY_NS=https://industryfusion.github.io/contexts/ontology/v0/base/
```

They are **not** the same string and must not be conflated. `BASE_ONTOLOGY`
(passed as `-i` and `-burl`) is the fetchable *document*; `BASE_ONTOLOGY_NS`
(passed as `-b`) is the *term namespace* the `base:` IRIs inside it are minted
under. The v0.3 document is a patched version of the base ontology that still
declares its terms under the original, unchanged v0 namespace.

A nodeset and every nodeset it depends on must be built against the *same* base
ontology. Mixing a `core.owl.ttl` built with one version into a build that uses
another produces IRIs that silently fail to join up.

The URLs can be sourced straight from the Makefile so they cannot drift:

```
source <(make -f translate_default_nodesets.make -s print-nodesets)
```

That exports `BASE_ONTOLOGY` and one `<NAME>_NODESET_URL` per companion
specification. It does **not** export `BASE_ONTOLOGY_NS`, so set that one
yourself as shown above.
