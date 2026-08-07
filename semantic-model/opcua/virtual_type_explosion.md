# Virtual Type Accounting in the Semantic Bridge → OWL Transformation

*A worked example using `TMCStateMachineType`*

> **Correction (this revision):** an earlier version of this document was
> titled "Type Explosion" and argued that Virtual Type counts vastly exceed
> Instance Declaration counts. That comparison was wrong: it compared
> Virtual Types (which are computed recursively, at every nesting depth)
> against `count_own_instance_declarations()`'s original count, which only
> ever looked at a type's own *direct* children — one level of nesting.
> Counted correctly (recursively, matching what Virtual Type generation
> actually processes), Virtual Type count is **provably bounded by, and in
> practice well below**, the true Instance Declaration count across the
> whole corpus (0.4×, see §5). There is no explosion. What survives from the
> original document, and is still worth understanding, is *why the same
> BrowseName can legitimately need several different classes* — that part is
> real and explained below.

## 1. The mismatch that forces Virtual Types to exist at all

OPC UA lets a Type nest **Instance Declarations** inside itself: a Component
or Property that is itself typed, itself governed by a ModellingRule
(Mandatory / Optional / Placeholder), and that may itself nest further
Instance Declarations, arbitrarily deep. A single ObjectType can encode an
entire state diagram this way — named states, named transitions, named guard
conditions — just by nesting Components inside Components.

OWL has no equivalent primitive. It has classes, `rdfs:subClassOf`, object
properties, and restrictions (`allValuesFrom`, `minQualifiedCardinality`).
There is no "this class has a nested, independently-typed slot at BrowsePath
X" construct. So Part 14 of this transformation invents one: every Instance
Declaration whose own content is genuinely new — not just a bare, unchanged
reference to an already-known type — gets minted into a synthetic OWL class,
a **Virtual Type**, so it can carry its own `rdfs:subClassOf` and its own
restrictions the way OPC UA's nesting implicitly does.

This is a real mechanism with a real cost in class count — but as §5 shows,
that cost stays at or below the number of declarations it represents. The
interesting part isn't *how many* classes get created; it's *why the same
BrowseName sometimes needs more than one*.

## 2. Meet `TMCStateMachineType`

This is a real, named `ObjectType` in the TMC companion spec — a PackML-based
state machine. Its own declaration tree, as it actually appears in
`tmc.ttl`, looks like this (ModellingRule shown in parentheses):

```
TMCStateMachineType                                          (real ObjectType)
│
├─ Aborting               : StateType                         (Optional)
├─ Aborted                : StateType                         (Optional)
├─ Cleared                : StateType                         (Optional)
│
├─ AbortingToAborted      : TransitionType                    (Optional)
│    └─ AbortingToAbortedGuard : BooleanGuardVariableType     (Mandatory)  DataType: LocalizedText
├─ AbortedToCleared       : TransitionType                    (Optional)
│    └─ AbortedToClearedGuard  : BooleanGuardVariableType     (Mandatory)  DataType: LocalizedText
├─ ClearedToAborting      : TransitionType                    (Optional)
│    └─ ClearedToAbortingGuard : BooleanGuardVariableType     (Mandatory)  DataType: LocalizedText
│
├─ AbortedSubstate        : StateMachineType                  (Optional)   ◄── a nested sub-machine
│    └─ CurrentState      : StateVariableType                 (Mandatory)  ◄── "CurrentState" #1
│
└─ MachineState           : TMCMachineStateMachineType         (Mandatory)  ◄── another nested sub-machine
     ├─ CurrentState       : FiniteStateVariableType            (Mandatory) ◄── "CurrentState" #2
     ├─ LastTransition     : FiniteTransitionVariableType        (Mandatory)
     ├─ StoppedSubstate    : StateMachineType                    (Optional)
     │    └─ CurrentState  : StateVariableType                  (Mandatory) ◄── "CurrentState" #3
     ├─ StoppingToStoppedGuard / RunningToStoppingGuard / ClearingToStoppedGuard
     │    : BooleanGuardVariableType                             (Mandatory, each)
     │
     └─ ExecuteState       : TMCExecuteStateMachineType           (Mandatory) ◄── yet another sub-machine
          ├─ CurrentState      : FiniteStateVariableType          (Mandatory) ◄── "CurrentState" #4
          ├─ LastTransition    : FiniteTransitionVariableType
          ├─ IdleSubstate      : StateMachineType
          │    └─ CurrentState : StateVariableType               (Mandatory) ◄── "CurrentState" #5
          ├─ ExecuteSubstate   : StateMachineType
          │    └─ CurrentState : StateVariableType                (Mandatory) ◄── "CurrentState" #6
          ├─ CompleteSubstate  : StateMachineType
          │    └─ CurrentState : StateVariableType                (Mandatory) ◄── "CurrentState" #7
          └─ … further transition guards (StartingToExecuteGuard,
               ExecuteToCompletingGuard, IdleToStartingGuard, …)
               each its own BooleanGuardVariableType slot
```

This is one real `ObjectType`. Every arrow in that tree is a Component or
Property that OPC UA lets you nest for free. In OWL, every arrow that
carries real content needs to become something — but note this is also,
itself, the full accounting of Instance Declarations this type introduces:
every node in this diagram, at every depth, is one Instance Declaration.
Comparing Virtual Type count only against the *top-level* arrows (12 of
them) while counting classes from the *whole* tree is exactly the mistake
this revision corrects.

## 3. What OWL forces us to write instead

Take just the `MachineState` branch. In OPC UA this is one line: "MachineState
: TMCMachineStateMachineType (Mandatory)". In OWL it has to become a synthetic
class carrying *every one of its own children's restrictions*, because OWL
classes are the only thing that can carry `rdfs:subClassOf`/restriction axioms
— there's no way to attach a restriction to "a nested slot":

```turtle
# VT(TMCStateMachineType, "MachineState") -- shown with a readable alias;
# the real IRI is a stable content hash, e.g. tmc:VT_92cab66a9db7cc39741b9728

VT(…,"MachineState")
    rdfs:subClassOf tmc:TMCMachineStateMachineType ;   # §8: nominal type
    rdfs:subClassOf packml:VT(…,"MachineState") ;      # §9: PackML's own
                                                        #     version of this
                                                        #     slot (inheritance
                                                        #     dimension)
    rdfs:subClassOf [ a owl:Restriction ;
        owl:onProperty tmc:hasCurrentState ;
        owl:allValuesFrom VT(…,"MachineState/CurrentState") ] ,
    [ a owl:Restriction ;
        owl:onProperty tmc:hasCurrentState ;
        owl:minQualifiedCardinality 1 ;
        owl:onClass VT(…,"MachineState/CurrentState") ] ,
    [ a owl:Restriction ;
        owl:onProperty tmc:hasLastTransition ;
        owl:allValuesFrom VT(…,"MachineState/LastTransition") ] ,
    [ a owl:Restriction ;
        owl:onProperty tmc:hasExecuteState ;
        owl:allValuesFrom VT(…,"MachineState/ExecuteState") ] ,
    … # one pair of restrictions per child in the tree above
```

And `VT(…,"MachineState/ExecuteState")` needs the *same* treatment for its own
24 children. This is the mechanism in full: **one class per tree node that
has something of its own to say**, because OWL has nothing lighter-weight to
offer — but "one class per node" is exactly 1:1 with the tree, not a
multiplier on it.

## 4. Why "CurrentState" needs seven classes, not one

Notice the tree in §2: the BrowseName `CurrentState` appears **seven separate
times** — once directly under `AbortedSubstate`, once under `MachineState`
itself, and once under each of `MachineState`'s four further nested
sub-machines (`StoppedSubstate`, `IdleSubstate`, `ExecuteSubstate`,
`CompleteSubstate`).

In OPC UA this is unremarkable: `CurrentState` is just the conventional name
every state machine's "what state am I in" Variable gets, and a BrowsePath
(`MachineState/ExecuteState/IdleSubstate/CurrentState`) disambiguates which
one you mean.

OWL classes have no BrowsePath — they have a global identity. There is no
single `owl:Class` that can mean "CurrentState, but only when reached via
this particular position in this particular tree" and simultaneously *not*
mean the same thing at a different position — different positions can
legitimately require different things (a different Datatype, a different
ValueRank, or in this tree, genuinely different declared types:
`StateVariableType` in some places, `FiniteStateVariableType` in others).
So each position gets its own class:

```
VT(…,"AbortedSubstate/CurrentState")                : StateVariableType
VT(…,"MachineState/CurrentState")                   : FiniteStateVariableType
VT(…,"MachineState/StoppedSubstate/CurrentState")   : StateVariableType
VT(…,"MachineState/ExecuteState/CurrentState")      : FiniteStateVariableType
VT(…,"MachineState/ExecuteState/IdleSubstate/CurrentState")     : StateVariableType
VT(…,"MachineState/ExecuteState/ExecuteSubstate/CurrentState")  : StateVariableType
VT(…,"MachineState/ExecuteState/CompleteSubstate/CurrentState"): StateVariableType
```

Seven classes, one BrowseName — but also **seven Instance Declarations**,
one per position, each a physically distinct node in the original nodeset.
This is not seven copies of one thing; it's seven genuinely distinct
declarations that happen to share a name, each correctly getting its own
class. A minimal, hand-reviewable version of exactly this point is in
`tests/owl2virtualtypes/test_vt_distinct_owners.NodeSet2.xml`.

## 5. Counting it correctly

The original version of this document counted `TMCStateMachineType`'s "own"
declarations as 12 (its direct children only) against 53 Virtual Types, and
called that a 4.4× explosion. Counted recursively — every node in the §2
diagram, at every depth — `TMCStateMachineType` actually introduces **92**
Instance Declarations, against those same 53 Virtual Types:

```
TMCStateMachineType  (1 real, named ObjectType)
   92 Instance Declarations, at every nesting depth
        │
        ▼
   53 Virtual Types                                    (0.58×, not 4.4×)
```

Roughly 40% of the tree needs no new class at all — plain Object references
and pass-throughs that point directly at a real type or an already-minted
Virtual Type. Across the whole default corpus, with the same recursive
counting (strict definition -- see §6 for why "strict" matters here):

```
 real types declared . . . . . . .    877
 Instance Declarations, all depths .  19,455
 Virtual Types  . . . . . . . . . .   7,395    (8.4× per type, 0.4× per declaration)
```

Virtual Type count is below Instance Declaration count for every single file
in the corpus, with no exceptions -- see §6 for how that's now guaranteed by
construction rather than merely observed.

## 6. Declarations without a ModellingRule: one switch, both sides together

OPC UA also aggregates real structural content via HasComponent/HasProperty
with **no ModellingRule at all** — most commonly the named States and
Transitions inside a `StateMachineType`-derived type (e.g.
`ExclusiveLimitStateMachineType`'s `High`, `HighHigh`, `LowToLowLow`). These
aren't optional-or-mandatory in the usual sense — they're always present,
more like fixed enum members — so they aren't "Instance Declarations" by the
strict OPC UA sense of the term, yet they still carry real content and can
still need their own Virtual Type.

Earlier revisions of this tooling counted these two things inconsistently:
`OwlBuilder` always minted Virtual Types for them regardless, while the
"Instance Declaration" count excluded them by default — comparing a
numerator that includes them against a denominator that doesn't. That
mismatch is what produced occasional warnings ("Virtual Types exceeds
Instance Declarations") that weren't actually bugs.

Both `OwlBuilder` (`require_modelling_rule`) and
`count_own_instance_declarations` (`include_unruled`, its logical inverse)
now take the same parameter, and `virtual_type_stats.py`'s `--include-unruled`
flag drives both together, so the numerator and denominator always agree on
what "Instance Declaration" means:

- **Default** (strict): `require_modelling_rule=True` — `OwlBuilder` skips a
  ModellingRule-less declaration entirely (no Virtual Type, no restriction,
  nothing nested inside it visited either), and the count excludes it too.
  877 types / 19,455 declarations / **7,395** Virtual Types (§5).
- **`--include-unruled`** (broad): both process every declaration regardless
  of ModellingRule. 877 types / 20,452 declarations / **7,881** Virtual
  Types (0.39×).

Either way, Virtual Type count is now a provable upper bound on whichever
Instance Declaration count is active: every node the active definition
counts is processed by the same code path (`_merge_local`'s loop →
`_resolve_target` → `_mint_vt`, cached per `(owner, key)`, never re-minted),
so it can never produce more than one class. Verified with zero exceptions,
in both modes, across the full corpus. `virtual_type_stats.py` still prints
a warning if this is ever violated for a file — with both sides now
consistent, that warning means a genuine algorithm bug, not a legitimate
ModellingRule-less-children case.

## 7. Takeaway

> Virtual Type count is bounded by the number of Instance Declarations it
> represents, provided both are counted the same way: recursively, at every
> nesting depth, and (for a hard guarantee) including OPC UA's rare
> ModellingRule-less structural children as well as ModellingRule-governed
> ones. There is no explosion. What *is* true, and worth remembering, is
> that a BrowseName is a *position* in OPC UA's tree, not a *class identity*
> in OWL's: the same name can legitimately require several different
> classes, one per distinct position, because different positions can
> genuinely require different things. `TMCStateMachineType` needing 53
> classes for 92 declarations isn't redundancy — it's a faithful,
> sub-1:1 accounting of how much internal structure that one type actually
> declares.
