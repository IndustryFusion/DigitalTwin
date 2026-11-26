# Design

## Context

The Main page and a test case page draw their entities as a graph: roots are
the entities nothing on the page points at, and a circle nothing points into is
entered at its first entity; a relationship row opens the card it points at
below it, and an entity is shown in full once (`semforge-sdk/editor-layout`,
"Pages open their entities as a graph"). The graph is drawn by the page itself
from the entities and relationships the page carries; the extension and the
language server only fetch the page. A page's webview is redrawn whole by a
validation that finishes, by an edit, and when its tab is shown again.

## Decisions

### D1: The path is found by the page
- **Chosen:** the page's script walks backwards from the entity over what points
  at it until it meets a root, breadth first (shortest first), each path without
  an entity twice. At most 20 paths are shown and 20,000 steps taken; one
  path more is looked for, so "or more" is said only when there is one, or
  when the step bound stopped the search with paths left. Without any within
  the bound, the first shortest path is taken with each entity seen once.
- *Alternative:* the language server finds the paths. Rejected: the page has
  exactly the entities and roots it draws; a server answer could disagree with
  what is drawn (filters, two definitions of an id) and costs a request.
- *Alternative:* all paths. Rejected: a model of layers that point at all of the
  next has millions.

### D2: A root is a root of the graph
- **Chosen:** a path starts where the graph starts: at an entity nothing points
  at, or at the entity a circle nothing points into is entered at. So every
  entity has a path; an entity of such a circle, or one only pointing at
  itself, is its own path, shown by itself.
- *Alternative:* only entities nothing points at. Rejected: an entity of a
  circle would have no path though the graph shows it below a root.

### D3: Which page
- **Chosen:** a row under a test case opens that case's page; a row under Main,
  an instance on a type page and an id on the Main page open Main; the cases of
  a shape page their case. A row of Knowledge knows only its file: the server
  says whether it is a case, a model file, or included by a case (the first
  that includes it, resolved as the case reads it), comparing real paths. A page already showing the entity's
  page is asked to show the path, without fetching it again.
- *Alternative:* the search's "page at a line" request. Rejected: not on main,
  and a line is not what a row knows.

### D4: The path survives a redraw by what the page remembers
- **Chosen:** each time the extension opens a page somewhere, the page gets a
  number with it. The page remembers the path, which of the paths, the cards
  shown in full, what else was opened, the scroll and the number it last
  followed, also from a message. Drawn again with the same or an older number
  (a tab shown again re-runs what it was first drawn with), it shows what it
  remembers -- path, filter, view, scroll -- takes neither the focus nor the
  scroll, and neither says nor jumps again; only a newer number is followed.
  A path not yet seen (the first second) is gone to again.
- *Alternative:* the extension keeps the request until the page says it landed,
  or until someone works on the page. Rejected: the tab shown again re-runs the
  page with what it was rendered with, and a page opened at an entity jumped
  back to it on the next redraw, losing the path.

### D5: An entity of two files
- **Chosen:** a path goes over cards, not ids: when a case and the file it
  includes both define an id, the path goes by the card whose relationship
  leads on, and each of the definitions of the entity can be a path's end.
- *Alternative:* by id. Rejected: the card with the relationship need not be
  the one the graph draws, and the path broke off.

### D6: Ids as written
- **Chosen:** ids are matched as the page's files write them; a relationship
  row carries the id it points at as written, besides the value it shows
  (a prefixed id is shown without its prefix). A card also carries its id
  spelled out by the package's names, which is how type and shape pages name
  it, and a use in Knowledge names the id as each file writes it, so it finds
  its files. Only a relationship to one id -- a string or `{"@id": …}` -- is an
  edge and offers a reveal; a list does not. Everything an id carries into a
  page is escaped, its menu context too.
- *Alternative:* expand ids by the context. Rejected: the graph and the pages
  match by the id as written today; this change does not change that.

### D7: A button, and the right click
- **Chosen:** a real button (Enter and Space, a label naming the id), coloured
  as a link in both themes with a focus ring, beside every id; and the webview's
  context menu. The default items of that menu (Copy) stay.
- *Alternative:* a link with role=link. Rejected: Space does nothing on it.

### D8: Copy on a page's id comes after #1110
- **Chosen:** the copy commands of #1109 are offered on the same context of an
  id. What is copied is the entity as the page has it: on a case or Main page
  the card's file, on a shape page its case, else the main model. Done as the
  last step, when #1110 is merged.
- *Alternative:* wait with the whole change. Rejected: the reveal does not need
  copy.

## Risks

- The bound can hide a path longer than the shortest ones; it is said ("or
  more") and the shortest is always shown.
- A webview's remembered state is gone when its panel is closed; a closed page
  opens as asked.
