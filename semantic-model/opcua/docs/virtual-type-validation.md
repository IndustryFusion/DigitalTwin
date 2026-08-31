# Tutorial: Virtual Type (Logical) Validation

This is validation type 3 of 3 (see [Validation Overview](./validation-overview.md)).
It is the only one that does not use SHACL.

The question it answers is: **are the type declarations jointly satisfiable?**
An OPC UA subtype may only *narrow* what it inherits. Narrowing is allowed
independently in the ObjectType hierarchy and in the VariableType hierarchy —
and two narrowings that are each perfectly legal can combine into a type that
no server could ever instantiate.

## The contradiction, in OPC UA terms

Before any of the tooling, here is the problem it exists to find. Three
modelling steps, each legal on its own.

**Start.** `SensorValueType` is a VariableType under `BaseDataVariableType`.
Like its parent it declares `ValueRank = -2` (Any): its value may be a scalar,
or an array of any dimensionality. Nothing is committed yet.

**Step 1 — an ObjectType pins the rank.** `DeviceType` declares a Mandatory
component `Reading` whose TypeDefinition is `SensorValueType`, and gives it
`ValueRank = -1` (Scalar). Restricting Any to Scalar is exactly what an
instance declaration is entitled to do. From this point on, every instance of
`DeviceType` — and of every subtype of `DeviceType` — has a scalar `Reading`.

**Step 2 — a VariableType pins the rank differently.** `ArraySensorValueType`
derives from `SensorValueType` and declares `ValueRank = 1` (OneDimension).
Also a restriction of Any, also legal. And entirely independent of step 1: this
happens in the VariableType hierarchy, which knows nothing about `DeviceType`.

**Step 3 — a subtype narrows the declaration's type.** `ArrayDeviceType`
derives from `DeviceType` and re-declares `Reading`, narrowing its
TypeDefinition from `SensorValueType` to `ArraySensorValueType`. Narrowing an
inherited declaration to a subtype is precisely what subtyping is for. The
re-declaration even looks locally consistent — it carries `ValueRank = 1`,
matching its new nominal type.

```
   VariableType hierarchy                 ObjectType hierarchy

   BaseDataVariableType (-2)              DeviceType
            |                               |  Reading : SensorValueType, ValueRank -1
            v                               |
     SensorValueType (-2)  <----------------+
            |                               |
            v                               v  HasSubtype
   ArraySensorValueType (1) <----------- ArrayDeviceType
                                            Reading : ArraySensorValueType, ValueRank 1
```

**The result cannot exist.** `Reading` in `ArrayDeviceType` is bound by two
decisions at once:

- From the **ObjectType** chain: `DeviceType` already fixed it to Scalar, and a
  subtype may restrict an inherited declaration but never widen it. `-1` admits
  no further restriction, so it stays `-1`.
- From the **VariableType** chain: its TypeDefinition `ArraySensorValueType`
  fixes it to OneDimension.

Scalar and OneDimension are disjoint — no value is both. `ArrayDeviceType` is
therefore a type no server can instantiate, even though all three steps were
legal narrowings and no single node is malformed.

That last sentence is what makes this hard to catch. Run
[ontology validation](./ontology-validation.md) over the very nodeset and it
passes, because every node is individually correct:

```
python3 validate.py -m ontology -ni reading.owl.ttl
```

```
Validation Conforms: True
No validation errors found.
```

## How virtual typing finds it

The reason no per-node check can see this is that **`Reading` is not one
thing**. `DeviceType` has a `Reading` and `ArrayDeviceType` has a `Reading`;
they are different nodes that happen to share a BrowsePath, and the fact that
the second one *inherits the first one's restrictions* is a rule the reader is
expected to apply mentally. OPC UA has no name for "the `Reading` of
`ArrayDeviceType`" as an entity distinct from "the `Reading` of `DeviceType`".

`owl2vt.py` gives that concept a name. Walking each type's *Effective
Declaration Tree* — its own declared children plus everything inherited from
its supertype, with local overrides taking precedence — it mints one **Virtual
Type** class per (owning type, BrowsePath) pair, and writes the inheritance out
as `rdfs:subClassOf` edges:

```
VT(DeviceType, "Reading")       ⊑ SensorValueType
                                ⊑ ValueRank_Scalar          (step 1)

VT(ArrayDeviceType, "Reading")  ⊑ ArraySensorValueType
                                ⊑ ValueRank_OneDimension    (steps 2 + 3)
                                ⊑ VT(DeviceType, "Reading")  ← the inheritance
```

That last edge is the whole trick. It turns "a subtype inherits the base type's
restrictions", which a human applies by reading, into a subclass edge a
reasoner applies mechanically. Once both parents sit on one named class, the
conflict stops being an argument about specification prose and becomes a plain
subsumption question:

`VT(ArrayDeviceType,"Reading")` is below both `ValueRank_OneDimension` and —
through the inherited Virtual Type — `ValueRank_Scalar`. Those two classes are
declared disjoint, and `sb:hasValueRank` is a Functional property, so the class
has no possible members. And because `ArrayDeviceType` requires at least one
`Reading` of that class (`owl:minQualifiedCardinality 1`), `ArrayDeviceType` is
empty too.

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

[`ReadingContradiction.NodeSet2.xml`](./files/ReadingContradiction.NodeSet2.xml)
declares exactly the three steps above, and nothing else.

## Step 1: Convert the nodeset to OWL

```
python3 nodeset2owl.py docs/files/ReadingContradiction.NodeSet2.xml \
    -i ${BASE_ONTOLOGY} core.owl.ttl \
    -b ${BASE_ONTOLOGY_NS} -burl ${BASE_ONTOLOGY} \
    -v http://example.com/v0.1/reading/ -p reading -o reading.owl.ttl
```

## Step 2: Derive the Virtual Types

```
python3 owl2vt.py reading.owl.ttl -o reading.vt.owl.ttl
```

```
Parsing reading.owl.ttl ...
Resolving imports: ['https://industryfusion.github.io/contexts/staging/ontology/v0.3/base.ttl', 'file:///.../core.owl.ttl']
...
No --roots given: generating Virtual Types for all 4 ObjectType/VariableType classes this file itself declares (not its imports).
Building Virtual Types and restrictions ...
Writing 347 triples to reading.vt.owl.ttl (4.3s elapsed) ...
Done in 4.3s.
```

`owl2vt.py` only derives Virtual Types for the types the input file *itself*
declares — four here. The hundreds of types in `core.owl.ttl` are not
re-derived; the output `owl:imports` `core.vt.owl.ttl` instead. On a large
companion specification, use `--roots` to scope the run to a few named types
for a faster first look.

## Step 3: Run the reasoner

```
python3 validate.py -m vt reading.vt.owl.ttl
```

```
Validation Conforms: False

=== HermiT DL Consistency Report ===
2 unsatisfiable class(es) in reading.vt.owl.ttl:
  http://example.org/reading/ArrayDeviceType
  http://example.org/reading/VT_846c36be7db6a6dc097e57c0
```

`validate.py` exits with status `1`, so this works in CI.

An **unsatisfiable class** is one the reasoner has proven equivalent to
`owl:Nothing`: it can have no members, ever. `ArrayDeviceType` is unsatisfiable
— that ObjectType cannot be instantiated by any server — and the Virtual Type
alongside it says *which member* made it so.

## Step 4: Read the report

`VT_846c36be7db6a6dc097e57c0` is a generated Virtual Type. The name is a
sha256 digest of `"<owning type IRI>|<BrowsePath>"`, truncated to 24 hex
characters, so it is stable and reproducible: the same model always yields the
same name. Two ways to find out what it stands for.

**Look it up in the generated file.** Every Virtual Type carries the BrowsePath
it was minted for:

```
grep -A 16 "VT_846c36be7db6a6dc097e57c0> a owl:Class" reading.vt.owl.ttl
```

```turtle
<http://example.org/reading/VT_846c36be7db6a6dc097e57c0> a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ;
            owl:onProperty sb:hasValueRank ;
            owl:someValuesFrom opcua:ValueRank_OneDimension ],
        ...
        [ a owl:Restriction ;
            owl:allValuesFrom opcua:ValueRank_OneDimension ;
            owl:onProperty sb:hasValueRank ],
        <http://example.org/reading/ArraySensorValueType>,
        <http://example.org/reading/VT_6d34dd87e3a197bac52a918e> ;
    sb:originalBrowsePath "http://example.org/reading/Reading" .
```

**Or recompute the digest** for a (type, BrowsePath) pair you suspect:

```
python3 -c "import hashlib; print(hashlib.sha256('http://example.org/reading/ArrayDeviceType|http://example.org/reading/Reading'.encode()).hexdigest()[:24])"
```

```
846c36be7db6a6dc097e57c0
```

So the flagged class is *`ArrayDeviceType`'s `Reading`*, it is below
`ValueRank_OneDimension`, and it is below `VT_6d34dd87e3a197bac52a918e` — which
the same lookup identifies as *`DeviceType`'s `Reading`*:

```turtle
<http://example.org/reading/VT_6d34dd87e3a197bac52a918e> a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ;
            owl:allValuesFrom opcua:ValueRank_Scalar ;
            owl:onProperty sb:hasValueRank ],
        ...
        <http://example.org/reading/SensorValueType> ;
    sb:originalBrowsePath "http://example.org/reading/Reading" .
```

`ValueRank_Scalar` on one side, `ValueRank_OneDimension` on the other, and
`sb:hasValueRank` is Functional — one value cannot be both. That is the
contradiction from the first section, restated in the form the reasoner
actually consumed.

The rule of thumb when reading these reports: **the Virtual Types tell you
*where*, the real types tell you *what*.** Take the `sb:originalBrowsePath` of
each flagged `VT_...` class to locate the offending BrowseName, then look at
which real types it ended up beneath.

## Other kinds of contradiction

The same mechanism catches conflicts along every axis an OPC UA declaration
has. Each has its own end-to-end fixture under `tests/owl2vt/`, worth reading
as further worked examples:

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
python3 check_consistency.py core.vt.owl.ttl reading.vt.owl.ttl
```

```
core.vt.owl.ttl                OK  consistent  (33340 triples, 2.7s)
reading.vt.owl.ttl             FAIL  2 unsatisfiable class(es)  (33662 triples, 2.1s)
    http://example.org/reading/ArrayDeviceType
    http://example.org/reading/VT_846c36be7db6a6dc097e57c0

1/2 ontologies consistent.
Ontologies with issues: reading.vt.owl.ttl
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
python3 validate.py -m vt reading.owl.ttl
```

fails with

```
ValueError: .../reading.owl.ttl looks like a semantic-bridge ttl (it has base:definesType triples),
not a generated Virtual-Types ontology. ... Pass its Virtual-Types sibling instead (reading.vt.owl.ttl);
if it does not exist yet, build it first with 'make -f translate_default_nodesets.make' or
'python3 owl2vt.py reading.owl.ttl'.
```

The check is deliberate. A semantic-bridge file has none of the Virtual Type
classes and restrictions the reasoner needs, so without this guard it would
report a meaningless "consistent" verdict while validating nothing.

**A missing `*.vt.owl.ttl` dependency.** Your generated file `owl:imports` the
Virtual-Types file of every specification it depends on, by absolute `file://`
URL, and `check_consistency.py` follows those imports and loads them. If one
was never built you get a bare `FileNotFoundError` naming it:

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
