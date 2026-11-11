# Design

## Context

The SemForge VS Code extension (`semantic-model/SemForge-SDK/vscode`)
contributes one activity-bar container with five tree views and opens pages in
the editor area: package, health, type, shape, vocabulary, SPARQL workbench,
and the case and Main model pages. Each tree view sets a fixed heading as its
message. The case and Main model pages show their entities as cards and offer
a graph of the same cards. The extension supports VS Code 1.75 and later.

Nothing about this layout is specified, and no other component depends on it.
The SemForge README describes the views and the pages; it is updated with this
change. No existing specification conflicts with it.

## Decisions

### D1 — The details are a second container, hidden by a context key

- **Chosen:** a second activity-bar container, SemForge Details, whose three
  views are shown only while a workspace-scoped flag is set. Show details sets
  it and opens the container; Hide details clears it. Moved once to the
  secondary side bar by the user, the container stays there.
- *Alternative:* keep one container and mark the three views as collapsed.
  Rejected: their headers still take three rows, and a collapsed view is
  expanded by any reveal into it.
- *Alternative:* contribute the container to the secondary side bar directly.
  Rejected: VS Code 1.75 offers extensions no such contribution point.
- *Alternative:* a setting that hides the views. Rejected: a setting is the
  wrong place for a layout choice made many times a day, and it is shared
  across workspaces.

Hidden views are not rendered, so their trees ask the language server nothing
while hidden. Nothing in the main column reveals into them; the knowledge view
reveals into the constraints view, and both are in the same container.

### D2 — What a view is, is the tooltip of an ⓘ action

- **Chosen:** one command per view whose title is the explanation, shown as an
  ⓘ button in the view's title bar; VS Code shows the title as the button's
  tooltip. Running it shows the same text as a notification, for keyboard
  users. The commands are hidden from the command palette.
- *Alternative:* the view's description beside its name. Rejected: it is
  truncated at the width of a side bar.
- *Alternative:* drop the explanation. Rejected: the views' names alone do not
  say what a click opens.
- *Alternative:* keep the message but only for the first session. Rejected:
  the extension has no reliable notion of a first session per view, and the
  text would vanish for exactly the user who needs it later.

The texts live in one place in the extension; a unit test checks that each
command's title equals its text.

### D3 — Graph first, All for every card

- **Chosen:** *Graph | All*, graph first and the default. *All* names what the
  other view is: every entity, as a card.
- *Alternative:* keep *Cards | Graph* with Cards as default. Rejected by the
  issue: the graph is how a model is read.
- *Alternative:* expand every card of the graph. Rejected: the OPC UA model
  pages would build thousands of cards.

A jump to one entity or attribute keeps going to *All*: there every entity has
exactly one card, so the target is unambiguous and in a known place. Because
the graph is built from copies of the cards, counts and jumps read the cards
of *All* only, and leaving the graph removes its copies.

### D4 — A command category instead of a prefix

- **Chosen:** every command declares the category SemForge and its title drops
  the "SemForge:" prefix; VS Code adds the category in the palette only.
- *Alternative:* shorten the prefix. Rejected: it would still repeat in every
  menu entry.

Command identifiers stay as they are, so keybindings, settings and the
`when` clauses of menus keep working.

### D5 — Settings folded, not removed

- **Chosen:** the Package view's Settings group starts folded; the package page
  remains where settings are read and edited.
- *Alternative:* remove the settings from the view. Rejected: inline editing of
  one setting from the tree is used, and removing it is a feature change.

## Risks

- Users who relied on the five views in one column must find SemForge Details
  once. Mitigation: Show details is a button in the Package view, the README
  explains the columns, and the version becomes 0.2.0.
- Renamed views and commands make older screenshots and notes outdated. The
  README is updated in the same change.
