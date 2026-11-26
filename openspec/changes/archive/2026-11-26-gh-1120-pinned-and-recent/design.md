# Design

## Context

SemForge's pages (type, shape, vocabulary, test case and main model, SPARQL workbench) are opened by commands that take what a view's row carries. Renames of shapes, cases and suites are commands of the extension that know the old and the new name. No specification covers going back to a place.

`semforge-sdk/editor-layout` restricts the title bars of the views. This change puts nothing there: its buttons are at the top of pages, its entries in the menus of rows and in an overflow menu. There is no conflict.

## Decisions

### D1: A pin names the thing

- **Chosen:** kind, identifier and package, plus the file for an entity of a case, since the same id appears in several cases.
- *Alternative:* file and line. Rejected: wrong after the next edit, and it leads to a file, not a page.

### D2: One list

- **Chosen:** pinned first, then recent, in one list that is narrowed by typing. Both answer "back to that one"; the order says which was put there on purpose.
- *Alternative:* a view of its own. Rejected: `semforge-sdk/editor-layout` keeps the main column to the package and its data, and the list is opened for a moment only.

### D3: Kept in the workspace state

- **Chosen:** the editor's state for this workspace. Two people who work on one package pin different things.
- *Alternative:* a file in the package. Rejected: it would be a member of the package or have to be ignored, and changes on every visit.

### D4: Whether a thing is there is asked when the list opens

- **Chosen:** one request per package with all entries. An entry that is gone stays when it was pinned, so that the user decides, and is left out when it was only visited.
- *Alternative:* check after each change of the package. Rejected: work for a list that is closed most of the time.
- Not answered is not gone: a server that is down must not make pins look lost.

### D5: A rename takes the pin along

- **Chosen:** the rename commands tell the list the old and the new name. A suite's rename is a folder's: it moves the files of its cases and of the entities pinned in them.
- *Alternative:* find the renamed thing by similarity. Rejected: a guess that can open the wrong thing.

### D6: The ids on pages

- **Chosen:** the entry is contributed to the context menu of an entity's id, which #1117 gives the ids on pages. Until that is there it shows nowhere; nothing else of this change depends on it.
- *Alternative:* give the ids that menu here. Rejected: two changes to the same markup.

## Risks

- A place is recorded when its page is opened, not when its tab is brought to the front again.
