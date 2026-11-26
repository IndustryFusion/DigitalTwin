# Tasks

## 1. The check

- [ ] 1.1 Find shacl2flink (`SEMFORGE_SHACL2FLINK`, beside the package, beside SemForge), load its check of SPARQL expressions in process with its modules kept apart, and ask it for a package and for a draft query; verify unit tests for "Named", "Beside the package", "No checkout", "A checkout that cannot be loaded" and that every query of the kms corpus can be deployed ("Every query can be deployed")
- [ ] 1.2 Mark a refused query in the editor at the line of the compiler's pattern, only when it has no other error, never failing the diagnostics; verify unit tests for "A variable as predicate", "The line of the pattern", "A rule", "Two target classes", "Parts the compiler refuses", "Forms that compile", "A query that does not parse" and "The check fails"
- [ ] 1.3 Report each refused query of a package as `SF-CAP-006` and as a `not-deployable` row of `semforge check`; verify unit tests for "In the Problems panel", "A rule in the Problems panel", "In the terminal", "Export" and "Every query can be deployed"

## 2. What goes

- [ ] 2.1 Remove the findings `explicit-node`, `path` and `not-compiled`, their quick fixes, the hover line, the command `semforge.nestForFlink` (its registration, its menu entry and its tests), and the claim on shacl2flink of `variable-node`; verify unit tests for "A named instance and a path", "An attribute no shape nests a payload for" and "The attribute instance read instead of its value", and that the extension's command list no longer has the command
- [ ] 2.2 Describe it in the SemForge README; verify by reading it

## 3. End to end and checks

- [ ] 3.1 Add an end-to-end test in VS Code that writes a query with `$this ?attribute ?value .`, sees the mark at that line with its reason, and sees it go when the query reads the value ("A variable as predicate", "Fixed while written"); verify it passes
- [ ] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass and that more than 80 % of the changed code is covered
