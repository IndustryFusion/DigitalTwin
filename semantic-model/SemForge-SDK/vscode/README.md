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

**Starting a new one?** Creating a project is a SemForge-level gesture, not a
constraint one, so it lives one layer above the artifact views: in the
**SemForge menu** on the status bar, in the **Package** view's title bar, and
on any folder in the Explorer (right-click ▸ SemForge):

| | does |
|---|---|
| **New project…** | makes a *folder* and scaffolds it, then offers to open it, open it in a new window, or add it to this workspace — the classical File ▸ New Project |
| **Create a package in this folder** | scaffolds the folder you already have |
| **Doctor** | what the extension sees and which server answers |
| **Delete project…** | moves the whole directory to the trash, after telling you what is in it |

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

### The five views

Each view is one way into the same package; its name says which, and the
package it shows stands beside it.

| View | Shows | From | A click opens |
|---|---|---|---|
| **Package** | the package itself: name, contexts, namespaces, contents, health | `semforge.yaml` | the package page, the row marked |
| **Entity Types & Constraints** | every entity type, inherited ones included, with what its shapes require of each attribute | the shapes, read per type | the type page, the attribute marked |
| **SHACL Shapes** | the shapes as written, one row per named shape and rule | the shapes files | the shape page |
| **Entities & Test Cases** | the Main model's entities, then the test suites and their cases | the model and `examples/` | the Main page or the case page, the entity marked |
| **Knowledge (Ontology)** | entity types, attributes, value lists (vocabularies), units | the knowledge files | the type or vocabulary page |

Every page has its file one click away — an **Open …** button or ⋯ entry —
but a click never lands in the file by itself.

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

### Which package am I on

The **status bar** says, bottom left: `📦 kms` — or `📦 kms/test`, because the
label is the path relative to the folder you opened and two directories called
`test` are not the same project. All the views show that one package; the
package is a property of the window, not of a view.

Clicking it opens the **SemForge menu**. VS Code gives an extension no way to
add a menu beside File and Edit — there is no contribution point for the menu
bar — so the status bar item is the one place everything hangs off, the same
answer the Python interpreter and the active Docker context use. Everything in
it is in the command palette under `SemForge:` as well.

| | |
|---|---|
| 📦 Switch package… | which package all the views show |
| ⚙ Project settings | name, contexts, namespaces — focuses the Package view |
| ✓ Revalidate | re-run analysis over the package |
| 📁 New project… / Create a package in this folder | scaffold — the level above the views, which is where a project belongs |
| ◎ Doctor · ⟳ Restart language server | when something is wrong |

**Switch package…** lists every package in the window — nested ones included,
which is where a scaffolded test project lives — and ends with **Follow the
active editor**:

* **following** (the default) — opening a file in another package moves all
  three views there. Right when you have one package.
* **pinned** (after you choose one) — the views stay put whatever you open.
  Right while you are reading a second package.

On the command line the same question is `semforge where`, and every command
that reads a package prints the one it resolved.

### Adding an entity

The **+** on a case or a model file asks for the type **first**, and offers
only what the knowledge declares — the entity hierarchy, each row saying which
shape will judge it and how many instances the model already has:

```text
Type — from the knowledge
  iffBaseEntities:Filter          judged by iffBaseShacl:FilterShape
                                  under iffBaseEntities:Machine · 2 in the model
  iffBaseEntities:Plasmacutter    judged by iffBaseShacl:CutterShape
                                  under iffBaseEntities:Cutter · 1 in the model
  ➕ New entity type…             declare it in the knowledge, then use it
```

There is no free-text box for the type, and that is the point: nothing rejects
an undeclared class, no shape targets it, so every constraint stays silent and
the entity reads as *validated*. A type that is genuinely missing is declared
first — the last entry writes the class into `knowledge.ttl` beneath a parent
you pick, opens the line it wrote, and then types the new entity with it.

The rule lives in the SDK, not in the extension: `add_entity` refuses a type
the knowledge does not declare, so no client can route around it.

Only the id is typed, and it is prefilled from the type (`urn:filter:3`).

### Adding a type or a subtype

A type does not need an entity to exist. **New entity type…** (the class icon
in the Entity Types & Constraints view's title bar, or the palette) asks for a name and its parent;
**New subtype…** (right-click a type in Entity Types & Constraints, or a type page's `⋯`)
asks only for the name — the parent is the type you started from. Every type
has a parent: a top-level one sits under the root of the hierarchy.

Both write two lines into `knowledge.ttl` and show them:

```turtle
iffBaseEntities:Watercutter a owl:Class ;
    rdfs:subClassOf iffBaseEntities:Cutter .
```

A subtype is judged by every shape of its ancestors already — SHACL class
targets include subclasses — so it appears under Types at once, with those
shapes marked *inherited*, and its type page lists what it inherits. What it
lacks is a shape of its own, so the message offers **Create its shape**
(then its attributes and constraints go on the shape page) or **Open its
type page**.

**+ Attribute** works on such a type anyway — on its type page and on its
row in Entity Types & Constraints. The attribute has to live in a shape of the type's own, so when
there is none yet the shape is written first (its name asked, prefilled with
e.g. `WatercutterShape`), and the attribute picker opens on it straight away.
Attributes a parent's shape already constrains are marked *inherited* there:
to make one stricter for the subtype, use **Override** on its row instead.

### Adding an attribute

Same rule, one level down. The **+** on an entity offers the attributes the
knowledge declares *for that type* — `rdfs:domain` is the join, and it is
inherited, so a Plasmacutter is offered what a Cutter and a Machine carry:

```text
Attribute for urn:plasmacutter:1 — from the knowledge
  iffBaseEntities:hasState     Property · constrained
                               carried by iffBaseEntities:Machine
  iffBaseEntities:hasFilter    Relationship · constrained
                               carried by iffBaseEntities:Cutter
  iffBaseEntities:hasTrust     Property · constrained
                               no domain declared — carried by anything
  ➕ New attribute…            declare it in the knowledge, then use it
```

Then the **value** is picked the same way, from what the attribute's shape
allows — `hasState` on anything descending from Machine takes an individual of
`base:MachineState`, so the states are listed rather than typed. The shape is
found by walking the entity type's ancestors, so a type you declared a minute
ago gets its parent's constraints. *Type a value* is always the last entry, for
anything the shape does not constrain.

An attribute spelled wrong is not a broken document — it is an **invisible**
one. No `sh:path` selects it, so the constraint that should have judged the
value never fires and the entity reads as validated. The shipped kms has had
`iffBaseEntities:hasOutWorkpiecexx` in its model instance all along, two
letters from `hasOutWorkpiece`, and nothing ever said so.

**➕ New attribute…** asks for the name, whether it carries a *Property* (a
value) or a *Relationship* (another entity) — that decides which key holds the
payload and which half of the encoding a shape must constrain — and one line of
prose. It writes the declaration into `knowledge.ttl` with `rdfs:domain` (this
entity type) and `rdfs:range` (the NGSI-LD kind), and opens the line.

#### Nested attributes

A sub-attribute's subject is the parent's **attribute node**, and the encoding
types that node: `hasFilter` expands to a node `a ngsild:Relationship` carrying
`ngsild:hasObject`. So `rdfs:domain` works perfectly well — it is that node's
class:

```turtle
iffBaseEntities:hasTrust a owl:DatatypeProperty ;
    rdfs:domain <https://uri.etsi.org/ngsi-ld/Relationship> ;   # what carries it
    rdfs:range  <https://uri.etsi.org/ngsi-ld/Property> ;       # what it is
    rdfs:label  "a sub-attribute of hasFilter: how far the reading is trusted" .
```

An ordinary class, nothing invented, no punning — and the kms was already doing
it for `base:boundBy`. What domain constrains is the **kind** of carrier: this
may hang off any Relationship.

**Which** attribute it nests inside is the shapes', and only the shapes', to
say — a `sh:property` nested inside the parent's own property shape. The
two-layer encoding makes it exact: an inner `sh:property` on
`ngsild:hasValue`/`hasObject`/`hasJSON`/`hasValueList` is the *value*, and on
anything else a *sub-attribute*:

```turtle
sh:property [ sh:path iffBaseEntities:hasState ;
        sh:property [ sh:path ngsild:hasValue ; sh:class base:MachineState ] ,
                    [ sh:path iffBaseEntities:hasXXXWorkpiece ;      # ← nested
                      sh:property [ sh:path ngsild:hasObject ;
                                    sh:class iffBaseEntities:Workpiece ] ] ]
```

So the two halves answer different questions, and together they answer **which
attributes to offer when you nest one**:

| | says | used for |
|---|---|---|
| `rdfs:domain ngsild:Relationship` | may hang off any Relationship | the candidates |
| a nested `sh:property` | is placed inside *this* attribute | the ones already there |

Asking for the sub-attributes of `hasFilter` returns the placed ones first,
then the ones a Relationship is allowed to carry. Sub-attributes are **not**
offered among an entity's attributes — an entity does not carry one, and
putting `hasTrust` on a Filter would put it where no shape looks.

➕ **New attribute…** on a nested row names the parent attribute as the
carrier, and the declaration comes out as above. Placing the nested
`sh:property` in the shapes is still yours to do.

### Deleting a project

The one gesture no other gesture undoes, so it says the most before it happens.
The 🗑 sits on the **Project** row itself — the row that names the project — and
the same action is in the SemForge menu, in the Package view's title submenu,
and on a folder in the Explorer. It shows what the directory actually holds:

```text
Delete the project "test"?

/home/you/kms/test

10 file(s), 8 KB.

1 item(s) here are not part of the package: notes.md. Nothing else knows
what they are.
Nothing here is tracked by git, so nothing can bring it back.
```

Three things you cannot see from a tree row, and the reason the server is asked
first: what in there is **not** the package (a README somebody wrote, a scratch
file, a vendored copy — that is what a deletion actually costs), whether it
holds **packages of its own**, and whether **git has any of it**. Tracked files
come back with one command; untracked ones do not come back at all, and the
warning says which you have.

Then it asks again: type the folder name. A modal is dismissed by the same
reflex that opened it, and this is the wrong place for a reflex.

It goes to the **trash**, not to `unlink`. A confirmation is a guess about what
somebody meant; the trash is the thing that forgives being wrong. Nothing in
the SDK deletes — `semforge.package.removal` only plans, and has no `rmtree` in
it.

### The Package view (formerly Project)

The first of the views, and the one that says what the package *is*
rather than what it says. Its first row is **Health**, the package at a glance
(`6/6 cases pass · 3 violation(s) · 67 untested`); a click opens the health
page. It is red only for what is wrong with the package itself — a failing
case or a broken reference — since violations in the model data are
information. It is asked for after the rest of the view, so a slow first
computation never holds up the settings beneath it.

```text
Project      Cutting cell
  name       Cutting cell          ✎
  path       /home/you/kms/test
  recognised by  semforge.yaml
  manifest   semforge.yaml
Settings     semforge.yaml — click the pencil to change one
  local context      context.jsonld            ✎
  published context  https://…/context.jsonld  ✎
  entity root        —  not declared           ✎
  namespaces         4
  dependencies       0
Contents     13 shape(s) · 44 entity(s) · 6 case(s)
  knowledge / shapes / model   which file or directory, and how many documents
  test cases  6   4 suite(s): test_CartridgeShape, …
```

Every row that names a place carries `file:line`: clicking a setting opens its
line in `semforge.yaml`, so the paragraph explaining it is right there.

**Namespace prefixes are a package-wide table**, agreed once and binding on
every artifact: `knowledge.ttl`'s `@prefix`, `shacl.ttl`'s, and the model's
context all have to mean the same thing by the same name. rdflib binds one
prefix per namespace, so a second name evicts the first and a term copied
between artifacts changes meaning.

`rdf`, `rdfs`, `owl`, `xsd`, `sh` and `ngsild` are **known to every package**
and appear under *standard names* on that row. Nobody should have to write them
down: a package that listed them would carry boilerplate that can only drift,
and one that forgot would be told its own `shacl.ttl` had invented `sh:`.
They sit at the lowest precedence, so a package that has a reason to call one
of them something else declares it in `semforge.yaml` and that wins.

Every name appears **once**. A package that declares one of the standard names
with the standard IRI sees it under *standard names*, not in its own table — it
is the same name, and listing it above as this package's vocabulary is what
made `ngsild` look like two definitions. The row still carries its `file:line`
and says the line can go. Declaring one with a *different* IRI is a deliberate
override, so that one stays in the package's table and says what it overrides.

🗑 on a name **removes** it, in three steps depending on what the name is doing:

* **nothing uses it** — removed, no question;
* **in use, but removing it changes nothing** — because `context.jsonld` names
  it too, or it is one of the standard set — you are asked first, with what
  binds it and why it is safe: *"ngsild: is in use — <…> is bound in shacl.ttl
  and names 121 term(s). Removing this line is safe anyway: the standard set
  names it "ngsild:", so the table does not change."*;
* **in use and load-bearing** — refused: *"iffBaseShacl: cannot be removed — it
  is in use. <…> is bound in shacl.ttl and names 42 term(s), and nothing else
  in the package gives it a name."* Taking it out would leave every one of
  those terms undefined.

Usage is measured from both halves that matter: files whose `@prefix` binds the
namespace, and terms actually in it. A line that merely restates
`context.jsonld` says so on its row before you click — it reads as this
package's own vocabulary and is not.

The **namespaces** row is where that table lives. ➕ on it defines a new one —
it asks for the name and the IRI, refuses one that would collide with an
existing name or give a namespace a second name, and writes it to
`namespaces:` in `semforge.yaml`. The row itself turns red when an artifact
disagrees with the table, and the disagreement shows on the offending
`@prefix` line as a diagnostic. On the command line that is `semforge prefixes`
(`--define plant=https://example.org/plant/` to add one, `--fix` to align the
artifacts).

The pencil edits it. The write is **line-based**: it replaces the value on that
one line and leaves the rest of the file byte-for-byte, because the comments in
`semforge.yaml` are the documentation and a YAML round-trip deletes all of
them. A package with no `semforge.yaml` at all — the kms layout — gets one on
the first edit.

Two rows carry a warning rather than a blank: a **published context** that is
not declared (`semforge export` has nowhere to point the model) and **no test
cases** (nothing proves a constraint can fire). A setting that is simply not
set says so and names what applies instead — a list of whatever happens to be
in the file cannot show what you have *not* set, which is most of what you need
to know about a package you did not write.

**If a tree is empty it now says why** in the panel itself: no package found (and
what it looked for), the server not running, or whatever the server reported.
An empty panel with no message was indistinguishable from a broken extension,
which cost a day.

If you keep your interpreter somewhere the search will not find, set
`semforge.pythonPath`.

---

### The Knowledge (Ontology) view (formerly Vocabulary)

Three groups, for the three things `knowledge.ttl` declares:

```text
Entity types         8 type(s) under Entity
Vocabulary classes   …
Attributes           17 attribute(s) · 21 ontology relation(s)
  iffBaseEntities:Machine                1 attribute(s)
    iffBaseEntities:hasState             Property · 12 use(s)          ⚖
      iffBaseEntities:hasXXXWorkpiece    Relationship · inside hasState · 6 use(s)
  iffBaseEntities:Cutter                 5 attribute(s)
    iffBaseEntities:hasOutWorkpiece      Relationship · used by nothing   ⚠
  Ontology relations   used within the ontology, never as a document key
    material:contains                    22 statement(s)
```

Attributes sit under whatever **carries** them — the entity type from
`rdfs:domain`, shown where it is *declared* since it is inherited from there
down — and a sub-attribute sits under the attribute it nests inside, never at
the top. `rdfs:subPropertyOf` nests too, where a package uses it. The ⚖ on a
row opens the property shape that constrains it.

`knowledge.ttl` also declares the ontology's **own** relations —
`base:bindsFirmware`, `material:contains` — which are never keys in a document
and which no shape should constrain. They are shown apart and judged apart:
calling them unused and unchecked is true of a document and meaningless of an
ontology. They are flagged only when nothing uses them at all, data or
ontology.

An attribute is flagged when no shape constrains it (nothing is ever checked
against it), when no document carries it (no constraint about it can fire), or
when it has no `rdfs:range` (nothing says whether it is a Property or a
Relationship, and the two carry their payload under different keys).

### The NGSI-LD vocabulary

A fourth group, last, and not the package's: the terms of the **encoding**.

```text
NGSI-LD vocabulary   12 term(s) · ../ontology/ngsild.ttl
  Attribute kinds    what an attribute's `type` may say
    ngsild:Property        64 use(s) · a value: a literal, or an IRI naming a term
    ngsild:JsonProperty     3 use(s)
    ngsild:GeoProperty     not used here
  Slots and metadata  where the payload hangs, and what is recorded beside it
    ngsild:hasValue        62 use(s) · `value` in JSON-LD
    ngsild:observedAt       7 use(s) · orders the instances; the latest is validated
```

Until now this was the one rule the project did not apply to itself. Everything
else must be declared before it is used — but `rdfs:range ngsild:Property`
pointed at a class no file declared, so `ngsild:Propery` was not an error
anywhere: the attribute simply had no kind, and nothing said why. A term the
package uses and the vocabulary does not declare is now reported, in this group
and under `semforge test`.

The SDK does not ship it: the package **declares** it in `semforge.yaml`,
like any other knowledge it depends on.

```yaml
ngsild:
  source: ../ontology/ngsild.ttl     # a local file, relative to the package

ngsild:                              # or the shared, official version, pinned
  source: https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl
  sha256: sha256:…
```

A local file is where a repo works on the vocabulary before it is published;
the url is the version everybody shares. Moving from one to the other is
changing `source` and adding the `sha256` — a remote source is fetched once,
cached in the package and verified against it.

A package that declares none gets the **default**: the official url, or what
the `SEMFORGE_NGSILD` environment variable names instead (a path or a url — a
machine or a CI job can point every undeclared package at one copy).
`semforge init` writes the default into a new package, pinned. The Knowledge
view says which source applies, and the Problems panel says when it matters:
`ngsild-unavailable` (it did not load: missing, offline, wrong hash),
`ngsild-unpinned` (a url without a sha256), `ngsild-undeclared` (the default
applies).

In this repo the shared local copy is
[`semantic-model/ontology/ngsild.ttl`](https://github.com/IndustryFusion/DigitalTwin/blob/main/semantic-model/ontology/ngsild.ttl), and the kms
points at it. The official
[`ngsild.ttl`](https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl)
declares only `Property` and `Relationship`, while the kms uses **ten** NGSI-LD
terms; the local copy is that file extended — the five attribute kinds, the
four payload slots, and the three metadata keys. Nothing is invented: every
class is a value of an attribute's `type` in the NGSI-LD API and every
predicate is what the NGSI-LD `@context` maps a payload or metadata key to. The
additions are marked in the Turtle so they can go upstream, after which the kms
moves to the url.

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

### Tests

Three layers, each catching what the one before cannot:

| Layer | Runs | What it proves |
|---|---|---|
| **unit** (`tests/unit/test_*.py`) | `make test` | the SDK: validation, the cooked trees and pages, every edit written as text and checked by parsing |
| **harness** (`tests/harness/drive.js`, driven from pytest) | `make test` | the extension's logic against a stubbed VS Code: what each command asks, sends and opens. `test_contracts.py` feeds it payloads from the **real server handlers**, in both tree modes, so the two sides cannot drift apart unnoticed |
| **protocol** (`test_lsp_protocol.py`, `test_lsp_sweep.py`) | `make test` | the **real language server over stdio**, on a copy of the corpus: every `semforge/…` request as the extension sends it (parameters it leaves out left out), every write checked on the files it changes, and a SPARQL query document through open, change, squiggles, completion, hover, formatting, quick fixes and close |
| **end-to-end** (`vscode/test/e2e`) | `make test-e2e` | the extension in a **real VS Code** with its real language server, on a throwaway copy of the kms corpus: the Entities & Test Cases view, every page opening, editing from the Main page, + Entity, New subtype…, + Attribute, the SPARQL workbench (Apply, Inspect, Save, Revert, snapshots, Remove…) and its editor (completion, squiggles and their fixes, hover, formatting, the NGSI-LD checks, Ctrl+Enter / Ctrl+S), Rename… of a shape (menu, F2, and a rename typed and saved, with the stale assert's quick fix), a case and a suite, Clone… of a case into its twin, Delete… of a case and a suite, Remove… of an attribute from a case, Severity… with a new level, Delete… of a shape with its asserts and cases, an attribute shared with an unrelated type (its domain becoming a union), Restart Language Server, Revalidate |

The end-to-end run downloads VS Code once into `vscode/.vscode-test` and needs
a display (a desktop, WSLg, or `xvfb-run make test-e2e`); a VS Code window
appears while it runs. `SEMFORGE_E2E_GREP=<text>` runs only the matching
tests, `SEMFORGE_E2E_KEEP=1` keeps the workspace copy for a look afterwards.
It copies the corpus with its symlinks *followed* — the corpus files link into
`semantic-model/kms` — and fails if the source corpus changed during the run.
`SEMFORGE_E2E=1 pytest -k e2e` runs it from pytest.

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

**Find all references** (`Shift+F12`) goes the other way, from any term to every
place that names it: the `sh:path` that constrains it, the SPARQL body that
reads it, the ontology, and every example case that carries it -- as a key, as a
type, or as an IRI value like `{"@id": "base:state_OFF"}`. It works from a
`.ttl` or a `.jsonld`, and matches on the expanded IRI rather than the text: a
term is expanded the way the file it sits in would expand it (a Turtle file by
its prefixes, a query by its own `PREFIX` lines, a document by its `@context`),
so `iffBaseShacl:CartridgeShape` and `iffFilterShacl:CartridgeShape` stay two
terms, and `iffBaseEntities:hasObject` is not taken for `ngsild:hasObject`.
Only a name that cannot be expanded at all falls back to its local name.

**One click shows the row and leaves it open.** Selecting a row moves the file
to it *and* unfolds it. A click on a collapsible row toggles it, so the reveal
that showed you an entity also folded it shut — you had to click twice to see
what one click was supposed to show. The chevron still folds it.

**A click opens the row's page.** Tree → page → source: a click on a type or
an attribute in Constraints opens that type's page with the attribute marked; a
row inside a test case in Model opens the case page with its entity marked; an
entity type or one of its attributes in Knowledge opens the type page. One tab
is reused, and focus stays in the tree, so you can arrow through the rows and
watch the page follow. Rows that have no page yet — vocabulary, the model
scratchpad, settings — still move the editor to their source.

**The source is a right-click away**: **SemForge: Open source** on any row of
the three trees. Every node carries its own `file:line` — an attribute, a
single `sh:minCount`, not just the shape — so the editor lands on the line you
picked rather than the top of the block. To have a click do that instead, as it
used to, set *Settings → SemForge → Trees: Click* to `source`.

**One icon per kind**, the same in every view: `symbol-class` an entity type,
`symbol-field` an attribute, `symbol-event` a rule, `beaker` a test suite or
case, `symbol-object` an entity in the data, `symbol-enum` a vocabulary and
`symbol-enum-member` its values. Status is the icon's **colour** — red failing
or violated, yellow a warning, green a passing case, grey inherited — and the
description says it in words; a row never changes its icon to say it is wrong.
In summary mode rows have no hover buttons: their actions are on the right-click
menu and on the page. *Trees: Detail* `full` brings the buttons back.

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

A **greyed icon** and `from Machine` in the description mean the constraint is
inherited: it is declared on a
supertype and applies here because `sh:targetClass` reaches subclasses. `Filter`
shows `MachineShape`'s `hasState` for that reason — the constraint was never
missing from Filter, only from the tree. Right-click offers **Go to Definition** and **Declare on This Type**.

**Adding an attribute to a shape** is the **+** on one of the type's *own*
shape rows (an inherited shape has none — adding there would write into the
supertype's shape). It offers the attributes the knowledge gives that type,
and lists the ones it cannot add too, so the one you came for is never silently
missing:

```text
Add an attribute to iffBaseShacl:CartridgeShape
── Declared for this type ─────────────────────────────
  hasWasteclass   Property · iffFilterEntities:hasWasteclass
── Declared for other types — adding one gives it to this type too ──
  hasPressure     declared for Machine; adding it extends its domain to FilterCartridge too
── Already constrained ────────────────────────────────
  isUsedFrom      already constrained by this shape — edit it there
  hasState        already constrained by iffBaseShacl:MachineShape
```

**An attribute of another type** — `hasPressure`, declared for Machine, wanted
on an unrelated FilterCartridge — is offered too, in its own section. Picking
it asks first, because it changes the knowledge and not only this shape: its
`rdfs:domain` becomes the union, and then it is added here like any other.

```turtle
iffBaseEntities:hasPressure a owl:DatatypeProperty ;
    rdfs:domain [ a owl:Class ;
        owl:unionOf ( iffBaseEntities:Machine iffBaseEntities:FilterCartridge ) ] ;
    rdfs:range ngsild:Property .
```

A union, not a second `rdfs:domain` triple: two triples mean *both* — a
reasoner would infer that every entity with a pressure is a Machine **and** a
FilterCartridge, and with the two declared disjoint the knowledge becomes
inconsistent. The union says *a Machine or a FilterCartridge*. A union already
there grows by one member; several plain triples (the form the OPC UA mapping
generates) are rewritten as one union. Only the domain moves — the rest of the
statement is untouched, and it is written only if the file's graph after is
the one before with exactly that domain replaced. SemForge **reads** both
forms as "any of these types" everywhere: the pickers, the type pages, the
Knowledge view (which lists a shared attribute under each type), SPARQL
completion. Its value is still constrained per shape, so the value it must
have on one type is not the value it must have on the other.

Then it asks two things: **Optional** (`sh:minCount 0`) or **Required**
(`sh:minCount 1`), and what the **value** must be — for a Relationship, which
entity type it points at; for a Property, a datatype (`xsd:double`, …) or a
vocabulary class whose individuals are the allowed values. The kind is never
asked: it is the attribute's `rdfs:range` in the knowledge. What is written is
the full two-layer encoding, inserted into the shape's own statement so every
comment around it survives:

```turtle
    sh:property [ sh:path iffFilterEntities:hasWasteclass ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:nodeKind sh:BlankNode ;
        sh:property [ sh:path ngsild:hasValue ;
            sh:minCount 1 ;
            sh:maxCount 1 ;
            sh:nodeKind sh:IRI ;
            sh:class iffFilterKnowledge:Wasteclass ] ]
```

**Which namespace a new attribute gets.** By default the namespace of the type
that carries it — an attribute of `iffBaseEntities:Cutter` is
`iffBaseEntities:…`. But a namespace is ownership, not location: the kms's
`hasWasteclass` is carried by a base type and owned by the filter extension,
`iffFilterEntities:`. So after the name, when the package has more than one
candidate, a picker shows each choice as the full name it would write
(`iffFilterEntities:hasPressure`), the default first, then the namespaces that
already hold attributes, then the rest — never a standard vocabulary (rdf, owl,
sh, ngsild) and never a namespace that holds only shapes. Typing the prefix
into the name (`iffFilterEntities:hasPressure`) skips the question. A prefix the
package does not know is refused, not dropped — define it in the Package view
first.

If the attribute does not exist yet, the last entry, **New attribute…**,
declares it in `knowledge.ttl` for the shape's type and carries straight on to
the two questions above. The same flow is **SemForge: New attribute…**, which
starts by asking for the type instead and is reachable without the tree: the
Command Palette, the SemForge item in the status bar, right-click on a `.ttl`
or `.jsonld` (editor or Explorer) → **SemForge**, and the **symbol** button in
the Entity Types & Constraints and Knowledge view titles. VS Code gives an extension no menu of
its own beside *File* and *Edit*, so these are the places one can live. Started
that way it offers **Not now** too — declaring alone is a fine place to stop —
and a type with no shape of its own is declared and told so, rather than having
the attribute written into an inherited shape, where it would be demanded of
every sibling type.

It refuses, and writes nothing, for an attribute the knowledge does not
declare, one it gives to a different type (required here it would be demanded
of entities that never carry it), a sub-attribute, one this shape already
constrains, and one a supertype's shape constrains — that is an override, and
**Declare on This Type** is the command that says whether it would take effect.

**Sub-attributes.** In NGSI-LD an attribute can carry attributes of its own —
the kms's `hasTrust` hangs off `hasFilter`, `hasXXXWorkpiece` off `hasState`.
The **+** on an *attribute* row in the Entity Types & Constraints view adds one: it offers what
the knowledge allows inside that attribute (a sub-attribute's `rdfs:domain` is
the parent's kind of node, `ngsild:Relationship` or `ngsild:Property`), ends in
**New sub-attribute…** to declare one carried by that attribute, and writes the
same two layers an attribute gets, *inside* the parent's `sh:property [ … ]`:

```turtle
    sh:property [ sh:path iffBaseEntities:hasFilter ;
        …
        sh:property [ sh:path iffBaseEntities:hasConfidence ;
            sh:minCount 0 ;
            sh:maxCount 1 ;
            sh:nodeKind sh:BlankNode ;
            sh:property [ sh:path ngsild:hasValue ;
                sh:minCount 1 ;
                sh:maxCount 1 ;
                sh:datatype xsd:double ] ] ]
```

In the Entities & Test Cases view, right-click an attribute → **SemForge: Add Sub-attribute**
puts one into that attribute instance — the one the row shows, chosen by its
datasetId when the attribute has several. An entity attribute is refused
inside another attribute, a sub-attribute is refused inside a parent of the
wrong kind, and a duplicate is refused; none of them write anything.

**Deleting an attribute** is a right-click on its row in the Knowledge or
Entity Types & Constraints view (**SemForge: Delete attribute…**; from the palette it asks
which). An attribute is never in one place, so nothing is removed before you
have seen all of them:

```text
hasWidth is in use. Delete it and everything that depends on it?

the declaration (1)
   knowledge.ttl:75  the declaration of hasWidth
property shapes (1)
   shacl.ttl:296  iffBaseShacl:WorkpieceShape: the property shape on the entity
entities carrying it (4)
   model-instance.jsonld:252  urn:workpiece:1 carries it
   examples/subobjects/workpiece-steel.jsonld:15  urn:workpiece:1 carries it
   …
                                       [ Delete with 5 dependent(s) ]
```

One yes removes the declaration, every `sh:property` group whose path is the
attribute (nested ones too, with whatever is nested inside them), the key in
the model and every example, and each expectation assert naming one of those
constraints — computed and verified first, then written all at once, or not at
all. A case left expecting a violation it no longer asserts is called out.

The other button, **Delete declaration only**, removes the statement in
`knowledge.ttl` and nothing else — every shape, key, assert and query stays as
it is. Use it when the term is moving to another ontology, or when you would
rather rewrite its uses by hand. It is offered whenever the attribute is in
use, including when the full delete is blocked, since it touches none of the
blockers. What it leaves is not silent: each remaining use shows in the
Problems panel as naming an undeclared term, until it is declared again or the
use is removed.

Two kinds of use **block** the full delete: a SPARQL constraint or rule that reads
the attribute, and a shape or ontology statement that names it outside a
property shape (the kms's `CartridgeShape` uses `hasCartridge` inside a two-hop
inverse path). A query is not a list of parts — cutting the attribute out of it
changes what the rule means, and leaving it makes a rule that silently matches
nothing. The dialog lists them and opens the first, and deletes nothing.

**The package health page.** Is this package in good shape, and what needs
attention first? The first entry of the status bar's SemForge menu (also the
pulse button on the Package view, or **SemForge: Open package health**) opens
one page that puts side by side what `test`, `validate`, `check` and
`--coverage` each answer on their own:

- **figures**: test cases passing, violations in the model, constraints
  evaluated (the same count `semforge validate` prints), constraints no
  example makes fire, broken references, and the cache;
- **needs attention**: one list, errors first — a failing case, a reference
  that points at nothing, an undeclared attribute in a case — then warnings,
  where what is broken (a violation in the model) comes before what is merely
  untested (a constraint that never fired), then notes. Every item has the
  button that opens what it is about: the case page, the type page, or the
  line.

**Rescan** on the page rebuilds everything from scratch, ignoring the cache.

**New test case… — adding a test file.** The `+` in the Entities & Test Cases view title (also:
right-click a suite or the **Tests** group, the status bar menu) asks:

- **which suite** — an existing one, a new one for a shape that has none yet
  (`test_PumpShape`), or **New suite…** with any name you like;
- **should it conform or violate** — `good/` with `expect: valid`, or `bad/`
  with `expect: invalid`;
- **where it starts** — a copy of a case (its includes written into the new
  file, so editing it never changes a shared subobject), an entity from the
  model, a new entity of a type (its required attributes given valid values),
  or an empty file;
- **its name** (suggested).

**New suite… — a new test-case folder.** Right-click **Tests** in the
Entities & Test Cases view → **New suite…** (or pick it at the bottom of the suite list
above). A suite is a folder under `examples/` named `test_…`; type `pump
limits` and it becomes `test_pump-limits` — letters, digits, `_`, `-` and `.`,
`test_` added when missing. A folder only exists with something in it, so the
suite's first case is asked for right away (conform or violate, where it
starts, its name), and the folder appears with `good/` or `bad/` and its
`expectations.yaml`.

It is written, declared in that folder's `expectations.yaml`, run once, and
its case page opens. A bad case is declared without asserts: what fires shows
on the case page, where **Assert it** turns each firing into a claim; while
nothing fires the message says so. A `.jsonld` already under `examples/` that
no expectations file declares — a file nobody runs — is offered too
(**Declare a file under examples/ that nothing runs**) and is declared where
it is.

**Clone… — a case's twin.** The usual way to a bad case is the same scene
with one thing broken; the usual way to a good one, a bad case repaired.
Right-click a case in Entities & Test Cases (or the case page's `⋯`) → **Clone…** asks one
thing — **Expect the opposite** (a `good/` case's twin goes to `bad/`, a `bad/`
case's to `good/`) or **Expect the same** — and a name (`filter-on-violates`,
`filter-off-conforms`, `…-copy`). The clone stays in the case's suite, its data
copied with its includes written in (editing it never changes a shared
subobject), and its case page opens.

- **valid → invalid**: identical data violates nothing yet, so the twin
  fails — *"Nothing fires yet: edit its data until it violates, then assert
  what fires on its case page."* Break it, and **Assert it** on what fires.
- **invalid → valid**: the asserts are not copied (they would be wrong); the
  twin fails until its data conforms.
- **the same**: asserts and description come along, and it passes as the
  original does — a copy to vary.

Its description says where it came from and what it is waiting for.

**Delete… — a case, or a whole suite.** Right-click a case or a suite in
Instances (or the case page's `⋯`). A case is its file and its entry in
`expectations.yaml`; both go, and a `good/` or `bad/` — or a suite — left
with nothing goes too. The question says first what the deletion costs: the
constraints *no other case asserts* — *"No other case asserts:
iffBaseShacl:StateOnCutterShape/SPARQLConstraintComponent. After this, nothing
proves it can fire."* A file another case includes is shared data: its entry
goes, the file stays, and the question says who includes it. A suite goes
whole, listing its cases; it is refused while a case outside it includes one
of its files, which would then point at nothing. The case page and editors
of deleted files close.

**New test… for an attribute.** A new attribute needs cases that prove its
constraints work. Right-click it in the Entity Types & Constraints view (**SemForge: New test for
this attribute…**), or use its row on the type page — the **Tested** cell
("New test…" while untested) or the row's `⋯` menu. It asks what the test
should prove:

- **valid** — the attribute present with a valid value; the case conforms;
- **fires: …** — one per constraint that can actually fire: *missing* (a
  required attribute left out), *no value*, *twice* (two instances, a
  `maxCount` exceeded), *wrong datatype* (a text where `xsd:double` is
  expected), *too high / too low* (one past `sh:maxInclusive` /
  `sh:minInclusive`), *wrong class* (an IRI that is not a MachineState),
  *wrong kind*, *not in the list*. An optional attribute is not offered
  *missing*: leaving it out cannot fire.

Then a name (suggested: `pressure-wrong-datatype`). The case lands in
`examples/test_<Shape>/good|bad/`, declared `expect: valid`, or `expect:
invalid` with an assert that this constraint fires on that entity. Its scene
is a valid case with an entity of the type (includes written into the file),
else the model's entity, else a new entity with every required attribute
given a valid value. If the entity already has the attribute it is changed,
not replaced — a sub-attribute nested in it stays. The case is run once, and
the message says whether it already passes; the few breaks that cannot be made
mechanically (a Relationship that is not an IRI) say what to edit instead.

**The test case page.** A case answers three questions — what it claims,
whether the claims hold, what data it uses — and the Model tree spread them
over up to nine levels. A click on a case in the Entities & Test Cases view, or on
any row inside it (or **SemForge: Open test case page**), opens a page that answers them in
that order:

- **the claim**: *expects invalid · passes*, with `semforge test`'s own failure
  messages when it does not — the page runs the case exactly as the test
  runner does, so the two cannot disagree;
- **claims**: each assert, *holds* or *does not hold*, in plain words
  ("hasCartridge is required but missing on urn:filter:9"); then everything
  that fired without being asserted, marked *also fired* — either a second
  problem the case found, or a sign the data is not what the case means it
  to be;
- **data**: the case's own file and each include as sections (an include
  says how many other cases share it, because an edit there changes them
  too), one card per entity with its attributes and sub-attributes. A
  violation sits on the attribute it is about — a missing sub-attribute on
  the attribute it belongs inside — with SHACL's raw message as the tooltip.

Ids, attributes and files link to their line; an entity's type opens the
type page.

**Cards or graph, and a filter.** Above the entities, *Cards | Graph* switches
between the cards and the **entity graph**: a tree of cards, for following a
path and reviewing every entity along it. It starts at the entities nothing
points at, each a card with its rows — the same rows, links and edits as in
the cards view. A relationship row has a **▸**: it opens the card it points
at right under the row, so a path reads top to bottom (*Pump › hasPorts ›
PortsGroup › has‹Drive› › DrivePort*); a relationship inside a sub-attribute
opens the same way. Each entity is open in full once: asked for again, it is
a line — *↩ … is open elsewhere on this page* — that goes to it, which is
also where a cycle ends. A cycle nothing points into is entered at its first
entity, so every entity can be reached; a target that is not on the page
cannot be opened and says so. While scrolling, a bar at the top shows the
path to the card in view, each step a link back. The open branches and the
scroll position are remembered, so the edit you make on a path does not
close it.
*Filter* (closed until opened) narrows by type, by an attribute the entity
has, or by what its id contains: the cards that do not match are hidden, and
in the graph the matching entities become the roots. The view, the filter and
whether it is open are remembered per page.

**Editing on the page.** The data is edited where you read it, through the
same commands as the Entities & Test Cases view (so the same pickers: a known attribute, the
values the shape allows):

- a value you can change is a link — click it to edit it;
- **⋯** on an attribute row: *Edit value*, *Add sub-attribute*, *Add
  observation*, *Go to the SHACL rule*, *Open in .jsonld*, **Remove …** (and
  *Remove this instance* on a row that is one of several datasetIds);
- **+ Attribute** on each entity card, **+ Entity** on each file.

**Remove…** takes out what the row stands for, after asking: the whole
attribute, one datasetId's instances, one observation of a series, or one
metadata key (`observedAt`, `unitCode`) — also from the Entities & Test Cases view's
right-click. An attribute left with nothing goes entirely. Removing an
attribute a shape requires makes the case violate it — which is how a bad
case tests that it is required. In an included file the question says which
other cases change with it.

After a change the case runs again and the page re-renders, so you see the
claims move. An edit in an include still changes every case that shares it —
the file's header says how many.

**The Main page.** The package's own `main.jsonld` (or
`model-instance.jsonld`) has no claims, but it has entities and violations. A
click on **Main** in the Entities & Test Cases view, or on any row inside it, opens the same
cards for it: entity and violation counts instead of *expects/passes*, no
claims, and the same editing. Violations here are information — the model
declares nothing, so it cannot fail.

**Assert it.** Each *also fired* line has two buttons. **Assert it** turns the
firing into a claim: the assert is added to that case in its
`expectations.yaml` (comments and layout kept) and the line moves to *holds*.
That matters because an unasserted firing is checked by nothing unless a
residue is pinned — if the constraint stopped firing, `semforge test` would
stay green. Asserted, the case fails the day it stops. **Open in .jsonld** is
the other answer: when the firing only happened because the case's data is
incomplete (the kms's `without-cartridge` filter has a `hasState` without the
`hasXXXWorkpiece` MachineShape requires), fix the data so the case fails for
exactly one reason, rather than pinning the accident as expected. The button's
tooltip says so. A duplicate assert, or one on a constraint no shape declares,
is refused; a case with a pinned residue is told to `semforge accept` again.

**The SPARQL workbench — developing SPARQL constraints.** A shape page lists
its SPARQL queries under **Checks**; **Open** on one (or **Open in workbench**
at the top of a SPARQL shape, **SPARQL…** on a type page's rule row, or
right-click a shape in Shapes) opens the query in a page of its own. The page
shows what you work with — the query's name, severity and message, one
toolbar, the result — and folds the rest away:

- **The toolbar** — **Run over** the data (**Main** or a test case, the cases
  this shape reaches listed first) and how many focus nodes it has; **▶ Apply**
  (Ctrl+Enter in the editor) runs the editor's text as it is now;
  **Snapshot**; and **⋯** for what is used now and then: show the editor, show
  the query in `shacl.ttl`, open the shape page, **Remove…**. While the editor
  holds unsaved changes, *● unsaved* shows and so do **Save** (Ctrl+S) and
  **Revert** (the editor's Revert, back to what `shacl.ttl` holds).
- **The query** is edited in a real editor beside the page, `<Shape>.rq`
  (language SPARQL), with VS Code's own undo, find and multi-cursor. Save
  writes it over the `"""…"""` literal in `shacl.ttl` and nothing else
  (checked by parsing; refused — as a failed save, the edit kept — if the
  literal changed since the editor read it). See *The SPARQL editor* below.
- **Result** — for a constraint, which focus nodes violate, each row the query
  returned with `sh:message` filled in from it (`{?value}`, `{$this}`), and
  what the *saved* query says on the same data (*now also …*, *no longer …*).
  For a rule, the triples its CONSTRUCT builds. A query that does not parse
  says where; what validation reads differently is warned about (MINUS,
  VALUES, SERVICE, no `$this`, an aggregate in the current view).
- **What it runs over** (folded) — the instance data as Turtle, with what
  the rules derived listed apart.
- **What it selects** (folded) — how `$this` gets its value. A SHACL-SPARQL query never picks
  its own nodes: the engine takes the shape's target (*every Cutter, and every
  subclass of it → 2 node(s)*) and runs the query once per node with `$this`
  already bound. **Show as SPARQL** shows that hidden part as what it amounts
  to — `VALUES $this { <urn:plasmacutter:1> <urn:plasmacutter:2> }`. A query
  that never mentions `$this` runs once, and the page says so.
- **Show every row and the FILTER checks** — the toggle on the Result
  (Ctrl+Shift+Enter turns it on): the query taken apart, its text untouched: per focus node,
  every row its WHERE makes with *every* variable (not only the SELECTed
  ones), and for each part of the outer FILTERs (`&&` split up) whether it
  held: ✓, ✗, or ⚠ for an error such as an unbound variable, which FILTER
  counts as false. A dropped row is greyed, so "why does it not fire here?"
  is answered by the ✗. With GROUP BY it shows the rows before grouping; a
  FILTER inside OPTIONAL or a nested group is noted, not split. Its verdict is
  Apply's (a test checks this for every constraint and case).
- **Snapshots** (folded, there once you take one) — keep the current text, named, with what it did (*1 violating
  on filter-off.jsonld*), to come back to while experimenting: **Load** puts
  it into the editor, **Delete** drops it; *Saved in shacl.ttl* is always
  listed first. Snapshots last for the session only — nothing is written
  anywhere; closing VS Code keeps the saved query and nothing else. Which
  folds are open, and the toggle, are remembered while the page is open.
- **Shortcuts** (folded) — the editor's keys.

That data is exactly what validation gives the query, built the same way:
rules expanded to their fixpoint, the shape's data view (`current` keeps the
latest observation of each attribute), the knowledge added, and pyshacl's own
extra rule pass. A **constraint** runs once per focus node with `$this` bound,
and every row is a violation — the workbench's verdict is the one `semforge
test` reaches (a test checks this for every constraint and case). A **rule**
runs earlier, before any view, on every observation; it is shown over the
rules' fixpoint.

**+ Add check ▾ → SPARQL constraint** (shape page, or right-click a shape) asks for its
`sh:message` and writes a constraint that fires on nothing (`FILTER(1 = 0)`,
with the package's PREFIX lines), then opens it here: write the condition,
Apply until it finds what you mean, Save. Unsaved edits survive switching tabs;
closing the page with them offers to reopen it with them.

**The SPARQL editor.** The query's editor knows the package — its
namespaces, its classes, its attributes and whether each is a Property or a
Relationship — through the SemForge language server:

- **Completion** (Ctrl+Space, and as you type `:` `?` `$`): after `PREFIX`,
  the package's namespaces written out; after `iffBaseEntities:`, that
  namespace's classes, attributes and individuals, each with what it is
  (*Property · on iffBaseEntities:Machine*). A prefix the query has not
  declared is declared by the completion — its PREFIX line is added. Where a
  predicate goes, an attribute also comes as the whole NGSI-LD step:
  `iffBaseEntities:hasCartridge [ ngsild:hasObject ?cartridge ]` for a
  Relationship, `[ ngsild:hasValue ?state ]` for a Property. `?`/`$` offers
  the query's variables; anything else, keywords and built-in functions.
- **Squiggles**, as you type: a syntax error at the bracket or clause where
  the query stops reading; a prefix used but not declared (red, with **Add
  PREFIX** as its quick fix); a name in the package's own namespaces the
  knowledge does not declare — *iffBaseEntities:hasStat … did you mean
  iffBaseEntities:hasState?* — with the correction as its fix; an attribute
  read through the wrong NGSI-LD layer (`hasValue` on a Relationship, which
  matches nothing); what SHACL refuses (MINUS, VALUES, SERVICE, `AS ?this`);
  a constraint without `$this`; an aggregate in the current view.
- **Hover** on a name: its full IRI, what it is, its comment — and for an
  attribute, how to read it (`[ ngsild:hasObject ?x ]`).
- **Format Document** (Shift+Alt+F): one layout — a PREFIX per line, clauses
  on their own lines, a triple per line ending ` .`, `;` continuing on the next
  line, `[ … ]` and `( … )` kept on one line, keywords in capitals, comments
  where they were. Only whitespace and keyword case change, and that is
  checked: if a token would change, nothing is formatted.
- **Write out / Shorten** (the light bulb on a name): `iffBaseEntities:hasState`
  ⇄ `<https://…/base_entities/hasState>`, declaring the prefix when shortening.

**NGSI-LD in a query.** An attribute is two steps in RDF: the entity points at
an attribute *instance* (a blank node), and the instance holds the payload —
`$this iffBaseEntities:hasPressure [ ngsild:hasValue ?pressure ]`. The payload
predicate follows the attribute's kind, declared once, in the knowledge, as
`rdfs:range ngsild:<Kind>`:

| Kind | payload | Kind | payload |
|---|---|---|---|
| Property, GeoProperty | `ngsild:hasValue` | ListProperty | `ngsild:hasValueList` |
| Relationship | `ngsild:hasObject` | ListRelationship | `ngsild:hasObjectList` |
| JsonProperty | `ngsild:hasJSON` | LanguageProperty | `ngsild:hasLanguageMap` |
| VocabProperty | `ngsild:hasVocab` | | |

A property without an NGSI-LD range is a plain property of the knowledge, read
directly: `?material iffFilterKnowledge:hasWasteclass ?class`.

Every SPARQL constraint must also compile with shacl2flink, and shacl2flink
reads an attribute only as `attr [ … ]`, and only an attribute a shape nests a
payload for. Validation reads any form. So the editor refuses nothing; it
says what a form means and what Flink can compile, each with its rewrite:

| Written | What is wrong | Quick fix |
|---|---|---|
| `$this ex:hasPressure ?p . FILTER(?p > 5)` | `?p` is the instance, not the value | `[ ngsild:hasValue ?p ]` |
| `$this ex:hasState base:state_ON` | the object is always an instance: never matches | `[ ngsild:hasValue base:state_ON ]` |
| `$this ex:hasPressure ?a . ?a ngsild:hasValue ?p .` | valid, but Flink compiles only `[ … ]` | folded into `[ ngsild:hasValue ?p ]` |
| `$this ex:hasFilter ?filter .` | `?filter` names the instance, which Flink reads as a plain triple | `[ ngsild:hasObject ?filter ]` (the payload of its kind, the variable kept); or, when the variable is used nowhere else, `[ ]` — only "it is there" |
| `ex:hasPressure/ngsild:hasValue ?p` | Flink has no property paths | `ex:hasPressure [ ngsild:hasValue ?p ]` |
| `ex:hasState [ ngsild:hasObject ?s ]` | the wrong payload for the kind | `ngsild:hasValue` |
| `?m plainProperty [ ngsild:hasValue ?v ]` | a plain property has no instance | `?v` |
| an attribute no shape nests a payload for | Flink would compile it as a plain triple | **Add a shape so shacl2flink reads it as NGSI-LD** — an optional property shape on the type that carries it (the type's shape is written first when it has none) |

A rule's CONSTRUCT template is checked the same way. Inside an attribute's
`[ … ]`, completion offers its payload first (`ngsild:hasObject ?filter` for a
Relationship), then `observedAt`, `datasetId`, `unitCode` (a Property's), and
the sub-attributes its shape nests, each as its own step. Hover says the form
an attribute needs, its sub-attributes, and whether Flink knows it. Inspect
and Apply show an attribute instance by what it holds — `[hasValue 21.5 ·
observedAt 2024-…]` — instead of a blank node id.

**Remove…** (behind the workbench's ⋯, or a query's ⋯ on the shape page)
takes one SPARQL constraint or rule out of its shape: its whole `[ … ]` and
the `;` joining it, nothing else — checked by parsing, and refused if the file
changed since the page showed it. It asks first, and says what goes with it:

- **the test cases that assert it.** An assert names the shape's SPARQL
  constraints together (`StateOnCutterShape/SPARQLConstraintComponent`), not
  one query. When this is the shape's *last* SPARQL constraint, nothing is
  left to satisfy them: **Remove it and its asserts** keeps those cases
  meaningful, **Remove it only** leaves them to fail. While another one
  remains, the asserts are listed and kept.
- **unsaved edits** in the workbench, if any.

After the last query of a shape the workbench closes; otherwise it shows the
next one. A query that is the whole shape statement (no target, nothing else)
is not cut out — remove the shape instead.

**Summary trees.** The trees are for finding things; the type page is where a
type is read and edited. So by default the trees show one row per meaningful
thing, said once (the `semforge.trees.detail` setting, `summary`):

| View | Summary | `full` |
|---|---|---|
| Types | the entity type hierarchy; under each type its OWN attributes (`hasCartridge — required · one · → FilterCartridge`, an inverse path as `inverse of hasCartridge`) and one **Rules** row, then its subtypes. Inherited attributes are on the type page, not repeated under every subtype | types → shapes → every SHACL parameter as a row, editable in place (192 rows for the kms) |
| Shapes | every shape, prefixes dropped where unique | every shape, full names |
| Instances | **Main** first (`8 entities · 3 violation(s)`), then **Tests** with its suites by shape (`FilterShape — 1 case(s) · all ok`); an entity's type in its row, each value once (`hasStrength — 0.6`) | the same two groups, suites as `test_FilterShape`, a separate `type` row, `0.6 — 0.6 · Property` |
| Knowledge | no Entity types group (that is the Entity Types & Constraints view); a vocabulary class counts its values (`MachineState — 7 values`); `3 shape(s)` instead of a list; an id in several files is one row | every group, every file's row |

Prefixes are dropped wherever the local name is unambiguous in that tree; the
two `CartridgeShape`s keep theirs. In summary mode **Override…** and right-click
→ **Open entity type page** on any Constraints row go to the type page, where
each parameter is. Switch with *Settings → SemForge → Trees: Detail*; all
trees redraw at once.

**Types and Shapes: read by type, written by shape.** A SHACL shape is not tied
to an entity type. It selects focus nodes by class (`sh:targetClass`), by named
node (`sh:targetNode`), by the subjects or objects of a predicate
(`sh:targetSubjectsOf`, `sh:targetObjectsOf`), by a SPARQL query (`sh:target`,
SHACL-AF), implicitly when the shape is itself a class — or it has no target
and is reached from another shape through `sh:node`. So constraints have two
views:

- **Entity Types & Constraints** (formerly Types, before that Constraints) answers *what must a Filter carry*: the hierarchy, a click opening
  the type page. The page **collects every constraint that applies** to the
  type — its own shapes', the inherited ones (`· from Machine`), and those of
  shapes that reach it by another target, in the same tables, marked with the
  condition: a shape on `sh:targetSubjectsOf hasValve` puts its rows on the
  Pump page as `· only when it has hasValve`. That is decided from the
  knowledge where it can be (hasValve's `rdfs:domain` is Pump), so it shows
  before any data exists; a named node or a SPARQL target is found through the
  data. Such rows are edited on their shape's page (**Open shape**).

  The page says the essentials first. At the top: the crumbs (with the
  type's **subtypes** beside them, for navigating down), the name, one status
  line (*2 of 2 in the model violate · 4 case(s), all pass · 5 never fired*),
  **+ Attribute**, and a **⋯** for the rest (New subtype…, Open the shape in
  .ttl, Create its shape, Refresh). Then three sections:

  - **Attributes**, grouped by where they come from — *Own · FilterShape*,
    *From Machine · MachineShape*, a shape's condition — instead of a column
    repeating it on every row. The **Test coverage** column says how well
    the cases prove it (*never fired*, *fires only*, *both ways*; New
    test… is in the attribute editor). What the model's data does is another question,
    marked beside the attribute's name: *hasXXXWorkpiece ✗ 2*, the violating
    entities in its tooltip. Own rows have a `⋯`; inherited ones a quiet
    **override…**. The shape page's table has the same columns.
  - **Rules** — each SPARQL constraint or rule by what it says (its
    `sh:message`), then its shape; **Open** takes it to the SPARQL workbench,
    its `⋯` to the shape page or the `.ttl`. Inherited ones are grouped the
    same way. **+ SPARQL constraint** writes one on the type's own shape.
  - **Instances** — the model's entities with their verdicts, then the test
    cases with theirs, one row each; a case opens its case page.

  *Shapes that apply under a condition* is folded at the bottom.
- **SHACL Shapes** answers *what does this shape check and what does it reach*: one
  row per shape, its target in words (`targets Filter`, `targets subjects of
  hasValve`, `targets urn:valve:1`, `SPARQL target`, `no target · used by
  ValveNodeShape`). A click opens the **shape page**: the target (a SPARQL
  target's query included), the attributes and rules as the type page shows
  them, the nodes it reaches in the model with their verdicts, the types those
  are, and the test cases that reach it and whether it fires in them.

  The page says first what matters, and keeps the rest one click away. At
  the top, the name, one status line (*2 in the model, all valid · 2 case(s),
  all pass*, or what is wrong), the one action the shape is usually opened
  for — **Open in workbench** for a SPARQL shape, **+ Attribute** for one
  with attributes — and a **⋯** for the rest (Open in .ttl, the type page,
  **+ Target**, **Merge into…**, Refresh). Then three sections:

  - **Checks** — every check, one row each: its SPARQL constraints and rules
    (message, severity, *tested both ways* / *never fired*, **Open** in the
    workbench, a **⋯** with Remove…, the query folded under it) and the
    attribute table. **+ Add check ▾** adds an attribute or a SPARQL
    constraint.
  - **Applies to** — the node selector in one line, with the type it is
    about, and the nodes it reaches in the model with their verdicts.
    **Edit targets** unfolds every target with **Remove** (a SPARQL target,
    being a query, stays in the `.ttl`) and **+ Target** (several targets
    add up; taking off the last one leaves a shape that runs only where
    another reaches it via `sh:node`).
  - **Tested by** — the cases that reach it, one row each: *fires* (and on
    what) or *holds*, and whether the case passes. **+ New case** shows while
    no case makes it fire.

  Its attributes are **edited exactly as on the type page** — the same rows,
  the same actions: click the presence or the value, the `⋯` menu (edit a
  constraint, add a sub-attribute, remove from the shape, delete, New test…),
  the Tested cell, and **+ Attribute** — every write going into this shape. A
  shape without a class target offers every declared attribute (no type to
  scope them to); New test… there needs a type, so it says to start from the
  type page of an entity the shape reaches. A shape that is itself a class
  (`ex:Gauge a rdfs:Class, sh:NodeShape` — an implicit class target) counts
  as that type's own shape everywhere: in the Entity Types & Constraints view, as the shape the
  type page edits and **+ Attribute** writes into, never as one that applies
  "under a condition".

**New shape….** The `+` in the SHACL Shapes view title (also: right-click a type in
Types, the status bar menu) asks what the shape selects — an entity type,
one entity, everything that has an attribute, or everything a Relationship
points at — then the target and a name (suggested: `PumpShape`), and writes
`ns:PumpShape a sh:NodeShape ; sh:targetClass ns:Pump .` into the shapes
file, in the namespace the other shapes use, checked by parsing before it is
kept. Its page opens; attributes and constraints are added there. A type with
no shape of its own offers **Create its shape** in its page's `⋯` (and
**+ Attribute** creates one first anyway).

**Severity — how serious a result is, in SHACL's own vocabulary.**
`sh:severity` says how serious a constraint's result is *when* it fires, not
that it fires, so the pages show it as plain grey text — *severity: critical*
— and red and green mean only what fires and what holds. SHACL gives the
vocabulary: the class **`sh:Severity`** and its three levels, always offered
whether a package declares them or not — **violation** (the default: the data
does not conform), **warning** (reported; the data still conforms) and
**info**. A package adds its own levels as individuals of `sh:Severity`, or of a
class it derives from it, and may derive further classes from those:

```turtle
base:AlarmLevel a owl:Class ;
    rdfs:subClassOf sh:Severity .
base:severityMajor a owl:NamedIndividual, base:AlarmLevel ;
    rdfs:label "major" .
```

A level is said by its `rdfs:label` (else its name). **`sh:Severity` is in the
Knowledge view** as SHACL's own class — its three levels marked *SHACL*,
violation *the default* — with the package's levels of it and the classes
derived from it beneath. Its page shows SHACL's levels read-only (never
"unused": not naming one is no gap) and the constraints that name a severity;
**+ Value** adds a level in the package's namespace, and its `⋯` — like a
derived class's — offers **New severity class derived from …**.

The attribute tables of the type page and the shape page have a **Severity**
column: a click on the cell picks the level (inherited rows show it, changed on
the supertype's shape); an undeclared one reads *violation (default)*, dimmed.
**Severity…** is in a SPARQL check's ⋯ on the shape page and in the workbench's
⋯ too, and in each attribute row's ⋯. It offers SHACL's three, then each class's levels; **No
severity** goes back to SHACL's default; **+ New severity level…** and **+ New
severity class…** are made from the same list, a new level set at once. A
SPARQL check's undeclared severity reads *severity: violation (default)*. The Problems panel reports
an `sh:severity` that is no level (not SHACL's, nor an individual of
`sh:Severity` or a derived class), and a class whose individuals are used as
severities but which is not declared a kind of `sh:Severity` — the kms's
`base:SeverityClass` — with the fix **Declare it a kind of sh:Severity**.

**A rule's evidence, and + New case.** For a shape with a SPARQL constraint
or rule the page says **what it checks** (its `sh:message`, and *severity:
warning* — the kms's own `base:severityWarning` read as a word), how well the cases prove
it (*tested both ways*, *fires in 1*, *never fired*), the cases under
**Tested by**, and **the query**, folded, with its prefixes. A shape that
fires in no case gets **+ New case**: it writes
`examples/test_<Shape>/bad/<name>.jsonld`, copied from a case where the shape
is evaluated and holds (a valid one first, so no other shape's violation comes
along; its includes written into the file, so editing an entity does not
change a shared subobject), and declares it `expect: invalid` with an assert
that the shape fires on that entity. The case fails until you edit its data so
the rule is broken — it cannot pass by accident. With no case to start from it
copies the model's document for an entity the shape reaches. A `sh:rule`
derives data rather than firing, so it gets the query and no + New case.

Validation runs every shape that has a target, of any kind. Until this release
it ran only `sh:targetClass` shapes — a shape written with `sh:targetNode` was
never checked, and nothing said so. `tests/corpus/targets` has one shape per
target kind and pins all of it.

**The vocabulary page: value lists and their care.** A vocabulary class —
MachineState, Wasteclass — is a closed list of named values, and a value is
never just a declaration: `sh:class base:MachineState` makes `hasState` hold
one of them, a SPARQL rule tests for `base:state_ON`, a case writes
`{"@id": "base:state_OFF"}`. A click on a vocabulary class in the Vocabulary
view (or on one of its values, which is then marked) opens its page:

- **The status line**: how many values, how many unused, and what draws
  from the class — the constraint that takes its values from it
  (`MachineShape › hasState (sh:class)`) or lists some of them (`sh:in`),
  opening its shape page; with several, a *Drawn from by* list below. None
  is a warning: nothing checks that an attribute holds one of the values.
- **Values**: each with its label, its other properties as a reader says
  them (*valid for **Machine***, the type a link to its type page; the RDF in
  the tooltip) and where it is used, counted per kind — `7 in data · 6 in
  queries` for state_ON, the places in the tooltip. A value nothing names is
  **unused** and listed last; MachineState has four.
- Folded below: **Properties of its values** (whose domain or range is the
  class; *(no range declared)* where none is) and **Subclasses**.

Managing it happens on the page — **+ Value** at the top, a click on a
label, each value's `⋯` (Label…, Open in .ttl, Delete…), and the page's `⋯`
(Open in .ttl, Refresh):

- **+ Value** asks a name and an optional label and appends
  `ns:name a owl:NamedIndividual, ns:Class ; rdfs:label "…"` in the class's
  file — and its namespace, unless you pick another (below).
- **Label…** (click the label) changes it in place, adds one, or removes it
  when emptied — the rest of the statement untouched.
- **Delete…** removes exactly the value's statement. A value in use shows
  where first and needs **Delete anyway**; each use left behind then names an
  undeclared value, which the Problems panel reports. Adding and deleting an
  unused value leaves the file byte-identical.
- **New vocabulary class…** — in the Knowledge view's `…` menu (its `+` is New
  attribute), on the *Vocabulary classes* row, in the status bar menu —
  declares `ns:Name a owl:Class`, on its own or under another vocabulary class,
  and opens its page.

**Which namespace a new vocabulary term gets.** Every vocabulary "New …" —
class, value, severity level, severity class — asks after the name. The usual
place comes first, so Enter keeps it: beside the class the term belongs to or
derives from, a level of `sh:Severity` in the package's own vocabulary
namespace, a class on its own where most of the vocabulary lives. Each entry
shows the full name it would write (`alerts:Leak`). Then come the namespaces
that already hold vocabulary, then the package's others. Last is
**New namespace…**, which defines a prefix and its IRI for the whole package
right there (as the ➕ on the Package view's namespaces row does) and goes on
with it. Typing `prefix:Name` as the name chooses directly and skips the
question. A term in a namespace its file does not speak yet gets the file's
`@prefix` line with it, so it reads `alerts:Leak`, not `<https://…/Leak>`.
Standard vocabularies (sh, owl, rdf, rdfs, xsd, ngsild) are never offered and
are refused when typed: a level named `sh:Major` would claim to be SHACL's.

**The entity type page.** The trees are for finding things; reading one type's
whole story in them took three views and, for Filter, 39 rows. A click
on a type or attribute in the Entity Types & Constraints view, or on an entity type in the
Knowledge view (also: right-click an entity in the Entities & Test Cases view, or
**SemForge: Open entity type page** in the palette) opens one page in the
editor area — its tab reads `Filter · type` — with all of it:

- **where it sits**: a breadcrumb up the hierarchy (click to open a parent's
  page) and its subtypes;
- **its attributes, own and inherited**, one row each, in the model's words
  instead of SHACL — `required · one`, `number · 0 – 100`, `→ FilterCartridge`,
  `one of MachineState`. Inherited rows are dimmed and say where from;
  sub-attributes sit indented under their parent. Anything the vocabulary
  cannot say is shown verbatim, never hidden;
- **Tested**: whether any test case makes the attribute's constraints fire
  (*both ways* / *fires only* / *never fired* — a constraint that cannot fire
  looks exactly like one that is satisfied);
- **Main-model**: how many entities in the main-model violate it — the `✗ N`
  beside the attribute's name, a click opening the Main page;
- **its rules** (SPARQL), with their message and whether they ever fired;
- **the cases that exercise it** and whether they pass, and **its instances in
  the main-model** with what is wrong with each. A case opens its case page; a
  main-model entity — its id or its violations — opens the Main page scrolled
  to it.

Every name links to its line in the `.ttl` or `.jsonld`. It is one reused tab,
refreshes on save, and is served from the cache.

**Several shapes on one attribute.** A type has no single shape: every shape
that targets a Machine is evaluated against every Machine, and SHACL conjoins
them — an entity conforms only if it satisfies all. So an attribute two shapes
constrain is **one row**, saying what holds when both apply:

```text
Attribute            Presence         Value
Constrained by several shapes · all apply
hasPressure          required · one   number · ≥ 0 and < 100
  ↳ MachineShape     optional         number · ≥ 0 and < 100
                                        sh:minCount 0: no effect
  ↳ MachineShape2    required · one   < 200
                                        sh:maxExclusive 200: no effect
```

The highest minimum and the lowest maximum count win, and so do the tightest
bounds (an exclusive one at an equal value); each shape's line marks what of
it the others outdo. Contradictions are said in red — two datatypes no literal
can have at once, bounds or counts that admit nothing. A shape that applies
only under a condition is listed beneath the row but not merged into it.
Clicking the presence or value of the combined row asks **which shape** to
change; each shape's own line — `↳` and its name — has its own `⋯`. The Entity Types & Constraints view shows the attribute once (`2 shapes, all apply`).

**A shape's name has a random part.** The shape's IRI is its identity, and a
bare `MachineShape` reads like a description — it gets renamed, merged or
reused as if it meant "the Machine's shape". So every shape the editor names
carries a random part: **New shape…** writes `PumpShape-3f9a1c2e`, and a
**Rename…** changes the name and keeps the part (a shape that has none yet gets
one, derived from its IRI). A name another shape is already read as — the
same without its random part — is refused. A constraint is addressed by the
shape, the path and the type, all of the path: an attribute's own
`sh:minCount` and its value's are `hasTemperature/MinCount…` and
`hasTemperature.hasValue/MinCount…`.

**Rename….** A shape's name is written in more places than its declaration,
and a rename that misses one leaves a package that reads as validated and is
not. **Rename…** (right-click a shape in Shapes or Types, or the shape page's
`⋯`) asks the new name — same namespace — and says before writing what
follows it:

- every reference in the shapes and knowledge files: its declaration, another
  shape's `sh:node`, a SPARQL body naming it — rewritten term by term, a
  prefixed name keeping its prefix, an `<IRI>` staying one, nothing else in the
  file touched. It is written only if the shapes graph after is the graph
  before with that one name replaced; anything more and nothing is written;
- every assert naming one of its constraints
  (`iffBaseShacl:StateOnCutterShape/SPARQLConstraintComponent`);
- every pinned residue: the digest names the shape, so each case whose residue
  held before is pinned again — a rename changes no verdict. A case that was
  failing stays failing;
- its suite folder, `test_<Shape>`, if you choose **Rename it and
  test_<Shape>** (and the new name is free) — a convention only, nothing
  depends on it.

A shape that is also a class is refused (that would rename an entity type), as
is a name already taken or one that is not a name. The workbench of the shape
closes, since its query document is named by the shape; the shape page opens
on the new name.

**F2** on a shape's name in a `.ttl` is the same Rename…: the box shows the
name's local part, and the plan, the question and the write are the menu's —
not a text replace, which would leave the asserts behind.

**A rename typed into the file anyway** — the name replaced in `shacl.ttl` by
hand — is noticed when the file is saved: a shape vanishing as one saying
exactly the same appears (compared by what it says, its own name left out) is
that rename. If asserts, a pinned residue or a `test_<Shape>` suite still name
the old shape, a notification says so — *"FilterShape is gone and
FilterCheckShape says exactly what it said. Renamed? 1 assert(s) still name
iffBaseShacl:FilterShape"* — with **Update them** (and **… and rename
test_FilterShape**). A residue is pinned again only when it is exactly the old
one with the old name swapped back in: proof the rename is all that changed
it.

**An assert left behind** — the offer declined, or the rename made before any
of this — says what it most likely meant. When exactly one shape declares the
same attribute and component (`…/hasCartridge/MinCountConstraintComponent`),
the error in `expectations.yaml` and in the Problems panel offers **Rename the
assert to iffBaseShacl:FilterCheckShape/…** first and **Remove this assert**
second; the case page shows the assert as *names no shape* with **Rename to
FilterCheckShape** and **Remove**. Where several shapes declare it (four kms
shapes have a SPARQL constraint), the case page decides by what fires on the
asserted entity; nothing less certain is guessed.

A **test case** (right-click it in Entities & Test Cases, or the case page's `⋯`) is its
file: Rename… moves it, and its expectations entry and any `include` naming it
follow; its asserts and residue do not change, since a case's name is not in
any digest. A **suite** (right-click it) is its folder: nothing inside changes,
and an `include` elsewhere reaching into it follows. Open editors of moved
files are reopened where the files went.

**Delete….** A shape is more than its statement: asserts name its
constraints, a bad case may exist only to make it fire, and residues pinned
on it name it. **Delete…** (right-click a shape in Shapes or Types, or the
shape page's `⋯`) says what goes with it and lets you choose:

- **Delete it, its asserts and the cases** — the asserts naming its
  constraints go, and so do the cases that assert nothing else (with those
  asserts gone they test nothing); a case file another case `include`s is
  kept. Its `test_<Shape>` suite goes too when that leaves it without a case.
- **Delete it and its asserts** — the cases stay, minus those asserts.
- **Delete it only** — the asserts stay and those cases fail, which is how
  you find them.

Only the shape's statement leaves the file: it is written only if the shapes
graph after is the graph before without the shape's own statements (its
inline property shapes included), exactly. Pinned residues it was part of are
pinned again where they held. Refused, with the reason: a shape another
shape reaches through `sh:node` (that reference would point at nothing —
change it first), and a shape that is also a class. Its page and its
workbench close. Deployed, its open alerts close for good after the next
redeploy — the dialog says so.

**Merge into….** Two shapes selecting the same nodes can become one: the shape
page's **Merge into…** button, `⋯ → Merge … into…` on a row, or right-click a
shape in the SHACL Shapes view. It offers only shapes with exactly the same targets,
says what will happen before it writes — per attribute, which parameter is
added, which replaces a weaker one, which is already there or has no effect —
and then:

- where both constrain an attribute with plain parameters, combines them the
  way SHACL does (higher minimum and lower maximum count, tighter bound; a
  stricter value replaces the weaker one *in place*; two different datatypes
  or classes both stay); anything else (sub-attributes, `sh:or`) moves as
  written, as do SPARQL constraints and rules;
- deletes the merged shape, and renames test-case asserts naming it (a pinned
  residue gets a note to run `semforge accept`);
- checks before writing that every constraint either shape declared is still
  declared.

Nothing a validator decides changes; that is what it guarantees, and it is
tested by comparing every violation and every case's outcome before and after
on real merges in the kms. It refuses what would change it: shapes selecting
different nodes, a shape another reaches through `sh:node`, and one with
shape-level settings (severity, data view) to decide by hand.

**Editing on the page.** What is dashed-underlined is clickable, and every
action is a visible button rather than a hover icon:

| On | Click | Does |
|---|---|---|
| your own attribute | **Presence** | how many instances: Optional · Required · Exactly one · **Exactly…** · **At least…** · **Between…** · Any number (`sh:minCount` / `sh:maxCount` on the attribute) |
| your own attribute | **Value** | what the value must be — an entity type, a datatype, a vocabulary class, or any value; ranges and counts are kept. A value written with `sh:or`/`sh:in` is not rewritten by a picker; the tooltip says so |
| your own attribute | **⋯** | New test… · **Constraints…** · add a sub-attribute · remove it from this shape · delete the attribute everywhere · open in `.ttl` |
| your own attribute | **⋯ → Constraints…** | the constraints it carries — change or remove each — and every one it does not carry yet, to add: `sh:minInclusive` (≥), `sh:maxInclusive` (≤), `sh:minExclusive` (>), `sh:maxExclusive` (<), `sh:datatype`, `sh:class`, `sh:nodeKind` (picked from what fits), `sh:minLength`, `sh:maxLength`, `sh:pattern`, `sh:in` (a list: the values of the vocabulary class it draws from to tick, or typed — numbers, "quoted text", prefixed names), and `sh:minCount`/`sh:maxCount` on the attribute (instances) or on the value |
| an inherited attribute | **Override…** | a stricter constraint on this type's own shape — warns when the change could never take effect |
| the header | **+ Attribute** | the attribute picker, for this type's own shape |

Each edit is the same text-anchored, verified write as everywhere else, and
reads like a hand edit: swapping one class for another changes one line, and
nothing leaves a blank line behind. The page and the three trees refresh after
it.

An added constraint lands on its own line, indented like its neighbours; one
already there is replaced, not doubled. A datatype, range, length or pattern
goes on the **value** (on the attribute node it would constrain the blank node
itself and never hold — refused, with that reason); an attribute with no value
layer gets one (`sh:property [ sh:path ngsild:hasValue ; … ]`). Bounds that
together admit nothing (`> 100` and `≤ 16`) are written as asked and said in a
warning. The Value column words them: `> 0 and ≤ 16`, `at most 20 characters`,
`matching ^[A-Z]+$`.

**Counts beyond one.** `sh:minCount` / `sh:maxCount` on the attribute count its
instances — distinct `datasetId`s (see *Several instances* below). The Presence
cell sets any count: *Exactly…* (min = max), *At least…* (no maximum),
*Between…* (both, the current ones offered); the column says it back —
*exactly 3*, *at least 2*, *2 to 4*, *at most 5*, *any number*. **Required**
means *at least one* and keeps a minimum already above it: *exactly 3* made
required stays 3. **Optional** and **Required** leave the maximum alone.

A minimum above the maximum can never be satisfied — every entity the shape
judges would fail, for a reason no data can fix — so every edit that would
leave one (the Presence cell, *Constraints…*, an added count) is refused and
writes nothing. One typed into the `.ttl` by hand is reported on its
`sh:path` (`count-impossible`).

**An `sh:in` list is checked against the rest of the value.** `sh:in` compares
RDF terms exactly, so each item is read as the term it is and checked against
the value's datatype, node kind, class, bounds, lengths and pattern: `"warm" is
xsd:string, but the value must be xsd:double: it can never be given`, `WC9 is
not a Wasteclass`, `150 is outside ≤ 120`. It is said in a warning after the
write and in red on the row — on a combined row too, where the list sits in
one shape and the datatype in another, and two shapes' lists that share no
value admit nothing.

One trap is avoided rather than only reported: Turtle's `20.5` is an
`xsd:decimal`, but a JSON `20.5` in an NGSI-LD document arrives as
`xsd:double`, and the two are never equal — `sh:in ( 20.5 )` rejects every
20.5 there is (measured). So the editor writes a number with a fraction as
`"20.5"^^xsd:double` (or with the value's own `sh:datatype`); a whole number
stays as written, as a JSON whole number arrives. A hand-written list with an
untyped decimal is flagged.

**The cache: why reloading is fast, and how to distrust it.** What every view
and the Problems panel show is stored beside the package, in
`.semforge/cache/views/` (one JSON file per view, never committed — it carries
its own `.gitignore`). Each entry is stamped with a fingerprint of every file
of the package — path, size, modification time, symlinked folders included —
and of the SDK's own code; while that fingerprint holds, a reload serves the
stored result instead of rebuilding it. Any edit, checkout or SDK update
changes it, and the next request recomputes, so nothing stale is served by
design. Measured on the kms: a cold start takes about 4.6 s to have all four
views ready, a reload with nothing changed about 1.6 s (most of it starting
Python).

Parsed Turtle is kept too, in `.semforge/cache/graphs/`: each `.ttl` is
parsed once per content and read back as a term table afterwards — the same
triples and prefixes, in less than half the time (the OPC UA pump package loads
in 3 s instead of 7.4 s; 7.3 MB of cache for 12.8 MB of Turtle). An edit
replaces that file's entry; **Delete cache…** removes it with the views. The
statement index each file needs for "where is this declared" is kept the same
way (`.semforge/cache/index/`).

The first time anything asks about a package — the views, a page, an opened
file — the server loads it, indexes it and starts its validation in the
background, so the first click finds it ready (0.4 s on the pump package). A
click that comes earlier waits for that work rather than doing it twice, and a
page that is still waiting says *⟳ Loading …* instead of staying blank or
showing the page before.

**Validation runs in the background.** A page answers with what it shows —
attributes, shapes, cases, cards — at once, and says *⟳ evaluating…* where a
verdict belongs: the coverage chips, the instances' ✓/✗, a case's pass or
fail, the Problems panel's "fires here". The package is validated once per
version, in a separate process, and every open page fills in when it is done;
after an edit a page shows the last results, marked as such, until the new ones
are in. A page stays editable while it evaluates: results that arrive while an
edit is open (a picker, the timestamp editor) wait until it is done, so the
page is never redrawn under your hands. What an edit changes says *⟳
updating…* from the click until the edit is written — a row, a claim, a card —
and an edit request does nothing else on the server: the Problems panel is
worked out with the validation, in the background, and refreshed when it is
done. After an edit only the files that changed are read again (the knowledge
of the OPC UA pump package is reused as loaded), so the page comes back in a
fraction of a second. The verdicts are cached with the views (`verdicts.json`), so reopening
an unchanged package validates nothing. On the OPC UA pump package a class
page went from 15 s to 0.4 s, the main-model page from 30 s to 0.03 s.

The other half of the old wait was the network: every JSON-LD document names
the NGSI-LD core `@context` by URL, and rdflib downloaded it again on every
parse — 44 times for one Knowledge-view build. It is now fetched once per
machine and kept in `~/.cache/semforge/contexts/`, which also makes scanning
work offline.

The Package view's last row, **Cache**, says how many views are stored and
whether they are current. Its 🔄 **Rescan** ignores the cache and analyses from
scratch; its 🗑 **Delete cache…** removes it after saying what and where —
optionally with the downloaded contexts, which every package on the machine
shares. Both are also in the status bar menu, and Rescan in the SemForge
right-click submenu.

**Sanity: references that point at nothing.** Every artifact names terms the
others are supposed to define, and each link can break without anything
failing — a `sh:path` to an attribute the knowledge no longer declares still
parses and still validates; a SPARQL body reading a removed attribute matches
nothing, which looks exactly like a rule that is satisfied. So the Problems
panel reports each broken link on the line that holds it:

| Finding | Where | Level | Quick fix (💡) |
|---|---|---|---|
| `sh:path` names an undeclared attribute | the `sh:path` line in `shacl.ttl` | error | Declare it · Remove this property shape |
| a data key no knowledge file declares | the key's line in the `.jsonld` | error in a case, info in the scratchpad | Declare it · Remove it from this entity |
| a SPARQL body names an undeclared term of the package's own namespaces | the line inside the query | warning — a query is checked by token, not meaning | Declare it |
| `sh:class` / `sh:targetClass` names an undeclared class | the shape line | error | — |
| an expectation asserts a constraint no shape declares | the `constraint:` line in `expectations.yaml` | error | Remove this assert |
| a declared attribute nothing uses | its declaration in `knowledge.ttl` | info | Delete it… |

**Declare it** opens the New attribute flow with the name and namespace the use
already wrote, so only the type and the kind are asked. **Remove this…** takes
exactly the marked thing and refuses if the file has changed since it was
checked. A file whose last problem is fixed is told so, rather than keeping a
stale squiggle. `semforge test` now says *"a constraint no shape declares"* for
a stale assert instead of *"did not fire"*, and **`semforge check`** reports
the same findings in a terminal — exit 1 on an error (`--strict`: on a warning
too), so a broken link cannot reach CI unnoticed.

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

**The Entities & Test Cases view** (formerly Instances, before that Tests and Model) shows the instance
data the constraints judge — the model's own and the test cases' — in two
groups, because they are judged by different rules:

```
✎ Main    the scratchpad — violations here are information, not failures
   └── main.jsonld                  the model as shipped
🧪 Tests   6 case(s) · all ok
   ├── test_CartridgeShape          1 case(s) · all ok
   └── test_StateOnCutterShape      2 case(s) · all ok
```

Main comes first: it is the model you deploy. The cases are evidence about the
shapes.

**Tests** are the declared cases: each says what it is for, and `semforge test`
passes or fails on it. **Main** is the scratchpad — where you try a violation to
see what a constraint does. It declares nothing and cannot fail a run.

The scratchpad's file is `main.jsonld` (`model-instance.jsonld` still loads —
the kms uses that name), and it may be a directory of documents like any other
role.

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
each gets its own row, named **`attribute[prefix:name]`** — the prefix one the
package registers for the `datasetId`'s namespace — with its own current value:

```
hasStrength                       2 instances
├── hasStrength            0.6 · Property · 4 observations · default   📈
└── hasStrength[sensor:B]  1.5 · Property · 2 observations             📈
```

The case page names its rows the same way.

The default instance is the one *without* a `datasetId` — the platform calls it
`@none` internally (the bridge fills it in, rules write it, and it is stripped
again before Scorpio), but in the data it is simply absent.

**Several instances: what a count counts.** JSON-LD writes an attribute's
instances as an array, but it is a dictionary keyed by `datasetId`, and
`sh:minCount` / `sh:maxCount` count its keys — distinct live `datasetId`s, as
shacl2flink does. Observations of one `datasetId` are one instance.

- **Add instance…** — on a dataset row in the Entities & Test Cases view, and in a case page
  row's `⋯` — asks for a `datasetId` (suggesting one the attribute does not
  have yet) and adds a copy of the current instance under it: valid in
  everything but the count.
- **Add Attribute** asks for the `datasetId` every time, right after the
  attribute: empty is the default instance. An attribute the entity already
  has is not refused — it gets another instance, with the type already
  written; only a `datasetId` the attribute already has is (another one there
  would be an observation: **Add Observation**). When it has a default
  instance, a free `datasetId` is suggested.
- **Which datasetId** is picked the same way in all three: *Default instance*
  (when the attribute has none yet), one of the package's namespaces — then
  only the local part is typed (`left`) — or **New namespace…**, defined for
  the package on the spot. **Its namespace is always a registered one**: that
  is what gives it its `prefix:name`, so a `datasetId` in no registered
  namespace is refused, and there is no free-form IRI. The full IRI is written
  (`https://…/sensors/left`): a prefix from `semforge.yaml` is not in a case's
  `@context`, and `sensors:left` would be read as an IRI whose scheme is
  `sensors` — valid, and silently another id.
- **Remove…** on a case page row that is one of several instances offers
  **Remove hasHeight[sensor:left]** — that instance only — and, separately,
  **Remove hasHeight…** for all of them. Rows are joined to their own
  `datasetId`, so an edit or a removal never lands on another instance.
- **Change datasetId…** renames one instance, every observation of it along;
  empty makes it the default instance (when the attribute has none).
- A `datasetId` must be an IRI: NGSI-LD makes it a URI and the context reads it
  as an `@id`, so `left` would silently resolve against the document's base.
  Both refuse anything else, and `@none`.
- **New test…** writes cardinality cases at the boundary, as many instances as
  that takes, each its own `datasetId` (`urn:<package>:dataset:2`, `:3`, …, in
  a namespace it registers as `<package>Dataset:` the first time):
  a valid case has `sh:minCount` instances, *too few* one less, *too many*
  `sh:maxCount + 1` — two instances would say nothing about a maximum of 3.

Four things in the data are reported where they are written, each with a
quick fix:

| code | what | quick fix |
| --- | --- | --- |
| `dataset-not-iri` | a `datasetId` that is no IRI (error) | Change the datasetId… |
| `dataset-none` | `"datasetId": "@none"` written out: in JSON-LD that is *another* instance, not the default | Remove it |
| `dataset-unregistered` | a `datasetId` in no namespace the package registers: it has no `attribute[prefix:name]` | Register a prefix for its namespace… · Change the datasetId… |
| `dataset-duplicate` | two instances of one `datasetId` with the same `observedAt`, or both without: one update written twice — the platform keeps only the last, so a count over them tests what it never sees | Give this instance its own datasetId… |

**Units (`unitCode`).** An NGSI-LD Property says its unit with `unitCode`, a
UN/CEFACT Recommendation 20 common code — `CEL`, `BAR`, `KMH` — three
characters that say nothing to a reader. So every unit carries its name, its
symbol and the quantity it measures, and **the unit picker searches all of
them**: *temperature* finds `CEL`, `FAH`, `KEL`; *celsius* or *°C* finds `CEL`.

- **The curated set:** about 120 engineering units (temperature, pressure,
  length, area, volume, mass, time, speed, flow, density, force, torque,
  energy, power, electricity, frequency, light, ratio, data), shipped
  read-only like SHACL's severities, under **`qudt:Unit`** in the Vocabulary
  view, grouped by quantity. Its `+` is **New unit…**, its 🔍 **Find unit…**
  (the code goes to the clipboard).
- **The package's own:** **New unit…** asks the code, name, symbol, quantity
  and namespace, and writes a `qudt:Unit` into the knowledge with the same
  terms — `qudt:uneceCommonCode "XKG" ; rdfs:label … ; qudt:symbol … ;
  qudt:hasQuantityKind quantitykind:…`.
- **In the shape — Unit…** in an attribute row's `⋯` (type page, shape page)
  ticks the units its instances may say and whether one is required. It is
  written on the attribute node, where its metadata is:
  `sh:property [ sh:path ngsild:unitCode ; sh:in ( "CEL" ) ; sh:minCount 1 ]`.
  The Value column says it: `0 – 120 · in °C · unit required`. Its
  constraints are named after the attribute — `…/hasTemperature.unitCode/InConstraintComponent`
  — so two attributes' units never share a name, and their violations show on
  the attribute's row.
- **In the data — Unit…** on a dataset row (Entities & Test Cases view) or a case page row sets
  or removes the `unitCode` of that instance, every observation of it along;
  the shape's units come first. **Add Attribute** asks for the unit when the
  shape names some. A case page shows the unit after the value: `21.5 °C`.
- **New test…** writes the allowed unit into a valid case, and offers
  *fires: unit In* (a unit of the same quantity outside the list — `FAH` where
  `CEL` is) and, when one is required, *fires: unit MinCount*.
- A `unitCode` in the data that is neither in the curated set nor the
  package's own is reported (`unit-unknown`), with **Choose the unit…** and
  **Add it as a unit of this package…** as quick fixes.

shacl2flink does not compile a unit constraint yet — it compiles a nested
property shape only with a payload of its own — so the platform neither
enforces it nor raises anything for it; that is part of aligning shacl2flink
with the SDK.

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
value and its time (picked: Now, Just after the latest, or one of your own), joins the series for *its* `datasetId`, and copies
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
Entity Types & Constraints view: that one asks what the *constraint* may say, this one what the
*datum* may be. **Type a value** stays at the bottom.

You can also just type into the picker: what you type becomes an entry of its
own, **Use …**, so a value that is not in the list is one Enter away.

A **relationship** may point at any entity. The picker lists the shape's
entities first, then **other entities** — every other one in the model and in
the file you are editing, each with its type. Below them, typed text is
accepted when it is an IRI: a scheme, a colon, no spaces (`urn:pump:42`,
`https://…`). An entity with that id does not have to exist yet. Anything else
shows as *not an IRI* with the reason, and Enter does nothing until it is
fixed. Linking outside the shape's `sh:class` is allowed; the shape then
reports it, which is what a test of that constraint wants.

Otherwise the input parses JSON, so `42` is a number and
`{"@id": "…"}` a node reference — typing an IRI into a Property should not
quietly produce the string form. The file is rewritten with a one-line diff and
both trees re-validate, which is the reason to edit here rather than in the
JSON: you see the verdict move.

**`current` and `superseded` are worth knowing about.** An attribute resolves to
its latest `observedAt` per `datasetId` before validation, so editing a
superseded observation changes the file and nothing else. Without the marker
that reads as the editor being broken.

**Timestamps (`observedAt`) — only the latest is validated.** The platform's
attribute view keeps, per (entity, attribute, `datasetId`), the instance with
the greatest `COALESCE(observedAt, ts)`; the bridge stamps an instance that has
no `observedAt` with the time it arrives. The SDK validates exactly that:

- per `datasetId`, only the **latest** observation is validated — the older
  ones are filtered out before validation, so an old out-of-range value does
  not fire, and a series never trips `sh:maxCount`;
- an instance **without** `observedAt` counts as **now** and supersedes every
  stamped one of its `datasetId`, as on the platform;
- timestamps are compared as points in time, not as text — `+02:00` or a
  missing millisecond part order correctly — and written in the kms form
  `2024-02-28T13:52:35.000Z`;
- instances tied on time (the same stamp, or several without one) are all
  kept: one update written twice is a duplicate, and still counts.

Timestamps are **never asked by default**; an imported series keeps its own.
When one is wanted:

- on the **case page** (and the Main page), each instance shows its **latest**
  observation — the one validated — and, when it has older ones, a small
  **+N earlier** beside it: a click folds them out underneath, dimmed and
  indented, each with its time, and folds them away again. A click on a time
  (or its ◷) opens a date-and-time panel under the row — UTC, to the
  millisecond — with **Set** (or Enter), **Now**, **Just after the latest**
  of its `datasetId`, **Remove**, and × (or Esc);
- in the Entities & Test Cases view, **Timestamp…** on an instance row offers Now, Just after
  the latest, or a time of your own (any ISO 8601 with its zone);
- **Add Attribute** offers the `datasetId`s the attribute already has: picking
  one adds *another observation* of it, and asks for its time — one none of
  its observations has. **Add Observation** asks the same way.

Four things are reported where they are written, each with a quick fix:

| code | what | quick fix |
| --- | --- | --- |
| `observed-at-invalid` | an `observedAt` that is no timestamp: the platform reads none, so the instance counts as now (error) | Set its time… |
| `observed-at-format` | a timestamp not in the kms form | Write it as `…000Z` |
| `observed-at-mixed` | one `datasetId` with stamped and unstamped instances: the unstamped one counts as now and supersedes them all | Set its time… |
| `observed-at-order` | one `datasetId`'s observations out of time order in the file: Scorpio and the bridge take the **last** one, validation the latest — they would disagree | Sort them by time |

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
`model-instance.jsonld` — or one holding `semforge.yaml`, which declares itself
one. Opening any file inside one activates the service, which walks up to find
the root — an editor hands you a file, not a project. The command line walks up
by the same rule, in the same code (`semforge.package.discover`), so the editor
and CI cannot disagree about which package a file belongs to.

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
| `SemForge: Menu` | everything below, from the status bar item |
| `SemForge: Select Package` | which package the views show; pins your choice |
| `SemForge: Change this setting` | the ✎ on a Project row; writes one line of semforge.yaml |
| `SemForge: Define a namespace prefix` | the ➕ on the Package view's namespaces row |
| `SemForge: Remove this namespace prefix` | the 🗑 on a name; refused while anything uses it |
| `SemForge: Doctor` | what it sees: folder, interpreter, active package, every other package in the window, whether `semforge` imports |
| `SemForge: Go to the SHACL rule for this attribute` | the ⚖ icon on an example attribute; creates an empty `sh:property` when none exists |
| `SemForge: Go to the shape for this class` | the ⚖ icon on a knowledge class |
| `SemForge: Add an entity` | the + on a case or file; the type is picked from the knowledge, never typed |
| `SemForge: Add an attribute` | the + on an entity; the attribute is picked from the knowledge, filtered by `rdfs:domain` |
| `SemForge: New attribute…` | declares an attribute in the knowledge, then (optionally) constrains it on its type's own shape — one flow, from the palette, the status bar menu, the SemForge submenu on a `.ttl`/`.jsonld`, or the Constraints/Knowledge view title |
| `SemForge: Rescan (ignore the cache)` | throws away everything known about the package and analyses it from scratch; also the 🔄 on the Package view's Cache row |
| `SemForge: Delete cache…` | removes the package's cache (optionally the downloaded JSON-LD contexts too), after saying what and where; also the 🗑 on the Cache row |
| `SemForge: Delete attribute…` | right-click an attribute in the Knowledge or Entity Types & Constraints view (or the palette, status bar menu, SemForge submenu); shows every dependent first and removes them all, or names what must be edited by hand |
| `SemForge: Add Attribute to Shape` | the + on a shape in the Entity Types & Constraints view; writes both NGSI-LD layers, optional or required, with the value's class or datatype |

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
