# Proposal

Issue: #950

## Why

The SemForge VS Code extension stacks five views in one side bar: Package,
Entity Types & Constraints, SHACL Shapes, Entities & Test Cases and Knowledge
(Ontology). A modeller mostly works with the package and its entities and test
cases; the constraint, shape and knowledge trees are details that the pages
already link to. In a narrow side bar five views leave each only a few rows.

Each view also starts with a paragraph saying what it is. It helps once, but it
is always shown and costs rows in every view; the Main model page has the same
kind of paragraph above its violation list. The entities of a page open as a
flat list of cards, although a model is read along its relationships. And the
menus are uneven: "SemForge:" in front of almost every entry, several names for
one kind of action, title bars with five buttons, the same welcome text five
times.

## What Changes

- **Two columns.** The SemForge side bar holds Package and Entities & Test
  Cases. Constraints by Type (formerly Entity Types & Constraints), SHACL
  Shapes as Written (formerly SHACL Shapes) and Knowledge (Ontology) move to a
  second container, **SemForge Details**, which is hidden until the user asks
  for it and remembers that choice per workspace.
- **Explanations become hovers.** What a view is becomes the tooltip of an ⓘ
  in its title bar; the top of a view shows only what is wrong or in progress.
  The paragraph above the Main model page's violation list becomes a hover.
- **Graph first.** A page's entity bar reads *Graph | All*; the graph is what
  the page opens on, *All* lists every entity as a card. A jump to one entity
  shows it among all the cards. Counts and jumps treat every entity once,
  whichever view is open.
- **Calmer menus.** Menus drop the "SemForge:" prefix while the command palette
  keeps it; one verb per kind of action; title bars hold what creates and the
  ⓘ, while refresh and the health and settings pages move to the overflow menu;
  "New attribute…" is offered once.
- **A shorter Package view.** The full no-package welcome text appears in the
  Package view only, and its Settings group starts folded.
- The extension's version becomes 0.2.0.

## Capabilities

### New Capabilities
- `semforge-sdk/editor-layout`: How the SemForge VS Code extension arranges its
  views, says what they are, presents the entities of a page, and names and
  places its commands.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK/vscode`): view containers, view
  names, title-bar actions, command titles, the case and Main model pages'
  entity bar, the README, and the version (0.2.0). View and command
  identifiers do not change, so keybindings and settings keep working.
- The language server, its requests and the `semforge` command line are
  unchanged.
- No change to any other component, image, chart or deployment.

## Out of Scope

- Page latency: pages validate the whole package synchronously (about 15 s for
  a type page and 30 s for the Main model page of the OPC UA package). It needs
  an issue of its own.
- Changing what the pages show beyond the entity bar and the violation-list
  hover.
- New editing features.
- Placing SemForge Details in the secondary side bar automatically; the
  supported VS Code versions do not let an extension do so.
