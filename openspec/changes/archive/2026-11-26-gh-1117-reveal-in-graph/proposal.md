# Proposal

Issue: #1117

## Why

In a package with hundreds of entities the graph on the Main page is too large
to see how one entity is reached. Its id is shown in many places -- the views,
the Main page, a test case, type and shape pages -- and from none of them can
the entity be found in the graph.

## What Changes

- **Reveal in graph view** on an entity's id: on its row in Entities & Test
  Cases and Knowledge (right click), and on every id a page shows (right click,
  or the ⌖ button beside it). It opens the page that holds the entity: its test
  case, or Main.
- **Only the path** from a root of the graph down to the entity is shown: of
  each card on the way the relationship it goes on by, the entity whole and
  marked. Several paths are stepped through, shortest first and bounded; the
  rest of a card and the whole graph are one click away.
- **Circles end**, an entity no root leads to is shown by itself, and the path
  **stays when the page is redrawn** by a validation, an edit or its tab shown
  again.
- **Copy entity** and **Copy with subtree** are offered on a page's ids as well,
  once copy and paste (#1109, PR #1110) is merged.
- One language server request: which page shows a data file.

## Capabilities

### New Capabilities
- `semforge-sdk/entity-graph`: finding an entity in the entity graph of a page
  by the path to it. Not part of `semforge-sdk/editor-layout`, which arranges
  views, pages and commands and decides which view a page opens on; this one
  is about what the graph shows of the entities and their relationships, and
  where an entity is found from.

### Modified Capabilities
- `semforge-sdk/editor-layout`: "Pages open their entities as a graph" says a
  page opened at an entity shows All; revealing an entity is the exception and
  shows Graph.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the extension (`vscode/src`:
  the case, type and shape pages, the Entities & Test Cases view;
  `package.json`: two commands, their menus, a webview context menu) and its
  README; one language server request (`semforge/pageOfFile`); a row of a page
  carries the id a relationship points at as written. No new dependency.
- No change to the `semforge` command line, to any other component, image,
  chart or deployment.

## Out of Scope

- Showing the Main page and a test case side by side.
- Relationships whose object is a list, and entities inlined in a
  relationship: they are no edges of the graph today and are not of the path.
- A path across pages: from a test case into the main model, or between
  packages.
- Searching for an entity by name; removing an entity.
