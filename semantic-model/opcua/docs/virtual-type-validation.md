# Tutorial: Virtual Type (Logical) Validation

This is validation type 3 of 3 (see [Validation Overview](./validation-overview.md)).
It is the only one that does not use SHACL.

The question it answers is: **are the type declarations jointly satisfiable?**
An OPC UA subtype may only *narrow* what it inherits. Narrowing is allowed
independently in the ObjectType hierarchy and in the VariableType hierarchy —
and two narrowings that are each perfectly legal can combine into a type that
no server could ever instantiate.

## The contradiction, in OPC UA terms

Before any of the tooling, here is the problem it exists to find. Two
declarations, each well formed on its own.

**Start.** `BaseType` is an ObjectType that declares a Mandatory Property
`Signal`, of `PropertyType` and DataType `Double`, with `ValueRank = 1`
(OneDimension) and `ArrayDimensions = "0"`. From this point on, every instance
of `BaseType` — and of every subtype of `BaseType` — has a one-dimensional
`Signal`.

**The override.** `SubType` derives from `BaseType` and re-declares `Signal`,
this time with `ValueRank = 2` (a two-dimensional array) and
`ArrayDimensions = "0,0"`. Re-declaring an inherited component is ordinary OPC
UA — it is how a subtype narrows what it inherits — and the re-declaration is
locally consistent to boot: `ValueRank = 2` and a two-entry `ArrayDimensions`
agree with each other exactly.

```
   ObjectType hierarchy

   BaseType
     |  Signal : PropertyType/Double, ValueRank 1   (OneDimension)
     |
     v  HasSubtype
   SubType
        Signal : PropertyType/Double, ValueRank 2   (MoreDimensions)
```

**The result cannot exist.** `Signal` in `SubType` is bound by two decisions at
once:

- From its **own** declaration: `ValueRank = 2`, which the Semantic Bridge
  collapses into the symbolic class `ValueRank_MoreDimensions`.
- From the **inherited** declaration: `BaseType` already fixed `Signal` to
  `ValueRank = 1`, i.e. `ValueRank_OneDimension`. A subtype may restrict an
  inherited declaration, but it cannot swap it for an incompatible one.

`ValueRank_OneDimension` and `ValueRank_MoreDimensions` are declared pairwise
disjoint, and `sb:hasValueRank` is Functional — a node has at most one rank. So
`SubType` is a type no server can instantiate, even though neither declaration
is malformed on its own.

That last sentence is what makes this hard to catch. Run
[ontology validation](./ontology-validation.md) over the very same nodeset and
it passes, because every node is individually correct:

```
python3 validate.py -m ontology -ni signal.owl.ttl
```

```
Validation Conforms: True
No validation errors found.
```

## How virtual typing finds it

The reason no per-node check can see this is that **`Signal` is not one
thing**. `BaseType` has a `Signal` and `SubType` has a `Signal`; they are
different nodes that happen to share a BrowsePath, and the fact that the second
one *inherits the first one's restrictions* is a rule the reader is expected to
apply mentally. OPC UA has no name for "the `Signal` of `SubType`" as an entity
distinct from "the `Signal` of `BaseType`".

`owl2vt.py` gives that concept a name. Walking each type's *Effective
Declaration Tree* — its own declared children plus everything inherited from
its supertype, with local overrides taking precedence — it mints one **Virtual
Type** class per (owning type, BrowsePath) pair, and writes the inheritance out
as `rdfs:subClassOf` edges:

```
VT(BaseType, "Signal")  ⊑ PropertyType
                        ⊑ ValueRank_OneDimension     (the base declaration)

VT(SubType, "Signal")   ⊑ PropertyType
                        ⊑ ValueRank_MoreDimensions   (the override)
                        ⊑ VT(BaseType, "Signal")      ← the inheritance
```

That last edge is the whole trick. It turns "a subtype inherits the base type's
restrictions", which a human applies by reading, into a subclass edge a
reasoner applies mechanically. Once both parents sit on one named class, the
conflict stops being an argument about specification prose and becomes a plain
subsumption question:

`VT(SubType,"Signal")` is below both `ValueRank_MoreDimensions` and — through
the inherited Virtual Type — `ValueRank_OneDimension`. Those two classes are
declared disjoint, and `sb:hasValueRank` is a Functional property, so the class
has no possible members. And because `SubType` requires at least one `Signal`
of that class (`owl:minQualifiedCardinality 1`), `SubType` is empty too.

The reasoner reports both, which is exactly the chain above read back out.

The full transformation is described in
[`owl_to_virtualtypes.md`](../owl_to_virtualtypes.md); the size of the
resulting ontologies is analysed in
[`virtual_type_explosion.md`](../virtual_type_explosion.md).

## The pipeline

Virtual Type validation has one more step than the other two validations:

```
NodeSet2.xml --[nodeset2owl.py]--> *.owl.ttl --[owl2vt.py]--> *.vt.owl.ttl --[HermiT]--> verdict
                                (Semantic Bridge)          (Virtual Types)
```

## Prerequisites

Beyond [Overview & Setup](./overview.md), this validation needs two things the
others do not:

```
pip install owlready2==0.51
```

and a **`java` runtime on `PATH`**.

`owlready2` is deliberately *not* in `requirements.txt` or
`requirements-dev.txt`, and `make setup` will not install it. It is
LGPL-3.0-or-later, and it bundles the HermiT.jar reasoner (also LGPL-3.0),
which is incompatible with this repository's default Apache-2.0 dependency set.
So it has to be an explicit, separate opt-in. It is used only to *locate* the
bundled HermiT.jar; the reasoning itself runs as a plain `java` subprocess.

Check both:

```
python3 -c "import owlready2; print(owlready2.VERSION)"
java -version
```

Then build the core ontologies:

```
export BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.3/base.ttl
export BASE_ONTOLOGY_NS=https://industryfusion.github.io/contexts/ontology/v0/base/

make -f translate_default_nodesets.make core.owl.ttl core.vt.owl.ttl
```

Both files are needed: `core.owl.ttl` is what your own nodeset is built
against, and `core.vt.owl.ttl` is what your generated Virtual-Types file will
`owl:imports`. Without the latter the reasoner cannot resolve the OPC UA base
types and the check is meaningless.

## The example nodeset

[`tests/owl2vt/test_vt_contradiction.NodeSet2.xml`](../tests/owl2vt/test_vt_contradiction.NodeSet2.xml)
declares exactly the two declarations above, and nothing else.

It is deliberately the same fixture the end-to-end suite uses:
`tests/owl2vt/test.bash` runs it and asserts that a contradiction is found, and
`tests/validation/test.bash` runs `validate.py -m vt` over its expected
Virtual-Types output. Every command and every line of output quoted below is
therefore covered by CI, and cannot drift away from the tutorial unnoticed.

## Step 1: Convert the nodeset to OWL

```
python3 nodeset2owl.py tests/owl2vt/test_vt_contradiction.NodeSet2.xml \
    -i ${BASE_ONTOLOGY} core.owl.ttl \
    -b ${BASE_ONTOLOGY_NS} -burl ${BASE_ONTOLOGY} \
    -v http://example.com/v0.1/signal/ -p signal -o signal.owl.ttl
```

## Step 2: Derive the Virtual Types

```
python3 owl2vt.py signal.owl.ttl -o signal.vt.owl.ttl
```

```
Parsing signal.owl.ttl ...
Resolving imports: ['https://industryfusion.github.io/contexts/staging/ontology/v0.3/base.ttl', 'file:///.../core.owl.ttl']
...
No --roots given: generating Virtual Types for all 2 ObjectType/VariableType classes this file itself declares (not its imports). This can take a while on the full core.owl.ttl (~600 types); pass --roots to scope a faster first look.
Building Virtual Types and restrictions ...
  [1/2] (5.1s elapsed) http://my.test/BaseType
  [2/2] (5.1s elapsed) http://my.test/SubType
Writing 239 triples to signal.vt.owl.ttl (5.1s elapsed) ...
Done in 5.1s.
```

`owl2vt.py` only derives Virtual Types for the types the input file *itself*
declares — two here. The hundreds of types in `core.owl.ttl` are not
re-derived; the output `owl:imports` `core.vt.owl.ttl` instead. On a large
companion specification, use `--roots` to scope the run to a few named types
for a faster first look.

## Step 3: Run the reasoner

```
python3 validate.py -m vt signal.vt.owl.ttl
```

```
Validation Conforms: False

=== HermiT DL Consistency Report ===
2 unsatisfiable class(es) in signal.vt.owl.ttl:
  http://my.test/SubType
  http://my.test/VT_785e8afd2dbfb8041e9beca4
```

`validate.py` exits with status `1`, so this works in CI.

The `http://my.test/` namespace is the one the fixture's own `<Models>` entry
declares; it has nothing to do with the `-v` value passed in step 1, which only
names the ontology being written.

An **unsatisfiable class** is one the reasoner has proven equivalent to
`owl:Nothing`: it can have no members, ever. `SubType` is unsatisfiable — that
ObjectType cannot be instantiated by any server — and the Virtual Type
alongside it says *which member* made it so.

## Step 4: Read the report

`VT_785e8afd2dbfb8041e9beca4` is a generated Virtual Type. The name is a
sha256 digest of `"<owning type IRI>|<BrowsePath>"`, truncated to 24 hex
characters, so it is stable and reproducible: the same model always yields the
same name. Two ways to find out what it stands for.

**Look it up in the generated file.** Every Virtual Type carries the BrowsePath
it was minted for:

```
grep -A 16 "VT_785e8afd2dbfb8041e9beca4> a owl:Class" signal.vt.owl.ttl
```

```turtle
<http://my.test/VT_785e8afd2dbfb8041e9beca4> a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ;
            owl:onProperty sb:hasValueRank ;
            owl:someValuesFrom opcua:ValueRank_MoreDimensions ],
        ...
        [ a owl:Restriction ;
            owl:allValuesFrom opcua:ValueRank_MoreDimensions ;
            owl:onProperty sb:hasValueRank ],
        <http://my.test/VT_0d94b86d0fb80fa6be1b3122>,
        opcua:PropertyType ;
    sb:originalBrowsePath "http://my.test/Signal" .
```

**Or recompute the digest** for a (type, BrowsePath) pair you suspect:

```
python3 -c "import hashlib; print(hashlib.sha256('http://my.test/SubType|http://my.test/Signal'.encode()).hexdigest()[:24])"
```

```
785e8afd2dbfb8041e9beca4
```

So the flagged class is *`SubType`'s `Signal`*, it is below
`ValueRank_MoreDimensions`, and it is below `VT_0d94b86d0fb80fa6be1b3122` —
which the same lookup identifies as *`BaseType`'s `Signal`*:

```turtle
<http://my.test/VT_0d94b86d0fb80fa6be1b3122> a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ;
            owl:allValuesFrom opcua:ValueRank_OneDimension ;
            owl:onProperty sb:hasValueRank ],
        ...
        [ a owl:Restriction ;
            owl:onProperty sb:hasValueRank ;
            owl:someValuesFrom opcua:ValueRank_OneDimension ],
        opcua:PropertyType ;
    sb:originalBrowsePath "http://my.test/Signal" .
```

`ValueRank_OneDimension` on one side, `ValueRank_MoreDimensions` on the other,
and `sb:hasValueRank` is Functional — one value cannot be both. That is the
contradiction from the first section, restated in the form the reasoner
actually consumed.

The rule of thumb when reading these reports: **the Virtual Types tell you
*where*, the real types tell you *what*.** Take the `sb:originalBrowsePath` of
each flagged `VT_...` class to locate the offending BrowseName, then look at
which real types it ended up beneath.

## Step 5: Fix it

The report named `SubType`'s `Signal`, and the two Virtual Types disagreed on
exactly one property: `sb:hasValueRank`. So the repair is a single declaration
— give the override the rank it inherits instead of an incompatible one:

```xml
<!-- was: ValueRank="2" ArrayDimensions="0,0" -->
<UAVariable NodeId="ns=1;i=2101" BrowseName="1:Signal"
            DataType="Double" ValueRank="1" ArrayDimensions="0">
```

Re-run the same three steps on the corrected nodeset and the reasoner is
satisfied:

```
python3 validate.py -m vt signalfixed.vt.owl.ttl
```

```
Validation Conforms: True
No validation errors found.
```

Dropping the re-declaration from `SubType` altogether works just as well —
`SubType` then simply inherits `BaseType`'s `Signal` unchanged. What is *not* a
fix is relaxing `BaseType` to `ValueRank = -2` (Any) so that both ranks become
legal narrowings: that removes the contradiction by giving up the guarantee
that made the base type worth declaring.

## Other kinds of contradiction

The same mechanism catches conflicts along every axis an OPC UA declaration
has. Each has its own end-to-end fixture under `tests/owl2vt/`, alongside the
one this tutorial walked through, and each is worth reading as a further worked
example:

| Axis | Fixture |
|------|---------|
| an instance declaration's `ValueRank` against its ancestor declaration (this tutorial) | `test_vt_contradiction.NodeSet2.xml` |
| a VariableType's *own* `ValueRank` against an instance declaration that overrides it | `test_vt_type_valuerank_contradiction.NodeSet2.xml` |
| the Variable's `DataType` | `test_vt_datatype_contradiction.NodeSet2.xml` |
| the Variable's own VariableType, overridden to a disjoint sibling | `test_vt_variabletype_contradiction.NodeSet2.xml` |
| a component Object's ObjectType | `test_vt_objecttype_contradiction.NodeSet2.xml` |

Each has a sibling fixture asserting that a *legal* narrowing along the same
axis is **not** flagged (`test_vt_datatype_subtype_override`,
`test_vt_objecttype_optional_no_contradiction`,
`test_vt_modellingrule_narrowing`, ...). The negative cases matter just as
much: a reasoner that flags correct models is worse than no reasoner at all.

## Checking many files at once

`validate.py -m vt` is a single-file wrapper that puts this check behind the
same CLI as the other two modes. The underlying tool, `check_consistency.py`,
does more.

Check several files, each on its own:

```
python3 check_consistency.py core.vt.owl.ttl signal.vt.owl.ttl
```

```
core.vt.owl.ttl                OK  consistent  (33340 triples, 2.9s)
signal.vt.owl.ttl              FAIL  2 unsatisfiable class(es)  (33554 triples, 2.1s)
    http://my.test/SubType
    http://my.test/VT_785e8afd2dbfb8041e9beca4

1/2 ontologies consistent.
Ontologies with issues: signal.vt.owl.ttl
```

With **no** file arguments it sweeps every `*.vt.owl.ttl` that
`translate_default_nodesets.make` knows how to build and that exists on disk.
This is the final step of `make test`.

Other options:

- `-c` / `--combine` merges *all* given files, plus everything they
  transitively import, into one ontology and reasons over the union. Two
  specifications that do not import each other are otherwise never loaded into
  the same reasoning pass, so an interaction between them would never surface
  from checking either one individually:

  ```
  python3 check_consistency.py -c tmc.vt.owl.ttl pumps.vt.owl.ttl
  ```

- `-o report.csv` also writes the results as CSV.
- `--expect-contradiction` / `--expect-none` turn the run into an assertion:
  the command exits non-zero when the verdict is not the expected one. This is
  what `tests/owl2vt/test.bash` checks each scenario with.

## Pitfalls

**Passing the semantic-bridge file instead of the Virtual-Types file.** The two
differ by only `.vt` in the name and it is an easy slip:

```
python3 validate.py -m vt signal.owl.ttl
```

fails with

```
ValueError: .../signal.owl.ttl looks like a semantic-bridge ttl (it has base:definesType triples),
not a generated Virtual-Types ontology. ... Pass its Virtual-Types sibling instead (signal.vt.owl.ttl);
if it does not exist yet, build it first with 'make -f translate_default_nodesets.make' or
'python3 owl2vt.py signal.owl.ttl'.
```

The check is deliberate. A semantic-bridge file has none of the Virtual Type
classes and restrictions the reasoner needs, so without this guard it would
report a meaningless "consistent" verdict while validating nothing.

**A missing `*.vt.owl.ttl` dependency.** Your generated file `owl:imports` the
Virtual-Types file of every specification it depends on, by absolute `file://`
URL. Imports are resolved eagerly and a missing one is fatal rather than a
warning, so you get a bare `FileNotFoundError` naming it — from `owl2vt.py`
when it resolves the inputs it is generating from, and from
`check_consistency.py` (or `validate.py -m vt`) when it follows the imports of
an already-generated file. Neither writes partial output:

```
FileNotFoundError: [Errno 2] No such file or directory: '.../di.vt.owl.ttl'
```

The Makefile builds the `*.owl.ttl` chain in dependency order, but it does
**not** chain the `*.vt.owl.ttl` targets, so list them all yourself. For the
pump specification, for instance:

```
make -f translate_default_nodesets.make core.vt.owl.ttl di.vt.owl.ttl machinery.vt.owl.ttl pumps.vt.owl.ttl
```

For the tutorial above, `core.vt.owl.ttl` is the only dependency, which is why
the Prerequisites build it alongside `core.owl.ttl`.

**Moving a `*.vt.owl.ttl` after generating it.** Those `owl:imports` are
absolute paths written at generation time. Regenerate rather than relocate.

**Reasoning takes real time on big specifications.** HermiT is exponential in
the worst case. A small model like this one is seconds; the full corpus sweep
in `make test` is minutes. Use `--roots` in `owl2vt.py` to scope the ontology
while iterating on a design.
