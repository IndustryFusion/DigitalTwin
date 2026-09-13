# SemForge for VS Code

Semantic modelling feedback while you edit: validation, coverage and
cross-artifact navigation over a SemForge package.

The extension itself decides nothing. It starts the SDK's language server and
renders what it sends, so the editor, the CLI and CI always agree — which is the
whole point of `architecture.md` §8.4.

---

## Getting started

**Once, ever:**

```bash
cd semantic-model/SemForge-SDK && make setup
```

That builds the venv and installs `semforge` into it. The extension finds it on
its own — it searches upward from whatever folder you opened.

**Then, every time:** open a folder in VS Code and click the SemForge icon in
the activity bar. Nothing else. No flags, no launch configuration, no terminal.

**Starting a new one?** There is a **SemForge** menu in each view's title bar
and on any folder in the Explorer (right-click ▸ SemForge):

| | does |
|---|---|
| **New project…** | makes a *folder* and scaffolds it, then offers to open it, open it in a new window, or add it to this workspace — the classical File ▸ New Project |
| **Create a package in this folder** | scaffolds the folder you already have |
| **Doctor** | what the extension sees and which server answers |

On the command line: `semforge new "Plant Line"` creates `./plant-line`;
`semforge init <path>` scaffolds a directory you already have. Same scaffold
either way. An empty view also shows the buttons directly. It writes a package
that already works —
knowledge with one entity type and one vocabulary, shapes in the NGSI-LD
two-layer encoding, a scratchpad instance, and an example on *each side* of one
constraint so the suite proves the constraint can fire as well as be satisfied.
It refuses to write into a directory that already holds artifacts.

```bash
code semantic-model/kms        # or the repo root, or anything between
```

### If the trees are empty

Run **`SemForge: Doctor`** from the Command Palette (`Ctrl+Shift+P`). It prints
the folder it sees, the package it found, the interpreter it picked and where it
came from, whether that interpreter can import `semforge`, **which directory the
running server's code comes from and which methods it answers**, and the exact
command to fix it. Start there rather than in the output channel.

That second-to-last line matters more than it looks. The extension and the
server are shipped separately — the `.vsix` is JavaScript, the server runs from
your venv — so a server older than the extension shows every new icon and
answers none of them: the click does nothing, with no error and nothing in the
log. The doctor now says `This server is OLDER than the extension` and names the
missing methods. The fix is **`SemForge: Restart Language Server`** or a window
reload.

The usual answer is that `make setup` has not been run, or was run before
`semforge` became installable — in which case run it again and reload the
window.

### What counts as a package

Any directory holding `knowledge.ttl`, `shacl.ttl` and `model-instance.jsonld`
— **or a directory in place of any of them**: `shacl/` of `.ttl` files,
`knowledge/` of `.ttl` files, `model-instance/` of `.jsonld` files. The graph is
the union; an edit lands in the document that declares the thing being edited,
and the shape jump names that file. A file wins if both are present.

The data can also be grouped under **`model/`**, with the scratchpad and the
suite at the same level:

```text
model/
├── model-instance.jsonld   (or model-instance/, or bare *.jsonld)
└── examples/
```

The trees look identical either way.
`semantic-model/kms` is one. Open the package itself or the folder above it —
the trees look in each workspace folder and one level below it, so opening
`semantic-model/` finds `kms/`. Open higher than that and they wait until you
open a file inside a package.

**If a tree is empty it now says why** in the panel itself: no package found (and
what it looked for), the server not running, or whatever the server reported.
An empty panel with no message was indistinguishable from a broken extension,
which cost a day.

If you keep your interpreter somewhere the search will not find, set
`semforge.pythonPath`.

---

## Working on the extension itself

Only needed if you are changing the extension's own code:

```bash
cd semantic-model/SemForge-SDK/vscode
npm install
code --extensionDevelopmentPath="$PWD" ../../kms   # or press F5 in this folder
```

Packaging and installing it instead:

```bash
npx @vscode/vsce package
code --install-extension semforge-0.1.0.vsix --force
```

Remember that VS Code loads extension JavaScript at window startup, so a change
there needs **`Developer: Reload Window`** — `SemForge: Restart Language Server`
only restarts the Python process.

---

## What you get

Open `shacl.ttl` in a package and the shapes are annotated in place.

**Errors** — things that would break, marked on the shape that causes them:

- *capability*: a shape the target profile cannot compile. Compiled to nothing,
  it would produce no alert — and no alert is exactly what a satisfied
  constraint produces, so this must never be discovered later.
- *view*: a shape that aggregates while reading the `current` data view, where
  each attribute has already been resolved to its latest instance. The aggregate
  would run over one observation where several were meant and return a
  plausible wrong number.

**Warnings** — *fires*: this shape currently raises violations, listing which
constraint on which entity.

**Information** — *unexercised*: no example makes these constraints fire.

That last one is the one worth having an editor for. A constraint whose
condition can never match produces exactly what a satisfied constraint
produces, so a green test run cannot tell "correct" from "dead". The only
available signal is that no example has ever made it fire. A real instance of
this sat in the KMS for months: `StateOnFilterShape` asked for
`?pc a Plasmacutter` where the instances are typed `Cutter`, and every test
stayed green.

**Hover** a shape name for its provenance — where it came from, its tier, and
the file and line that declares it.

**Go to definition** (`F12`) on a property in `sh:path` jumps from `shacl.ttl`
to the `owl:ObjectProperty` in `knowledge.ttl` that declares it. Nothing else in
the toolchain can follow that link: the two files are related only through the
graph.

**One click shows the row and leaves it open.** Selecting a row moves the file
to it *and* unfolds it. A click on a collapsible row toggles it, so the reveal
that showed you an entity also folded it shut — you had to click twice to see
what one click was supposed to show. The chevron still folds it.

**Selecting anything moves the `.ttl` to it.** Every node carries its own
`file:line` — an attribute, a single `sh:minCount`, not just the shape — so the
editor lands on the line you picked rather than the top of the block. Focus
stays in the tree, so you can arrow through a shape and watch the file follow.

**Outline** lists every shape in the file.

> Both halves of a click are ordered deliberately: the tree unfolds or reveals
> first, the editor moves second. Opening a file can refresh a tree, and a
> refresh makes VS Code drop the handles it uses to find nodes — a reveal after
> that silently resolves nothing. For the same reason a tree no longer refreshes
> when you open a file in the package it is already showing: that was a full
> re-validation per click, and the refresh was what broke the reveal.

---

## Install

### 1. The SDK

```bash
cd semantic-model/SemForge-SDK
make setup          # creates venv/ and installs pinned dependencies
make test           # optional: 142 tests should pass
```

The extension finds `venv/bin/python` on its own. If you keep your interpreter
elsewhere, set `semforge.pythonPath` in VS Code settings.

### 2. The extension

```bash
cd semantic-model/SemForge-SDK/vscode
npm install
```

Then pick one of three ways to run it.

**A. One command, no F5.** The most reliable, because it depends on nothing in
your VS Code setup:

```bash
cd semantic-model/SemForge-SDK/vscode
code --extensionDevelopmentPath="$PWD" ../..
```

A new window opens with the extension loaded and `semantic-model/` as its
folder. Open `kms/shacl.ttl` in it.

**B. F5 from the extension folder.**

1. Open **`semantic-model/SemForge-SDK/vscode`** as the VS Code window — the
   folder itself, not the repository root. `.vscode/launch.json` lives there and
   is what teaches F5 what to do.
2. Press `F5`, or pick **Run SemForge Extension** in the Run and Debug panel.
3. A second window opens on `semantic-model/`. Open `kms/shacl.ttl`.

> If F5 asks you to *select a debugger* or offers Node.js/Chrome, VS Code has
> not found `launch.json`. That means the open folder is not the `vscode/`
> directory — check the title bar. Use method **A**, which does not depend on
> it.

**C. Install a packaged build.**

```bash
npm install -g @vscode/vsce
vsce package                       # produces semforge-0.1.0.vsix
code --install-extension semforge-0.1.0.vsix
```

Installed this way it loads in every window, so open the repository normally.

### 3. What you should see

Open `semantic-model/kms/shacl.ttl`. The file itself looks no different — the
extension adds no syntax colouring beyond what VS Code already does for `.ttl`.
**Everything it contributes is in three places, and none of them is the editor
text by default:**

**Problems panel** — `Ctrl+Shift+M` (`Cmd+Shift+M` on macOS), or View → Problems.
This is the main thing. On the shipped KMS it should hold **11 entries**:

```
⚠  3 violation(s) here: MinCountConstraintComponent(hasXXXWorkpiece) on urn:filter:2 …   [160]
ⓘ  7 constraint(s) here have no example that makes them fire (hasCartridge/MaxCount…)    [14]
ⓘ  20 constraint(s) here have no example that makes them fire (hasFilter/ClassCons…)     [46]
…
```

**Squiggles in the file** — a yellow underline on line 160 (`:MachineShape`) and
faint blue ones on each other shape's first line. Hover one to read the message.
Clicking a Problems entry jumps to it.

**The SemForge view** — click the SemForge icon in the activity bar (left
edge). This is the cooked view: entity types, their attributes, and the
constraints on each.

```
Filter                            2 shape(s)
└── :FilterShape                  2 attribute(s)
    └── hasStrength
        ├── ✎ sh:maxCount   1
        ├── ✎ sh:minCount   1
        ├── ✎ sh:nodeKind   sh:BlankNode
        └── value                 hasValue
            ├── ✎ sh:maxInclusive  100.0
            ├── ✎ sh:minInclusive  0.0
            └── 🔒 or (raw only)   structure, not a parameter
```

A pencil means editable: click it and you get a picker of what the model
allows, or an input box where the value is free (a count, a bound, a pattern).

For `sh:class` the picker knows which half of the ontology applies, because the
two sides of the NGSI-LD encoding mean different things:

| slot | offers | because |
|---|---|---|
| `value → hasObject` | entity types — `Filter`, `Workpiece`, `Cutter` | a Relationship points at an entity |
| `value → hasValue` | vocabulary classes — `MachineState`, `Wasteclass`, `Material` | a Property with an IRI value points into the ontology |

Entity types are found by their root: the KMS declares `base_entities:Entity`
and everything else hangs beneath it. A package without such a root can declare
one as `entityRoot:` in `semforge.yaml`; a package with neither gets no
suggestions and is told why, rather than being offered every class in the file.

**The list is ranked, not alphabetical**, and each entry says why it is where it
is:

```
MachineState       vocabulary class · used by 1 shape(s) · 7 individual(s)
Wasteclass         vocabulary class · used by 1 shape(s) · 4 individual(s)
Material           vocabulary class · used by 1 shape(s) · 3 individual(s)
ChemicalElement    vocabulary class · 9 individual(s)
…
FieldType          vocabulary class · no individuals -- cannot be a value
```

Two signals do the ordering. A class already used as `sh:class` somewhere is a
proven value class rather than a guess. And a `sh:class` on a value says the
value IRI is an *individual* of that class, so a class with no individuals
cannot be the answer however plausible its name — those sink to the bottom and
say so. Alphabetically the KMS put `Binding`, `BoundConnector`, `BoundMap` and
`FieldType` ahead of the three you would actually pick.

**Typing narrows it.** For an ontology that fits, VS Code filters locally on the
name, the term and the detail. For one that does not, the server caps what it
sends and each keystroke asks it again — so a large ontology stays navigable
instead of arriving as a truncated list with no way to reach the rest. The
placeholder says which you are in (`showing 200 of 4,318; keep typing to
narrow`).

Every picker keeps **Enter a different value…** at the bottom. The suggestions
are a convenience, not a restriction — a list you cannot escape would make the
cooked view less capable than the file it edits.

The offered term is spelled for `shacl.ttl`, which matters more than it looks:
`knowledge.ttl` calls that namespace `default1:` while the shapes file calls it
`iffBaseKnowledge:`, and writing the wrong one would break the file on the next
parse.

The edit rewrites
**only that value** in `shacl.ttl` — changing `1` to `0` moves one byte and
leaves every comment in the file intact — then re-validates, so the Problems
panel follows immediately.

A **⇧ hierarchy icon** means the constraint is inherited: it is declared on a
supertype and applies here because `sh:targetClass` reaches subclasses. `Filter`
shows `MachineShape`'s `hasState` for that reason — the constraint was never
missing from Filter, only from the tree. Right-click offers **Go to Definition** and **Declare on This Type**.

**Go to Definition navigates both views**: it reveals and expands the declaring
shape in the tree *and* moves the `.ttl` to the line. Jumping only the editor
would leave you to find the declaring shape in the tree by hand, which is the
work the command exists to remove.

> **There is no override in SHACL.** A constraint declared on `Filter` is
> *conjoined* with the one on `Machine`, not substituted for it — adding
> `hasState minCount 0` to `FilterShape` leaves `MachineShape`'s `minCount 1`
> firing exactly as before. So the action can only tighten, and when the value
> you give would be weaker or identical it says so and offers to open the
> inherited shape instead. To genuinely relax, edit the shape that declares it.

`sh:nodeKind sh:BlankNode` is **not shown on an attribute**. In NGSI-LD an
attribute *is* a blank node carrying `hasValue`/`hasObject`, so stating it
decides nothing — `semforge export` adds it to every forward attribute path,
because a SHACL consumer knows nothing of that convention. Two places it stays
visible, because there it is a real decision: on a **value** (`sh:IRI` for a
relationship target, `sh:Literal` for a plain value), and wherever an attribute
declares something *other* than `BlankNode`, which is a modelling error rather
than boilerplate.

A padlock means shown but not editable here. Connectives (`sh:or`, `sh:node`)
are structure rather than a parameter, and a SPARQL body is not a form. They
appear so the tree does not lie about what the shape contains; edit them in the
`.ttl`.

**The Model view** — the second tree in the SemForge container. It shows the
data the constraints judge: every declared case, what it is for and whether it
did it, and the model instance as the scratchpad beside them.

The tree shows two different things, and they are not interchangeable. The
cases under `examples/` are the **suite**: each says what it is for and
`semforge test` passes or fails on it. `model-instance` is the **scratchpad** —
where you try a violation to see what a constraint does. It carries no
expectation and cannot fail a run, and each of its documents gets its own root
marked *a scratchpad, not a declared example*.

```
🧪 cutter-processing-with-filter-on.jsonld   good · valid · ok · 3 include(s)
   ├── urn:plasmacutter:1                    Plasmacutter
   └── 🔗 filter-on.jsonld                   included — edit it where it is declared
🧪 cutter-processing-with-filter-off.jsonld  bad · invalid · ok · 3 include(s)
   └── urn:plasmacutter:1                    Plasmacutter · 1 violation(s)   ⛔
🧪 model-instance.jsonld                     the model as shipped — not a declared example
```

A **bad** example that violates is `ok` — violating is its pass condition. One
that stops violating is the failure, which is the regression a negative example
exists to catch.

Entities arriving through `include` are editable where they appear, and the
write goes to the subobject. The tree says how many cases include that file and
the edit asks before changing more than one of them — a decision worth taking
deliberately, but not one worth forbidding.

Under each entity is the data itself, starting with its **type**:

```
model-instance.jsonld            8 entities
├── urn:cutter:1                 Machine · 1 violation(s)     ⛔
│   ├── type                     iffBaseEntities:Machine
│   └── hasState                 base:state_ON · Property     ✎
└── urn:filter:1                 Filter · 1 violation(s)      ⛔
    ├── type                     iffBaseEntities:Filter
    ├── hasCartridge             "urn:cartridge:1" · Relationship  ✎
    └── hasStrength              0.6 · Property · 4 observations   📈
        ├── 0.9   2024-02-28T13:52:32.000Z · superseded
        ├── 0.8   2024-02-28T13:52:33.000Z · superseded
        ├── 0.7   2024-02-28T13:52:34.000Z · superseded
        └── 0.6   2024-02-28T13:52:35.000Z · current
```

The type is also the entity row's description, but a description is grey and
truncated in a narrow panel — and the type is the most load-bearing field an
NGSI-LD entity has, since it decides which shapes judge it at all. So it gets a
row. It is read-only here: changing a type is not an edit to one value, because
every shape that targeted the old type stops applying.

**An id is not an address; the file is the rest of it.** The same
`urn:filter:1` appears in four files — "the filter, switched off" is written as a
second one, and each case is validated on its own — so every row that names an
entity shows its path, and nothing is flagged for the reuse. Hover an entity row
to see which file it was read from.

Three things *are* errors, reported on the `.jsonld` file and line and failing
`semforge test`:

| Case | Why |
|---|---|
| the same id twice in one file | one entity carrying the attributes of both, and no path can tell them apart |
| the same id in a case *and* one of its includes | the files are parsed into one graph, so the definitions **merge** — an include saying `hasState ON` and a case saying `OFF` produce an entity with both. There is no override; vary an entity by including a different subobject |
| an entity with no `@context` | `id` and `type` are ordinary keys until a context maps them, so it expands to a blank node, no `sh:targetClass` matches, and the case passes having validated nothing |
| a relationship pointing at an entity the case does not define | in a case the composition is the whole world, so nothing about the target gets checked and the case passes having tested less than it says. This is what a half-finished rename leaves behind: change an id in a subobject and the filters pointing at it go nowhere, while the verdict moves somewhere unrelated |

Those are the only diagnostics this extension puts anywhere but `shacl.ttl`.

**Instances are grouped by `datasetId`.** That is not cosmetic: an NGSI-LD
attribute is identified by `(entity, name, datasetId)`, so several instances
sharing one are the *same* attribute observed repeatedly, while different
`datasetId`s are *different* attributes that happen to share a name. The dedup
resolves within a `datasetId` and never across, and a flat list hides that.

With one `datasetId` the series hangs straight off the attribute. With several,
each gets its own row showing its own current value:

```
hasStrength                       2 datasets
├── 0.6    @none · Property · 4 observations        📈
└── 1.5    urn:sensor:B · Property · 2 observations 📈
```

**Anything carrying a value carries the pencil** — including the value of an
attribute with sub-attributes, which does not fold onto the attribute row: the
row beneath it is where the value lives. **Add Observation** appears only on a
row that stands for a `datasetId`, since that is what a series belongs to. The
only rows without a pencil are rows with no value of their own, and they say so
on hover.

**Rows from an included subobject are editable too.** They are ordinary JSON-LD
files and the edit lands in the file the row came from. What is worth knowing is
the reach: `workpiece-steel.jsonld` is included by three cases, so changing its
height moves three verdicts. Those rows say `shared by 3 cases` and the edit
asks once, listing them, before writing. A file only one case includes asks
nothing.

A row with the 📈 icon takes **Add Observation** (right-click). It asks for the
value and an `observedAt`, joins the series for *its* `datasetId`, and copies
the `type` from what is already there — a Property whose new instance arrived
as a Relationship would be a different attribute, not a new observation of the
same one. A `datasetId` of `@none` is not written out: that *is* the default
instance, and stating it would mean something else.

**Building NGSI-LD, legally.** Right-click an example for **Add Entity**, or an
entity for **Add Attribute**. An attribute is not free-form JSON — its `type`
decides which key carries the payload:

| type | key | payload |
|---|---|---|
| `Property` | `value` | a literal, or `{"@id": …}` for a vocabulary term |
| `Relationship` | `object` | an entity IRI, never a literal |
| `GeoProperty` | `value` | GeoJSON |
| `JsonProperty` | `json` | arbitrary JSON, opaque to the graph |
| `ListProperty` | `valueList` | an ordered list |

The type is read **from the shapes** by default — a value shape on
`ngsild:hasObject` means Relationship, one on `hasValue` means Property — so you
are not asked something the model already knows. A pairing that cannot mean
anything is refused rather than written: this repo has already lost time to
`{"object": …}` where the model said Property, which made a SPARQL rule's join
predicate refuse the row silently while every test stayed green.

Each attribute row carries a **⚖ icon: the SHACL rule for this attribute**. It
opens `shacl.ttl` at the `sh:property` block that judges this datum — including
when that block is on a supertype, which is where it is hardest to find by hand
(`hasState` on a `Filter` is `MachineShape`'s, and the status bar says so).
**If nothing constrains the attribute it offers to write an empty
`sh:property`** for it, so there is somewhere to add constraints. That stub
deliberately constrains nothing yet, and the capability check reports it as
compiling to nothing until you add a parameter — a property shape that asserts
nothing is a visible TODO, not a finished shape.

Editing a value **offers what the shape allows**. Where the value's shape
declares `sh:class`, the picker lists the individuals of that class — and for a
relationship, the entity ids of that type — spelled the way the file needs them
(`{"@id": "base:state_ON"}` for a Property with an IRI value, a bare IRI for a
Relationship). This is a different question from the `sh:class` picker in the
Constraints view: that one asks what the *constraint* may say, this one what the
*datum* may be. **Enter a different value…** stays at the bottom.

Otherwise the input parses JSON, so `42` is a number and
`{"@id": "…"}` a node reference — typing an IRI into a Property should not
quietly produce the string form. The file is rewritten with a one-line diff and
both trees re-validate, which is the reason to edit here rather than in the
JSON: you see the verdict move.

**`current` and `superseded` are worth knowing about.** An attribute resolves to
its latest `observedAt` per `datasetId` before validation, so editing a
superseded observation changes the file and nothing else. Without the marker
that reads as the editor being broken.

An entity that violates something is marked, and carries the message on hover —
a `minCount` violation is about an attribute that is *not there*, so there is no
attribute node to hang it on.

**The Knowledge view** — the third tree, and the third ingredient. Shapes say
what must hold, examples are what holds; neither says what the model *is*.

```
📚 Entity types                        9 type(s) under Entity
└── iffBaseEntities:Entity
    ├── iffBaseEntities:Consumable
    │   ├── iffBaseEntities:FilterCartridge  CartridgeShape + 4 more · 3 instance(s)
    │   └── iffBaseEntities:Workpiece        WorkpieceShape · 4 instance(s)
    └── iffBaseEntities:Machine              MachineShape · 1 instance(s)
        ├── iffBaseEntities:Cutter           CutterShape · 1 instance(s)
        │   ├── iffBaseEntities:Plasmacutter 3 instance(s) · checked by an inherited shape
        │   └── iffBaseEntities:Lasercutter  checked by an inherited shape
        └── iffBaseEntities:Filter           FilterShape + 2 more · 7 instance(s)
📚 Vocabulary classes                  14 class(es)
└── base:MachineState                  7 member(s) · used by 1 constraint(s)
    ├── state_ON          ON · used in 7 place(s)
    ├── state_OFF         OFF · used in 1 place(s)
    └── ⚠ state_CLEANING  CLEANING · unused
```

What it adds over reading `knowledge.ttl` is the **joins** — the places where
the three ingredients meet, which is where authoring goes wrong and where
nothing reports today:

| Row says | Meaning |
|---|---|
| `FilterShape + 2 more` | which shapes judge instances of this class. The ⚖ icon opens the shape |
| `checked by an inherited shape` | no shape of its own, but `sh:targetClass` reaches subclasses — `CutterShape` judges a `Plasmacutter` |
| ⚠ `no shape` | nothing targets this type or anything above it, so nothing about it is ever checked |
| `7 instance(s)` | how many examples instantiate it, counted across every suite — not only `model-instance.jsonld`. **Clicking one opens it and shows it in the Model tree** |
| `used in 7 place(s)` | an example gives this term as a value. Expand for which entity, attribute and file — **clicking one opens that file at that attribute and shows the entity in the Model tree** |
| ⚠ `unused` | no case gives this value, so nothing exercises the constraint that allows it |
| ⚠ `no members` | a shape uses this class as `sh:class` and it has no individuals: no value can ever satisfy it |

The flags are narrow on purpose. `unused` is shown only for a vocabulary some
shape actually draws values from — a `Binding` or a `ChemicalElement` is not
something an NGSI-LD example is meant to mention, and colouring those would
turn the tree yellow and bury the real gap. `no members` is likewise only for a
vocabulary class: an entity class under `sh:class` is the *range of a
relationship*, and its instances live in the data rather than in
`knowledge.ttl`. An abstract root — subclasses, no instances — is not expected
to have a shape of its own and is not flagged.

Selecting a class or a member moves `knowledge.ttl` to its declaration.

Selecting a row that names an entity — an **instance** ("this class is
instantiated here") or a **usage** ("this term is given as a value there") —
does both halves of showing it: the `.jsonld` opens at the entity, or at the
attribute that gives the term, and the entity's row is revealed in the Examples
tree, where its verdicts and its other attributes are. The same entity id appears in a good
case and a bad one, so each file gets its own row rather than one row guessing
which you meant.

**Output → SemForge** — pick "SemForge" in the dropdown of the Output panel.
This is where the server reports for itself, and the first place to look if the
Problems panel stays empty.

If you see none of that, the language server is not running — the table below
says why.

If nothing appears, open **Output → SemForge** in the dropdown for the server
log. The usual causes:

| Symptom | Cause |
|---|---|
| Problems panel empty, no SemForge output channel | the server exited at startup. Almost always `semforge` is not installed into the interpreter: run `make setup` again — it now does `pip install -e .`, which earlier versions did not |
| F5 offers a debugger list | the open folder is not `vscode/`; use method A |
| Output says `No module named semforge` | same as the first row: `cd semantic-model/SemForge-SDK && make setup` |
| Problems empty but the output channel exists | the file is not inside a package: its directory needs `knowledge.ttl`, `shacl.ttl` and `model-instance.jsonld` alongside it |
| Nothing after editing | analysis runs on open and on **save**, not on keystroke |

A language server that exits immediately is indistinguishable from one that
found nothing to report, which is why the first row is the first row.

---

## How it decides what to analyse

A *package* is any directory containing `knowledge.ttl`, `shacl.ttl` and
`model-instance.jsonld`. Opening any file inside one activates the service,
which walks up to find the root — an editor hands you a file, not a project.

Analysis runs on open and on save, over the whole package, because a constraint
in `shacl.ttl` is meaningless without the ontology and the examples.

---

## Commands

| Command | What it does |
|---|---|
| `SemForge: Restart Language Server` | after changing `semforge.pythonPath`, or if the server dies |
| `SemForge: Revalidate Package` | saves the active file, which re-runs analysis |
| `SemForge: New project…` | creates a project folder and scaffolds it, then offers to open it |
| `SemForge: Create a package in this folder` | scaffolds a directory you already have |
| `SemForge: Doctor` | what it sees: folder, interpreter, whether `semforge` imports |
| `SemForge: Go to the SHACL rule for this attribute` | the ⚖ icon on an example attribute; creates an empty `sh:property` when none exists |
| `SemForge: Go to the shape for this class` | the ⚖ icon on a knowledge class |

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `semforge.pythonPath` | `""` | Interpreter with `semforge` importable. Empty means look for `venv/bin/python`, then `python3`. |
| `semforge.trace.server` | `off` | LSP message tracing, for debugging the extension itself. |

---

## Limits worth knowing

- **Violations are attributed to the shape, not to the entity.** They land on
  `shacl.ttl`, against the constraint you are editing. Entity-identity findings
  are the exception and land on the `.jsonld` line, now that a JSON position
  index exists; mapping every violation back to its entity is still not done.
- **Cooked editing covers Core parameters only** — cardinality, datatype,
  class, nodeKind, ranges, lengths, pattern. That is deliberate rather than
  partial: those are the constraints that honestly fit one name and one scalar
  value. Connectives and SPARQL bodies are shown and locked.
- **Adding constraints is half-wired.** You can change and remove what a shape
  declares, and the ⚖ icon on an example attribute will create an *empty*
  `sh:property` for an unconstrained attribute — but filling it in is still a
  `.ttl` edit. There is no "add a parameter" command yet.
- **The Knowledge view is read-only.** It shows the ontology and the joins; a
  new class or member is a `knowledge.ttl` edit.
- **`instance(s)` and `used in` count the examples, not the world.** They say
  what the suite exercises. A term no case uses may still be perfectly valid —
  that is why those rows are flagged as warnings and only where a shape draws
  from them.
- **Analysis is whole-package on every save.** Fine at KMS scale (about a second);
  the incremental path exists in the plan and is not wired up.
