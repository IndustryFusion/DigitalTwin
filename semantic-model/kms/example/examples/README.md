# Examples

Executable specifications for the shapes in `../shacl.ttl`. `semforge test ..`
runs them.

```
subobjects/                    the pieces cases are assembled from
test_StateOnCutterShape/
├── good/
│   ├── expectations.yaml      declares the cases in THIS directory
│   └── filter-on.jsonld
└── bad/
    ├── expectations.yaml
    └── filter-off.jsonld
```

## One expectations file per directory

A central list means every new case edits one shared file, so two people adding
a test to different shapes collide over it. Declaring a case next to itself
makes a suite something you can add, move or delete on its own — and a case's
`path` is relative to the file declaring it, so renaming a suite touches
nothing inside it.

Includes stay relative to `examples/`, because a subobject is shared and does
not belong to the suite that happens to use it.

## Naming is free

`test_<Shape>` reads well and nothing depends on it. A **suite** is a directory
holding `good/` and `bad/`; the suite is whatever sits above them, called
whatever you like.

A directory with **no** `good/` or `bad/` works too: its cases are assumed to
conform. That is the weaker position and worth naming — a suite with no bad
case cannot tell a constraint that is *satisfied* from one that could never
fire. `semforge test --coverage` is what reports the difference.

## Folders group, they do not decide

A file under `bad/` that asserts nothing is an unfinished test, not a passing
one. What a case means comes from `expect` and `asserts`, never from where it
sits — the manifest's §4.7 requirement, and why the runner reads the yaml
rather than the directory listing.

## Why subobjects

"A cutter running while its filter is off" needs a filter, a cartridge and a
workpiece before it is a well-formed entity at all. Repeating those in every
case makes the difference between two cases hard to see and easy to get wrong:
`test_StateOnCutterShape/good/filter-on` and `bad/filter-off` differ in exactly
one included file, which is the whole point of the pair.

Includes merge **before** the case, so the case wins where both describe the
same entity. That is what lets the bad one swap in a filter that is OFF.

## What these cover

Before they existed, every constraint was `no-firing-example`: nothing proved
any of them could fire, and a constraint that cannot fire looks exactly like
one that is satisfied. Five are now two-sided — proven able to fire *and*
proven not to fire spuriously:

| constraint | fired by |
|---|---|
| `StateOnCutterShape` | `test_StateOnCutterShape/bad/filter-off` |
| `CartridgeShape/hasCartridge` maxCount | `test_CartridgeShape/bad/shared-by-two-filters` |
| `FilterShape/hasCartridge` minCount | `test_FilterShape/bad/without-cartridge` |
| `WorkpieceShape/hasHeight` maxInclusive | `test_WorkpieceShape/bad/too-high` |
| `MachineShape/hasXXXWorkpiece` minCount | the shipped model |

The cartridge one is worth singling out: the exclusivity rule arrived with the
inverse-path work and **nothing exercised it** until
`bad/shared-by-two-filters` existed.

The other 67 are still `no-firing-example`, which `--coverage` lists.
