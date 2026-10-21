# Corpus: the production KMS

`knowledge.ttl`, `shacl.ttl` and `model-instance.jsonld` are **symlinks** into
`semantic-model/kms/`, not copies. The fixture cannot drift onto last month's
shapes; a copy is how the sql-core chart ended up running SQL the generator had
already fixed.

`context.jsonld` is the exception: a vendored snapshot of
`https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld`,
which is what the model's `@context` points at.

It is vendored because the shipped KMS **cannot be compiled without fetching
that URL**. `create_sql_checks_from_shacl.py` needs a local context, and the
model names a remote one, so a build of the model as shipped depends on the
network and on whatever that URL serves today. That is the same class of
supply-chain problem as `make ontology2kms`'s `wget -r` (architecture.md section
13), and it is why `semforge export` copies a context into its output and the
cross-check refuses to run without one rather than fetching silently.

Being a snapshot, it can drift from the URL. That is the trade for a build that
is reproducible offline, and it is the reason a package should declare its
context as a versioned dependency rather than a bare URL.
