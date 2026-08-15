# Supported Features for the SHACL to Flink transformation

## Target Nodes

SHACL defines a mechanism to select the node which is validated. The following mechanisms are supported


<table>
<tr>
<th> Feature </th>
<th> Example </th>
<th> Implemented </th>
</tr>
<tr>
<td>

```turtle
sh:targetNode
```
</td>
<td>

```turtle
cutterTemperatureShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
</table>


## Constraint Components

<table>

<tr>
<th> Feature </th>
<th> Example </th>
<th> Implemented </th>
</tr>

<tr>
<td>

```turtle
sh:class
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasState ;
        sh:property [
            sh:class ontology:MachineState ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>

<tr>
<td>

```turtle
sh:datatype
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:datatype xsd:double ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:nodeKind
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:nodeKind sh:Literal ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minCount
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:minCount 1 ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxCount
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:maxCount 1 ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minExclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:minExclusive 20.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minInclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:minExclusive 20.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxExclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:maxExclusive 50.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxInclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:maxInclusive 50.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minLength
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:minLength 5 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxLength
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:maxLength 5 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:pattern
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:pattern "^1\\.\\d{4,5}" ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:in
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:in ("Hello" "World") ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:hasValue
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:hasValue "Hello World" ;
        ]
    ] .
```

The empty list `sh:hasValue ()` works too, and means the list must be empty.
It is one arm of every array-valued OPC UA variable, beside "a list of the
right datatype".

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:not
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:not
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:or
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:or (
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ]
        [
            sh:property [
                sh:path iffbase:hasTemperature2 ;
                sh:property [
                    sh:minInclusive 20.0 ;
                ]
            ]
        ]
    ) .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:and
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:and (
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ]
        [
            sh:property [
                sh:path iffbase:hasTemperature2 ;
                sh:property [
                    sh:minInclusive 20.0 ;
                ]
            ]
        ]
    ) .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:xone
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:xone (
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ]
        [
            sh:property [
                sh:path iffbase:hasTemperature2 ;
                sh:property [
                    sh:minInclusive 20.0 ;
                ]
            ]
        ]
    ) .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:sparql
```
</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:select """
        """
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:message
```
</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:sparql [
        sh:message "Cutter {?this} executing without executing filter {?filter}" ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:severity
```
</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:severity iffbase:severityCritical ] ;
        sh:path iffbase:hasAttribute ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
</table>

## Sparql based constraints

### Sparql Query

The following SPARQL features are supported

<table>
<tr>
<th> Feature </th>
<th> Example </th>
<th> Implemented </th>
</tr>
<tr>
<td>

```
Basic Graph Pattern (BGP)
```
</td>
<td>

```sparql
    ?this iffbase:hasFilter [ ngsi-ld:hasObject ?filter ] .
    ?this iffbase:hasState [ ngsi-ld:hasValue ?cstate ] .
    ?filter iffbase:hasState [ ngsi-ld:hasValue ?fstate ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```

OPTIONAL {}
(only single triple supported)
```
</td>
<td>

```sparql
OPTIONAL{ ?this iffbase:hasFilter [ ngsi-ld:hasObject ?filter ] }
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
BIND
```
</td>
<td>

```turtle
BIND("hello world") as ?value
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
BOUND
```
</td>
<td>

```turtle
BOUND(?value)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
IF
```
</td>
<td>

```turtle
IF(condition, true, false)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
FILTER
```
</td>
<td>

```turtle
FILTER (?cstate = ontology:executingState && ?fstate != ontology:executingState)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
ConditionalOrExpression
```
</td>
<td>

```turtle
?cstate = ontology:executingState || ?fstate != ontology:executingState
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
ConditionalAndExpression
```
</td>
<td>

```turtle
?cstate = ontology:executingState && ?fstate != ontology:executingState
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
RelationalExpression
(=, !=, <,>, <=, >=, IN, NOT IN)
```
</td>
<td>

```turtle
?x > 5 
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
JOIN
```
</td>
<td>

```sparql
{BGP}
{BGP}
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
NOT EXISTS
```
</td>
<td>

```turtle
    FILTER NOT EXISTS{
        BGP
    }

```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
DISTINCT
```
</td>
<td>

```turtle
SELECT DISTINCT ?value
    WHERE {}
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>

<tr>
<td>

```
Now
```
</td>
<td>

```turtle
NOW()
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
CAST
(xsd:integer, xsd:float, xsd:dateTime, xsd:string)
```
</td>
<td>

```turtle
xsd:integer(?value)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
Additive Expression
```
</td>
<td>

```turtle
?value1 + ?value2
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
UnaryNot
```
</td>
<td>

```turtle
!(?value)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
Multiplicative Expression
(*, /)
```
</td>
<td>

```turtle
?value1 * ?value2
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
</table>

## NGSI-LD value paths

A value shape's `sh:path` selects how the attribute's value is read. Four are
supported, and they are exactly the ones `create_ngsild_models` builds
attribute rows from:

| path | attribute type |
|---|---|
| `ngsi-ld:hasValue` | Property |
| `ngsi-ld:hasValueList` | ListProperty |
| `ngsi-ld:hasJSON` | JsonProperty |
| `ngsi-ld:hasObject` | Relationship |

**Any other `ngsi-ld:has*` path fails the build** -- currently
`hasLanguageMap` (LanguageProperty), `hasVocab` (VocabProperty) and
`hasObjectList` (ListRelationship).

The rejection is deliberate rather than incidental. The data pipeline builds no
attribute row for those, so such an attribute is not merely unchecked -- it is
absent. A `sh:minCount 1` over it reports *"Found 0"* for an attribute that is
present in the model, and any bound on it can never fire. Failing the build is
the only behaviour that does not misinform.

Supporting them means deciding what their value *is* for comparison -- a
language map is not a scalar -- and adding them to both `attributes_query` and
`VALUE_PATH_ATTRIBUTE_TYPES`. Until then the answer is an error, not a guess.

## sh:message

`sh:message` replaces the generated explanation in the alert's `text`. The
generated one names the attribute and the parameter that failed, which says
what the compiler checked rather than what the model got wrong:

```turtle
sh:property [ sh:path test:hasVariable ;
              sh:message "ValueRank constraint for valuerank=Scalar and datatype=double" ;
              sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:double ] ] .
```

It applies to the shape that carries it, and it is carried through `sh:node` —
the referenced shape's message describes the constraints being copied, so it
travels with them. This is where the OPC UA generator puts its messages.

A **circuit node inherits its members' message when they all agree**, which
matters more than it looks: for a shape like the OPC UA ValueRank the
connective is what fires, and the branches are only its inputs and are never
published on their own. Without that, the author's text would never reach an
alert. Members carrying *different* messages have no single explanation, so the
generated text stands.

The alert's `event` is unaffected — identity stays the stable
`<constraintComponent>(<path>)` regardless of wording, so changing a message
updates an alert rather than orphaning it and raising a new one.

> `sh:message` inside `sh:sparql` was already honoured; this is the same
> feature for property constraints, which ignored it.

## Attribute nesting depth

NGSI-LD attributes may carry sub-attributes. Constraints can target them, to
**two levels below the attribute**:

| shape | supported |
|---|---|
| `attribute` (e.g. `temperature`) | yes |
| `attribute -> sub-attribute` (e.g. `assembly -> torque`) | yes |
| `relationship -> sub-attribute` (e.g. `hasPart -> trust`) | yes |
| `attribute -> sub -> sub-sub` (e.g. `assembly -> torque -> bolt`) | yes |
| one level deeper still | **no** — fails the build |

A sub-attribute of a *relationship* works exactly like one of a property: the
parent is matched on `parentId`, so the parent's own type does not matter. This
is the usual NGSI-LD pattern of a relationship carrying metadata such as trust
or confidence.

**The limit is one number.** `MAX_SUBPROPERTY_DEPTH` in `lib/utils.py` sets it,
and both the `constraint_table` path columns (`propertyPath`,
`subpropertyPath`, `subpropertyPath2`, ...) and the chain of `attributes_view`
joins in the generated SQL are derived from it, so they cannot disagree. A
constraint declares its own depth by leaving the deeper path columns NULL:
`name = NULL` never matches, so its unused joins contribute nothing and the
values fall through to the deepest level that did match. That is what lets a
two-level and a three-level constraint sit on the same entity —
`tests/sql-tests/kms-constraints/test17` puts both there and checks each fires
only for its own violation.

It is a knob rather than a fact about SHACL, and it is deliberately not set
higher than a real model has needed: every level costs one more join of
`attributes_view`, and so one more join's worth of Flink state, for every
deployment. It was raised from 1 to 2 because the OPC UA generator emits
`hasC ==> hasE ==> hasValueList` chains.

> Until that change the chain was written out by hand for exactly two levels,
> which was the *only* reason a third was rejected — nothing about the
> semantics stopped there. Two of the OPC UA generator's outputs were
> uncompilable for want of one more join.

## Logical constraint components

`sh:and`, `sh:or`, `sh:not` and `sh:xone` are supported both **on a property
shape** (constraining the values of one path) and **on a node shape** (grouping
whole shapes, so each branch may constrain a different property):

```turtle
:CutterShape a sh:NodeShape ; sh:targetClass :Cutter ;
  sh:or ( [ sh:property [ sh:path :hasTemp   ; ... sh:maxInclusive 50 ] ]
          [ sh:property [ sh:path :hasCoolant ; ... sh:minCount 1     ] ] ) .
```

They are compiled into a boolean circuit (`constraint_table.operation` plus the
`constraint_combination_table` edge list) and evaluated one SQL statement per
circuit level, so nesting is not limited to one level.

**Connectives nest.** A connective may sit on a property shape, on a value
shape, or on both, and each one becomes its own circuit node with its own
operator:

```turtle
sh:property [ sh:path :hasRange ;
    sh:property [ sh:path ngsi-ld:hasValue ;
                  sh:xone ( [ sh:minInclusive 100 ] [ sh:maxInclusive 10 ] ) ] ] .
```

Levels are folded separately, so an inner connective never inherits the
operator of the one above it. That matters because only `sh:or` flattens:
`XONE(a, OR(b, c))` is not `XONE(a, b, c)`.

> Value-level connectives other than `sh:or` used to produce no constraint at
> all — the extractor descended only into `sh:or`, so the branches were never
> read. Truth tables for all four at the value level are pinned by
> `tests/sql-tests/kms-constraints/test14`.

**Recursive shapes are rejected at build time.** A cycle has no finite circuit,
and Flink SQL has no fixpoint with which to evaluate one.

**`sh:node` references are resolved into the referring shape.** A named shape
may be written once and pointed at from many properties — the form the OPC UA
generator emits for its ValueRank constraints:

```turtle
sh:property [ sh:path test:hasVariable ; sh:maxCount 1 ;
              sh:node shacl:ValueRankShape_Any_double ] .

shacl:ValueRankShape_Any_double a sh:NodeShape ;
    sh:or ( [ sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:double ] ]
            [ sh:property [ sh:path ngsi-ld:hasValueList ; ... ] ] ) .
```

The referenced shape's constraints are copied onto the referring node before
extraction, so writing them behind a reference and writing them inline compile
to the same thing. That equivalence is pinned by
`tests/sql-tests/kms-constraints/test16`, which runs test15's models against
the `sh:node` form of test15's shape and expects test15's results; the two
compile to byte-identical SQL.

Each reference gets its own copy, and the referenced shape is dropped once
resolved unless it carries targets of its own. Both matter: sharing the blank
nodes gives two properties one set of clause nodes, and a shape left behind
still answers graph-wide queries — which reparented a `hasValueList` count to
the top level, where it fired on every valid scalar.

Three cases are refused rather than merged, because each would silently weaken
the constraint: a reference cycle; a referenced shape carrying a connective
when the referring shape already has one (two `sh:or` lists on one node read as
a single wider `sh:or`, turning an AND of disjunctions into one disjunction);
and a parameter set to different values on both.

**Constraint parameters may be written beside a connective.** They are
conjoined with it, not made part of it:

```turtle
sh:property [ sh:path :hasRange ;
              sh:minCount 1 ;          # must be present ...
              sh:xone ( ... ) ] .      # ... AND satisfy exactly one branch
```

The parameters compile to their own published constraint, so violating either
them or the connective raises an alert, and the connective keeps exactly the
arity the shape declared. This holds uniformly for `sh:or`, `sh:and`, `sh:xone`
and `sh:not`.

> Earlier versions ran the shapes through a normalisation pass
> (`shacl_normalization.py`) before extraction. It distributed the parameters
> into each `sh:or` branch — valid, since `(A ∨ B) ∧ C ≡ (A ∧ C) ∨ (B ∧ C)` —
> but for the other connectives that rewrite is invalid, and the parameters
> were instead dropped outright, or absorbed as an extra *member* of the
> connective, turning `XONE(a, b)` into `XONE(a, b, minCount)`. Both failed
> open. **Shapes are now read as written and that pass no longer exists**; see
> "Shapes are not rewritten" below. Pinned by
> `tests/test_connective_parameters.py` and by the `sh:minCount` beside
> `sh:xone` in `tests/e2e-kms/shacl.ttl`.

## Unsupported shapes fail the build

A shape the compiler cannot translate is a build error, not a warning. The
build stops and names every problem it found at once:

```
ERROR: the following shapes cannot be compiled and would be silently unvalidated:
  - sh:xone inside the value shape of <https://uri.etsi.org/ngsi-ld/hasValue> is not
    supported. Only sh:or is descended into at the value level, ...
```

Two things are rejected today:

* a property path deeper than the sub-attribute limit (see the depth table
  above). This used to be a warning printed to stdout, which no build step read.
* a property shape that names an attribute and produces no constraint at all —
  usually a missing value shape, or parameters the compiler does not implement.

A shape whose constraint is attributed to a **sub-attribute** is not rejected:
`iff:assembly` carrying only `iff:torque` compiles to a constraint on `torque`,
and that counts.

This exists because the failure mode it replaces is undetectable from outside.
An uncompiled constraint produces no alert, and no alert is exactly what a
satisfied constraint produces — so a KMS could report conformant for years over
a shape that was never once evaluated. Every silent failure found in this
compiler had that shape.

## Shapes are not rewritten

The compiler reads the SHACL you wrote. There is no normalisation step, no
intermediate `shacl_normalized.ttl`, and no generated shape in between.

That pass existed for a mechanical reason rather than a semantic one: the
extraction queries could only reach a constraint *through* a connective, so a
plain property shape had to be wrapped in a singleton `sh:or` before anything
would match it. The queries now treat the connective step as optional — the
clause is either a branch of a connective or, when there is none, the property
node itself — and the boolean circuit does all the combining.

This matters beyond tidiness. Every rewrite was an opportunity to change
meaning silently, and each of the connective bugs above was introduced by one.
It also means an alert now refers to a shape that appears in your file.

**One rewrite remains: `sh:node` resolution.** It differs from normalisation in
what it is allowed to do. Normalisation redistributed constraints across a
connective and had to reason about whether the result meant the same thing —
which for three of the four operators it did not. Resolving `sh:node` moves
nothing: it replaces a reference with what the reference points at, and refuses
every case where the copy would have to be merged with something already there.
The claim that it changes no meaning is checked rather than argued —
`test16` compiles to byte-identical SQL to the inline `test15`.

### Construct
TBD