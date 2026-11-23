# Design

## Context

A package's tests are run by one function of the SDK, which `semforge verify --tests` and `semforge publish` share: it loads the package, composes every example and validates it with the package's shapes, knowledge and rules. Three places evaluate SPARQL from the package: the SHACL validator (SPARQL constraints and validators), the rule expansion (SPARQL rules) and the SDK's own evaluation of SPARQL targets. rdflib, which runs all of them, evaluates `SERVICE <url>` by an HTTP request to `url`.

JSON-LD contexts go through one fetch function of rdflib, which the SDK already wraps to keep fetched contexts in a per-user cache. The package's own published context URL is already answered from its local context file when a model is read. The NGSI-LD core context, which every package's local context names, is not inside any package; today it is fetched once and then read from the per-user cache. The NGSI-LD vocabulary a package names (`ngsild: {source, sha256}`) is a file inside the package or a remote URL, fetched through the dependency machinery into the package's `.semforge/cache/deps`; a vocabulary that does not load is a finding, and the package loads without it.

Conflict with existing specs: none. *Packages are standalone* already says checking a package needs no fetch; this extends that to running its tests. *Verification can run the tests again* and *Publishing runs the tests* keep their behaviour for a package that needs no network.

## Goals / Non-Goals

**Goals:**
- No connection is opened while a package's tests run, except a context or vocabulary fetch the caller allows.
- A refusal names what needs the network: the constraint, rule or target, or the context URL, and for an undeclared own context the `kms.yaml` line to add.
- The same result with and without that permission for every package in `semantic-model/kms`.

**Non-Goals:**
- A sandbox for the file system, processes or resources.
- Offline evaluation in the editor and the other commands.

## Decisions

### D1: SERVICE is found in what rdflib parses

Before the examples run, every SPARQL text of the shapes (`sh:select`, `sh:ask`, `sh:construct`, `sh:update`) is parsed with rdflib's own grammar, as the SHACL engine runs it: with the declared prefixes in front, and with a path in place of `$PATH`. Every federated query pattern in the parse tree is reported with its target and owner: a SPARQL constraint as `<shape>/SPARQLConstraintComponent`, the name coverage uses; a rule or a target by its shape; a validator by its constraint component. A text that does not parse is refused too, by its owner, since what it would do is not known. Escapes (`\u0053ERVICE`), comments and spacing are the grammar's business.

While the tests run, rdflib's evaluation of `SERVICE` is also replaced by a refusal, for a query the scan does not see. Code on the way may swallow the exception (the SDK's target evaluation does), so every refusal, this one and those of D3 and D4, is kept for the run, which fails on it at the end.

*Alternatives:*
- Search the text for the keyword: the search and the parser read it differently (`SERVICE:sparql { … }`, `FILTER(?b<2).SERVICE?u`, an escaped quote in a local name), and each difference is a way past.
- Only replace the evaluation: the error names no constraint, and a query that no example reaches passes.

### D2: SERVICE is rejected everywhere, also with --allow-network

Every `SERVICE` found by D1 fails the tests, in a constraint, a validator, a rule or a target, whatever the caller allows. In a constraint SHACL does not allow it (the queries it pre-binds must not contain `SERVICE`), and the validator refuses such shapes; with the network allowed the run ended in a traceback. The platform's validation, which shacl2flink compiles to Flink SQL, has no translation for `SERVICE` and cannot run it. And a package's results must not depend on what a remote endpoint answers: the release record would then describe that day, not the version.

*Alternatives:*
- Refuse `SERVICE` in rules and targets only offline, and let `--allow-network` run them: a package could then publish results nobody can reproduce, for a query the platform never runs.
- Refuse it only in constraints, where SHACL forbids it: the same objection for rules and targets.

### D3: An audit hook stops every other connection

While the tests run, an audit hook refuses every socket connection, datagram and host name lookup, and every `urllib` request, made by the thread that runs them. With `--allow-network` only the SDK's own fetch of a JSON-LD context (D4) or NGSI-LD vocabulary (D6) is let through, and only its `http(s)` requests; everything else stays refused. This is the mechanism rdflib's security notes recommend. Audit hooks cannot be removed, so the hook is installed once and does nothing outside a test run; it applies to the running thread only, so a server thread in the same process (the editor, a test's listener) is not affected.

*Alternatives:*
- Replace `socket.socket.connect` while the tests run: process-wide, so it also breaks other threads, and every library that keeps its own reference is missed.
- Rely on D1, D4 and D6 alone: a fetch nobody foresaw (a future rdflib feature) would still reach the network.

### D4: Contexts resolve from the package or the SDK's pins

The model keeps naming its published context URL; the file on disk is not rewritten. In a test run the fetch function answers that URL from the local context file `kms.yaml` declares for it, a remote context the SDK ships from its pinned copy, and refuses any other URL, naming it. When the model names a URL as its own context (an entity whose `@context` does not name the declared published URL) and `kms.yaml` does not declare it, the refusal says to add `published: <url>` under `context:` in `kms.yaml`, with `local:` naming the file that holds it. The function always returns the document or refuses, so rdflib opens nothing, wherever a context is named (a string, a list, `@import`, a term's or type's own context, another context file): it has one fetch function. A file context must be `file:///` followed by a file name, in any case of the scheme; the name is all the rest, unquoted, `#` and `?` included, as rdflib takes it. It is resolved through every link, must lie inside the package root, must be a regular file, and is read there. Any other URL is refused, with `--allow-network` too, and so is one that cannot be read with certainty. The per-user cache is not read, also with `--allow-network`: a result must not depend on what this machine fetched before. The SDK ships the NGSI-LD core context v1.8 (the version `semforge init` writes and `kms/example` names) byte for byte as `https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld` serves it, with its SHA-256 checked on every read (the file is read and hashed again each time; it is 11 kB). The same JSON, with LF line endings, is `coreContext/ngsi-ld-core-context-v1.8.jsonld` in ETSI's Forge repository `data/ngsi-ld-openapi` at tag `v1.8.1`. ETSI publishes its JSON-LD context files there under BSD-3-Clause (the Forge default, with ETSI as copyright holder); the repository's `LICENSE` ("Copyright 2024 ETSI") ships beside the file and `Notice.md` lists it. With `--allow-network`, other contexts are fetched; the package's own and the shipped ones still answer first. The fetch is the SDK's own: an opener with no handlers but http and https, whose redirects are checked the same way (at most 5), 16 MiB and 30 s, no `Link` header followed, and a JSON document whatever its media type.

*Alternatives:*
- Read the per-user cache offline: offline then means "whatever was fetched last", which differs between machines and CI.
- Check the URL and let rdflib open it: the check and rdflib read it differently (`HTTP://`, `FILE:`, a `#` in a file name), and each difference is a way past.
- Let rdflib fetch what is allowed: it follows a `Link` header to a local file and a redirect to `ftp:`.
- Ship every published version of the core context: only v1.8 is named by a package here; a new version is pinned when a package names it.
- Require each package to carry the core context: every package would hold the same standard file, and each copy could drift.

### D5: One flag, `--allow-network`, for contexts and the vocabulary only

`semforge verify --tests` and `semforge publish` take `--allow-network`, in the style of the existing long options. It lets the tests fetch remote JSON-LD contexts and NGSI-LD vocabularies the package and the SDK do not hold, and nothing else: `SERVICE` stays rejected (D2), and every other connection stays refused (D3). When the tests cannot run for any reason (a refusal, a shipped copy that fails its hash, shapes the validator refuses, any error of the parsers or the evaluation), both commands report it as "tests do not run" with the reason and exit with code 2; `publish` writes nothing. An example that does not meet its expectations is reported as before.

*Alternatives:*
- A declaration in `kms.yaml` that the package needs the network: the package could then grant itself the access the caller is meant to decide on; the refusal already says what needs it.
- Lifting all network refusals with the flag: a fetch nobody foresaw would then pass unnoticed in exactly the runs where the caller only meant contexts.

### D6: The NGSI-LD vocabulary resolves like a context

In a test run a remote `ngsild.source` is answered from a copy the SDK ships when it is the official URL `semforge init` pins by default (`https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl`, sha256 `b4b2e04e…`), byte for byte as that URL serves it, hashed on every read. Any other remote vocabulary is fetched only with `--allow-network`, as a context is (D4), and never read from or written to any cache or file during a test run: the bytes that were verified are parsed. A local one must be inside the package. `SEMFORGE_NGSILD`, the machine's default for packages that name no vocabulary, is ignored: the official one applies. A vocabulary that does not load fails the run, naming its source: the tests would otherwise run with no NGSI-LD term declared, which in an extracted archive (no cache) was always the case for a remote one.

The file is IndustryFusion's own: `staging/ontology/v0/ngsild.ttl` in `github.com/IndustryFusion/contexts`, a link to `staging/ontology/v0.1/ngsild.ttl`, whose content at commit `79edb472` is the shipped file. That repository is licensed under Apache-2.0 since that commit (IndustryFusion/contexts#74), as this one is, so the file is not listed in `Notice.md` as third-party software.

*Alternatives:*
- Read it from the package's dependency cache: an extracted archive has none (`.semforge/` is not a member), so an archive's tests would still depend on the network.
- Keep reporting a vocabulary that did not load as a finding and run on: the results then differ from a networked run without saying so.

### D7: Examples are read only from inside the package

While the tests run, an example or include path that resolves outside the package root (`..`, an absolute path) fails the run, naming it. The package check already refuses such paths since #940; this guards every caller of the test run, such as a direct call. The path is compared as written, made absolute: a symbolic link inside a package directory is its author's (an archive holds none).

*Alternative:* compare resolved real paths: the SDK's own test corpus links its examples into `kms/example`, and so would a package directory that shares examples by a link.

## Risks / Trade-offs

- A package naming another NGSI-LD core context version fails offline until the SDK ships it, or runs with `--allow-network`. The refusal names the URL.
- A package that used `SERVICE` in a rule or target can no longer be tested or published. None in `semantic-model/kms` does.
- The shipped core context is a third-party file (ETSI, BSD-3-Clause) inside the SDK; the licence scan sees it, and `Notice.md`, which FOSSA generates, keeps its hand-written entry only if a regeneration keeps it.
- A package naming a remote NGSI-LD vocabulary other than the official one cannot run its tests offline; the refusal names it. A package should carry its vocabulary (*Packages are standalone*); `kms/example` does.
- A new official vocabulary version needs a new shipped copy; until then a package pinning it fails offline, named.
