"""SPARQL as an editor reads it: tokens with positions, the package's terms,
and the language features built on them -- formatting, diagnostics,
completion, hover -- for the SPARQL workbench's query documents.

Everything here works on the query TEXT, and never changes what a query
means: the formatter checks that the tokens it emits are the tokens it read.
"""
