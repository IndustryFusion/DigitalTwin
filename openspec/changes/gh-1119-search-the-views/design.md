# Design

## Context

The four views are trees the language server answers whole: Entities & Test Cases, Constraints by Type, SHACL Shapes as Written, Knowledge (Ontology). Their answers are cached per package state, in the full form; the summary form, which is the default, is a pass over it. The extension draws the rows and keeps no model of its own. No specification covers searching. `semforge-sdk/editor-layout` restricts what title bars and the space above the rows hold and when SemForge Details is shown.

## Conflict with an existing specification

Three requirements of `semforge-sdk/editor-layout` exclude what the issue asks for and are modified, each only by the search:

- **Title bars hold what creates** allows no button that searches.
- **A view says what it is in a hover** allows no message for a search above the rows. Without one, a filtered view cannot be told from a short one.
- **The details are a second container, shown on request** shows the details only on Show details. Three of the four filtered views are there, and what fits may be in them only.

## Decisions

### D1: The server filters, the views draw

- **Chosen:** the request of a view carries the search text, and the server prunes the answer it has (cached or not) after building it.
- *Alternative:* filter in the extension. Rejected: what a row stands for (its statement, a case's asserts) is not in the answer, and sending it for every row would multiply the answers' size.
- *Alternative:* VS Code's own filter of a tree. Rejected: it fits only rows already drawn, by their label alone.
- *Alternative:* a list of results, as a quick pick or a view of its own. Rejected: it loses where a row is in the model, and the menus of the rows.

### D2: What a row stands for

- **Chosen:** the source text of the statement that declares it, of the property for an attribute row of a shape, and the description and asserts of a case. The text is read once per statement per search, and a shape's properties are split once.
- *Alternative:* the statements of the graph. Rejected: what the user reads and types is the text, with its prefixes.
- A row found that way names the word found, since otherwise nothing on it says why it is there.

### D3: Hidden rows still count for edits

- **Chosen:** a row whose rows are partly hidden still names all of them, in short (what they are, not their own rows). Three edits go by the rows under a row: which instances of an attribute an entity has, which shape is a type's own, and which file of a group an entity is added to.
- *Alternative:* disable editing while searching. Rejected: finding a row to edit it is what the search is for.
- *Alternative:* ask the server before each of these edits. Rejected for now: a second request where the answer is at hand.

### D4: The rows of a search are drawn afresh

- **Chosen:** each row of a search has an id of that search. VS Code remembers by id whether a row was open, and would keep closed what the search opens, and open what it opened after the search is cleared.
- *Alternative:* reveal each row that fits. Rejected: one call per row, and the views scroll.

### D5: One search for all four views

- **Chosen:** one text for the four views, so that a name is found wherever it is used, and one key.
- *Alternative:* a search per view. Rejected: the user would have to know where to look.

### D6: From a line to a page

- **Chosen:** the server answers which page a line is about, from the statement the line is in (Turtle), the entity (JSON-LD) or the declaration (expectations), and falls back to the word at the cursor. The text the editor shows is sent when it is not saved, because its lines are not those of the file.
- *Alternative:* a code lens on every statement. Rejected: it fills the file; a title button and a menu entry are there when wanted.
- A line between two statements belongs to the one before it.

## Risks

- A search on each pause in typing (300 ms) reads the statements of a large package. They are cached with the package's index; only the shapes' property lists are split per search.
- An answer that arrives after the text changed shows no count for it; the next answer does.
