# Design

## Context

A list is written in the shapes file as Turtle and read by the editor item by
item. The editor's form has one text field per condition; what is typed is split
at commas and each part taken for a number, a boolean, a quoted text, a prefixed
name or a text. Nothing it shows can be typed back reliably.

## Conflicts

None with approved specifications. #1087 (in progress) changes how the items of a
list are read (quotes of either kind, escapes, comments, datatypes given as IRIs);
this change reads items with it, so that there is one reading.

## Decisions

### D1: Rows with a kind instead of a better text syntax
- **Chosen:** each value has a row with its words and its kind.
- *Alternative:* show and accept Turtle correctly. Rejected: a modeller would have
  to know it, and a comma or quote in a text needs escapes.
- *Alternative:* comma separated texts. Rejected: no text with a comma.

### D2: The datatype decides the kind, then what was typed
- **Chosen:** as in the specification; the user can overrule it.
- *Alternative:* always ask. Rejected: one more question per value for what is
  nearly always clear.

### D3: An item carries what it is
- **Chosen:** an item goes to the editor with its words, its kind and, where the
  words do not tell it, its datatype or language, and comes back with them while
  its kind is not changed. So an untouched item is written as the term it was.
- *Alternative:* send the items' Turtle along and write it back verbatim.
  Rejected: what the editor sends would be written into the shapes unread.
- A new number follows the value's datatype; without one, a number with a fraction
  is an `xsd:double`, as a JSON number arrives, as before.

### D4: The row's text field stays
- **Chosen:** a list changed from the parameters of a type page's row keeps its
  text field, which reads a list written as Turtle as that list.
- *Alternative:* the row opens the attribute editor at the list. Deferred: opening
  it at the list while the panel may be drawn again meanwhile needs its own design.

## Risks / Trade-offs

- Two values of different kinds can read the same (the text `1`, the number 1).
  The rows say the kind.
