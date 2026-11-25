Issue: #1119

## Why

A model is worked on in SemForge's views and pages, but these cannot be searched. VS Code's search finds lines and opens files, and from a file no way leads back to the page of what was found. What a row does not say itself (a value in an `sh:in`, a constraint a test case asserts) cannot be found in the views at all, and in a package with hundreds of types the views can only be scrolled.

## What Changes

- **Search…** (a command with a key, and a button on each of the four views that show the model) filters Entities & Test Cases, Constraints by Type, SHACL Shapes as Written and Knowledge (Ontology) while the user types, to the rows that fit and the rows they are under. Each view says how many rows fit.
- A row fits by what it shows or by what it stands for: the statement that declares it, the constraints its case asserts. A row found by the latter says what was found.
- **Clear the search**, on each of those views while a search is kept, shows everything again.
- **Open in SemForge**, for `.ttl`, `.jsonld` and `expectations.yaml` files, opens the page of what the cursor is on; where nothing on the line has a page, it searches for the word at the cursor.
- The title bars of the four views hold the search, a search says its count above the rows, and searching shows SemForge Details.

## Capabilities

### New Capabilities

- `semforge-sdk/view-search`: searching the views, and the way from a file back to its page.

### Modified Capabilities

- `semforge-sdk/editor-layout`: **The details are a second container, shown on request** (a search shows them as well), **A view says what it is in a hover** (a kept search says above the rows how many fit) and **Title bars hold what creates** (Search… and Clear the search are buttons of the four views).

## Out of Scope

- Searching the contents of pages, the Package view, and packages other than the one shown.
- Replacing, and expressions such as wildcards or regular expressions.
- Keeping a search across window reloads.
- Pinned and recent places (#1120).

## Impact

- Components: SemForge SDK (language server: the four views' answers take a search; which page a line of a file is about), the SemForge VS Code extension and its README.
- No contract between components changes: the package format, the test runner and the command-line tools are untouched.
- No new dependency.
