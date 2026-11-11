# Tasks

## 1. Two columns

- [ ] 1.1 Contribute the SemForge Details container with Constraints by Type, SHACL Shapes as Written and Knowledge (Ontology), shown under a workspace-scoped flag; keep Package and Entities & Test Cases in the SemForge side bar; verify unit tests on the manifest for "Opening a package" and "Details hidden by default", and that every view still has its activation event
- [ ] 1.2 Add Show details and Hide details and keep the choice per workspace; verify an end-to-end test that runs both commands, and a manual check of "The choice survives a reload"

## 2. Explanations as hovers

- [ ] 2.1 Add one ⓘ command per view whose title is the view's explanation, place it in the view's title bar and hide it from the palette; stop setting the explanation as the view's message; verify a unit test that each ⓘ title equals its text and is in its view's title bar, and unit and end-to-end tests for "A healthy package"
- [ ] 2.2 Keep the message for no server, no package, a failed request and a running validation; verify the existing tests for those messages and the scenario "The language server is not running"
- [ ] 2.3 Turn the explanation above the Main model page's violation list into an ⓘ hover; verify a page-rendering test for "Main model page with violations"

## 3. Graph first

- [ ] 3.1 Make the entity bar *Graph | All* with Graph as the default; verify page tests in headless Chromium and an end-to-end test for "First opening of the Main model page"
- [ ] 3.2 Keep jumps to an entity, an attribute or a violation going to All; verify the page tests for "Opened at an entity" and "A violation in the list" with Graph as the page's view
- [ ] 3.3 Count and jump on the cards of All only, and drop the graph's copies when it is left; verify the page test for "Filtering while the graph is open"

## 4. Menus and the Package view

- [ ] 4.1 Give every command the category SemForge, remove the prefix from the titles, and apply sentence case, no "+" titles and "Add" for adding to an existing item; verify a unit test that every command has the category and that no title starts with "SemForge:" or "+"
- [ ] 4.2 Put creating actions, the package selection, Show details and the ⓘ in the title bars, and refresh and the health and settings pages in the overflow menus; offer New attribute… in Knowledge (Ontology) only; verify unit tests on the manifest for "The Package view's title bar" and "New attribute offered once"
- [ ] 4.3 Give only the Package view the full no-package welcome text and fold its Settings group; verify a unit test on the welcome contents and a tree test for "Settings folded"

## 5. Version and documentation

- [ ] 5.1 Raise the extension's version to 0.2.0 and let the packaging test read the version from the manifest; verify `vsce package` writes `semforge-0.2.0.vsix` and the packaging tests pass
- [ ] 5.2 Describe both columns, Show and Hide details, the ⓘ and *Graph | All* in the SemForge README, with the new view names throughout; verify by reading the rendered README
- [ ] 5.3 Run the unit suite and the end-to-end suite; verify both pass, and compare any end-to-end failure with the same tests on the default branch
