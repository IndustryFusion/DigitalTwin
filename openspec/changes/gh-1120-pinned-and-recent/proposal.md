Issue: #1120

## Why

Working on a model means going back and forth between a few things: the shape being written, its type, the case that should fail, an entity. SemForge keeps none of them at hand; each time they are found again through a view. VS Code's history and bookmarks know files and lines, not shapes, entities or pages, and a line number is wrong after the next edit.

## What Changes

- **Pinned and recent…** (a command with a key) lists what the user pinned and, after it, the places visited last. Choosing one opens its page.
- **Pin this page** / **Unpin this page** at the top right of SemForge's pages; **Pin or unpin** in the menu of a view's row and, where an entity's id on a page has a context menu, in that; **Pin** in the ⋯ menu of an attribute and of a SPARQL query on a type page.
- A pin names the thing, follows a rename done in SemForge, and says when the thing is gone. A recent place that is gone is not listed.
- Pins and recent places are kept in the user's workspace state. Nothing is written into the package.

## Capabilities

### New Capabilities

- `semforge-sdk/pinned-and-recent`: the pins and recent places, what they name, and what happens when that is renamed or gone.

### Modified Capabilities

## Out of Scope

- Sharing pins, or keeping them in the package.
- Following a rename done outside SemForge, or of an entity or term (its pin is shown as gone and can be searched for).
- Folders, names or an order of one's own for pins.
- Giving the ids on pages a context menu (#1117).

## Impact

- Components: the SemForge VS Code extension and its README, and the SemForge SDK's language server (whether what a pin names is still in the package).
- Uses the search of #1119 (`semforge-sdk/view-search`) for a pin whose target is gone, so it is implemented after that.
- No contract between components changes. No new dependency.
