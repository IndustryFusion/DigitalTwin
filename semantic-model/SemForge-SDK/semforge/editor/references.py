"""Find-references: every place in a package that names a term.

The use that matters is the one no text search gets right. From the
owl:ObjectProperty in knowledge.ttl, the references are the `sh:path` that
constrains it, the SPARQL body that reads it, and every example that exercises
it -- and those three spell it three ways: `iffBaseEntities:hasStrength` under
the Turtle file's prefixes, the same inside a query that may declare its own,
and whatever key the example's `@context` expands to that IRI. So matching is
done on the expanded IRI, never on the text.

Nothing here is protocol-shaped; the LSP server translates the result.
"""

import json
import os
from dataclasses import dataclass

from rdflib import URIRef

from ..package.prefixes import canonical_map
from ..rdfio import terms
from ..validate.normalise import local

JSONLD = ('.jsonld', '.json')
# JSON-LD keywords whose values are IRIs. `type` and `id` are only these once a
# context aliases them, which every NGSI-LD context does.
TYPE_KEYS = ('@type',)
ID_KEYS = ('@id',)


@dataclass(frozen=True)
class Reference:
    path: str             # absolute
    line: int             # 1-based
    column: int           # 0-based
    length: int           # characters, so the editor can highlight the term
    declaration: bool     # the subject of a statement about the term
    quoted: bool = False  # inside a string literal: a SPARQL body, say


# --- which term ---------------------------------------------------------------

class _Expander:
    """JSON-LD term expansion, one parsed context per distinct `@context`.

    Parsing a context is the expensive step and every document in a package
    usually names the same one, so they are shared by value.
    """

    def __init__(self, package):
        self.package = package
        self._contexts = {}

    def for_file(self, path):
        """A callable expanding a term as this file would, or None."""
        from rdflib.plugins.shared.jsonld.context import Context

        from ..package.context import resolve_model_document

        try:
            document, _ = resolve_model_document(self.package.path, path)
        except Exception:                          # noqa: BLE001
            return None
        entities = document if isinstance(document, list) else [document]
        value = next((entity['@context'] for entity in entities
                      if isinstance(entity, dict) and '@context' in entity), None)
        if value is None:
            return None
        key = json.dumps(value, sort_keys=True)
        if key not in self._contexts:
            try:
                self._contexts[key] = Context(value)
            except Exception:                      # noqa: BLE001
                self._contexts[key] = None         # an unreachable remote context
        context = self._contexts[key]
        return None if context is None else _expand_with(context)


def _expand_with(context):
    def expand(term):
        # A keyword is itself. rdflib's expand() does not special-case them and
        # runs `@id` through @vocab, which made every {"@id": ...} value
        # invisible.
        if term.startswith('@'):
            return term
        try:
            return context.expand(term)
        except Exception:                          # noqa: BLE001
            return None
    expand.context = context
    return expand


def _known_iris(package):
    found = set()
    for graph in (package.knowledge, package.shapes, package.model):
        for triple in graph:
            found.update(str(node) for node in triple if isinstance(node, URIRef))
    return found


def _is_iri(text):
    return bool(text) and ('://' in text or text.startswith('urn:'))


def iris_named(package, token, path=None):
    """The IRIs the token at the cursor means.

    The token is expanded the way the file it sits in would expand it: a Turtle
    file by its own prefixes, a JSON-LD document by its context, and anything
    else by the package's namespace table. An expansion is trusted even when
    nothing in the package declares the result -- `iffBaseEntities:hasObject`
    is not `ngsild:hasObject` because they share a local name, and answering as
    if it were would send a rename to the wrong term.

    Only a token that cannot be expanded at all falls back to the local name,
    which is what go-to-definition does and which is ambiguous where the corpus
    has two CartridgeShapes -- so all of them are returned.
    """
    token = token.strip().rstrip(':')
    if not token:
        return set()

    expanded = None
    if path and path.endswith('.ttl') and os.path.isfile(path):
        for term in terms(_read(path)):
            if term.raw in (token, f'<{token}>'):
                expanded = term.iri
                break
    elif path and path.endswith(JSONLD):
        expand = _Expander(package).for_file(path)
        expanded = expand(token) if expand else None
    if not _is_iri(expanded) and ':' in token:
        prefix, _, name = token.partition(':')
        namespace = canonical_map(package.path).get(prefix)
        if namespace:
            expanded = namespace + name
    if _is_iri(expanded):
        return {expanded}
    word = token.split(':')[-1]
    return {iri for iri in _known_iris(package) if local(iri) == word}


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


# --- where it is used ---------------------------------------------------------

def _turtle_references(path, iris):
    from ..rdfio import TurtleIndex

    source = _read(path)
    subjects = {block.start for block in TurtleIndex(source).blocks}
    return [Reference(path=os.path.abspath(path), line=term.line,
                      column=term.column, length=len(term.raw),
                      declaration=term.start in subjects, quoted=term.quoted)
            for term in terms(source) if term.iri in iris]


def _jsonld_references(expander, path, iris):
    """Keys that expand to the term, and IRI values that are the term.

    A key is an attribute the entity carries; a value is a type, a vocabulary
    individual (`{"@id": "base:state_OFF"}`) or a relationship target. The
    structure is walked rather than the graph, because the graph has no
    positions and a reference that cannot be opened is not much of one.
    """
    from ..cooked.jsonloc import locate

    expand = expander.for_file(path)
    if expand is None:
        return []
    raw = _read(path)
    try:
        document = json.loads(raw)
        index = locate(raw)
    except Exception:                              # noqa: BLE001
        return []
    lines = raw.split('\n')
    out = []

    def record(address, text):
        line = index.get(tuple(address))
        if not line:
            return
        # The line is the jsonloc's; the column is where the quoted text sits
        # on it, just past the opening quote.
        quoted = lines[line - 1].find(json.dumps(text, ensure_ascii=False))
        out.append(Reference(path=os.path.abspath(path), line=line,
                             column=quoted + 1 if quoted >= 0 else 0,
                             length=len(text), declaration=False))

    def is_iri_valued(key, keyword):
        if keyword in TYPE_KEYS + ID_KEYS:
            return True
        definition = expand.context.terms.get(key)
        return definition is not None and definition.type == '@id'

    def walk(node, address):
        if isinstance(node, list):
            for position, item in enumerate(node):
                walk(item, address + [position])
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key == '@context':
                continue
            keyword = expand(key)
            here = address + [key]
            if keyword in iris:
                record(here, key)
            if is_iri_valued(key, keyword):
                values = value if isinstance(value, list) else [value]
                for position, item in enumerate(values):
                    if isinstance(item, str) and expand(item) in iris:
                        record(here + ([position] if isinstance(value, list)
                                       else []), item)
            walk(value, here)

    walk(document, [])
    return out


def references_to(package, iris):
    """Every Reference to any of the IRIs, shapes first, then the ontology,
    then the data -- the order in which a constraint's story is told."""
    from ..cooked.knowledge import example_files

    iris = {str(iri) for iri in iris}
    if not iris:
        return []
    out = []
    expander = _Expander(package)
    for role in ('shapes', 'knowledge'):
        for path in package.files(role):
            if path.endswith('.ttl') and os.path.isfile(path):
                out.extend(_turtle_references(path, iris))
    for path in example_files(package):
        out.extend(_jsonld_references(expander, path, iris))

    seen, unique = set(), []
    for reference in out:
        key = (reference.path, reference.line, reference.column)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return unique


def used_iris(package):
    """Every IRI some artifact USES -- a shape, a query, a document, or an
    ontology statement about something else. One pass over every file, for a
    question asked of every declared attribute at once ("is this used at all")
    where asking references_to once per attribute would read the package
    twenty times.
    """
    from ..cooked.knowledge import example_files
    from ..rdfio import TurtleIndex

    used = set()
    for role in ('shapes', 'knowledge'):
        for path in package.files(role):
            if not (path.endswith('.ttl') and os.path.isfile(path)):
                continue
            source = _read(path)
            subjects = {block.start for block in TurtleIndex(source).blocks}
            for term in terms(source):
                # A statement's own subject is a declaration, not a use.
                if role == 'knowledge' and term.start in subjects:
                    continue
                used.add(term.iri)
    expander = _Expander(package)
    for path in example_files(package):
        expand = expander.for_file(path)
        if expand is None:
            continue
        try:
            document = json.loads(_read(path))
        except Exception:                          # noqa: BLE001
            continue

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                for key, value in node.items():
                    if key == '@context':
                        continue
                    used.add(expand(key))
                    if isinstance(value, str):
                        used.add(expand(value))
                    walk(value)
        walk(document)
    used.discard(None)
    return used
