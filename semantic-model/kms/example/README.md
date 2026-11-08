# example: the platform's default KMS package

KMS stands for Knowledge, Model, Shapes. This package is the platform's
default knowledge base, and `semantic-model/kms/default` links to it:
`knowledge.ttl` (ontology facts), `shacl.ttl` (constraints and SPARQL rules),
and `model-instance.jsonld` (example entities; `model-instance.scorpio.jsonld`
is the variant with one attribute instance per datasetId that Scorpio's batch
upsert accepts).

## A KMS package

This directory is a **KMS package**, as defined by the contract
`contracts/kms-package` (openspec change `gh-939-kms-package`): `kms.yaml`
names it (`example`), versions it and declares the package format
(`format: 1`); knowledge, shacl and model-instance may each be one file or a
directory of files; and everything it needs is inside it, including its
NGSI-LD vocabulary (`vocabulary/ngsild.ttl`, a copy of
`semantic-model/ontology/ngsild.ttl` that a test keeps equal).

```bash
semforge verify .                    # does it conform? prints the package digest
semforge pack .                      # example-<version>.kms.zip, with SHA256SUMS inside
semforge verify example-1.0.0.kms.zip    # every entry, then the package
unzip example-1.0.0.kms.zip -d x && (cd x && sha256sum -c SHA256SUMS)   # without SemForge
semforge test . --coverage           # the examples, and which constraints they make fire
```

**Version 1.0.0 is a draft.** A version is published (`semforge publish`) only
when every example meets its expectations and the examples make at least
`tests.coverage` (default 80 %) of the constraints fire, as asserted. Today 6
examples pass and make 4 of the 117 constraints fire as asserted (3.4 %), so
this package stays a draft until more cases are written. Once published, a version is immutable: changing the
package fails `semforge verify` until the version is raised (`semforge version
patch|minor|major`).

Not members, and left out of the archive: `model-instance.scorpio.jsonld`, a
broker serialisation of `model-instance.jsonld` that `semforge export --mode
broker` derives.

## Conventions

### Timestamps

Every timestamp carried as a **property value** uses ISO 8601 UTC with
millisecond precision and the `Z` suffix:

```
YYYY-MM-DDTHH:mm:ss.SSSZ        e.g. 2024-02-27T13:54:55.400Z
```

This is the same representation NGSI-LD prescribes for `observedAt`, so one
format flows from model to TSDB to writeback. The form is fixed-width, which
makes lexical order equal chronological order — SPARQL rules may compare two
timestamps directly (`FILTER(?ts1 > ?ts2)`), and `xsd:dateTime(?v)`
normalizes a value into this canonical form for such comparisons. Rules that
copy an attribute's `ngsild:observedAt` into a property value emit this form
as well.

Do not write epoch numbers into time-valued properties: they are ambiguous
(seconds vs milliseconds), untyped, and the two SQL dialects the pipeline
compiles to do not even share an epoch for their internal conversions.
Millisecond arithmetic remains available inside rule expressions — arithmetic
on time variables converts to milliseconds automatically.


## Prefixes

Every namespace has exactly one name, and `context.jsonld` is where the name is
agreed. `semforge prefixes .` checks it; `--fix` aligns the Turtle artifacts.

This was not always so. `:` denoted `base_shacl/` in `shacl.ttl` and
`base_entities/` in `knowledge.ttl`, and `default1:` denoted `filter_shacl/` and
`base_knowledge/` respectively -- so a term copied between the two files changed
meaning silently. The `default1..5` names came from `make ontology2kms` merging
modules with `rdfpipe`, which invents a name when the source supplies none.

`semforge.yaml` declares the four namespaces the context does not: the two
shapes namespaces, the test bindings, and NGSI-LD itself.

### base_knowledge/ is called `base`, everywhere

`shacl.ttl`, `knowledge.ttl` and `model-instance.jsonld` all say `base:`, and so
does the context. The SPARQL bodies inside `shacl.ttl` were brought along in a
separate pass -- they declare their own prefixes and the aligner deliberately
does not reach inside string literals, so that rename was verified by comparing
validation results before and after rather than by trusting the edit.

It went this way round rather than renaming to `iffBaseKnowledge` because the
obvious alternative does not work, and was tried:

* rdflib binds **one prefix per namespace**, so declaring a second name for
  `base_knowledge/` in the context evicts the first rather than adding to it;
* `shacl2flink/create_sql_checks_from_shacl.py` reads the context through rdflib
  and requires the survivor to be literally `base` -- *"No prefix 'base:' is
  found in your given context. This is needed!"*

So `context.jsonld` is byte-identical to what is published, and nothing upstream
has to change. `test_two_names_for_one_namespace_do_not_survive_rdflib` pins the
mechanism.

Moving to `iffBaseKnowledge` later remains possible, and now costs one
`semforge prefixes --fix` plus removing that hardcoded prefix name from the
compiler -- which is a wart whatever the spelling.

### The local/published split

`semforge.yaml` declares both:

```yaml
context:
  local: context.jsonld
  published: https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld
```

The model on disk keeps naming the **published** url -- it must, or it is
useless to anyone who resolves that url themselves. Loading substitutes the
**local** file's content in memory, so work here never depends on the network
and a term is usable as soon as it is agreed locally.

`semforge export` points the exported model back at the published url, and
checks first: any term the model uses that the published context does not
declare is an **error**, and nothing is written. That is the moment the split
has to be paid for, and the only moment anybody can act on it.

`semforge retarget --to local` is the other direction, for a model imported from
somewhere else.
