"""Every attribute a document uses must be one the knowledge declares.

An entity's TYPE decides which shapes judge it; an attribute's NAME decides
which `sh:path` matches it. So an attribute spelled wrong is not a broken
document -- it is an invisible one. Nothing rejects the key, no property shape
selects it, the constraint that should have judged the value never fires, and
the case passes having proved nothing. It is the same silence as a constraint
that cannot fire (§7.5), reached from the other side.

The shipped kms has five, and they are worth reading as a set:

  * `hasList`, `hasTrust`, `hasXXXWorkpiece` -- a shape constrains each of
    them, so the terms are real and only the declaration is missing;
  * `hasJSON` -- used in the scratchpad, constrained by nothing, declared
    nowhere;
  * `hasOutWorkpiecexx` -- two letters away from `hasOutWorkpiece`, which is
    declared, constrained and used. Exactly the typo this check exists for, in
    the corpus, unnoticed.

Where it is used decides how loud it is. A declared case that uses an
undeclared term proves nothing, so that is an error. The scratchpad is the
place to try things and cannot fail by design, so there it is reported and
left alone -- the same rule the Model view already draws between Tests and
Main.
"""

import json
import os
from dataclasses import dataclass, field

from .identity import example_files
from .store import examples_root

# Keys that are the encoding, not the vocabulary.
RESERVED = {'id', 'type', '@id', '@type', '@context', 'value', 'object',
            'json', 'valueList', 'observedAt', 'datasetId', 'unitCode',
            'createdAt', 'modifiedAt', 'instanceId', 'previousValue',
            'languageMap', 'vocab', 'entity'}


@dataclass
class Undeclared:
    """An attribute used by a document and declared by no knowledge file."""
    term: str                                   # as written in the document
    iri: str                                    # expanded, when it expands
    severity: str                               # error | info
    constrained: bool = False                   # a shape has sh:path on it
    places: list = field(default_factory=list)  # [(file, line)]
    message: str = ''


def _keys(path):
    """[(key, line)] for every attribute key in a document, nested included."""
    from ..cooked.jsonloc import locate

    try:
        with open(path, encoding='utf-8') as handle:
            raw = handle.read()
        document = json.loads(raw)
    except Exception:                              # noqa: BLE001
        return []
    try:
        index = locate(raw)
    except Exception:                              # noqa: BLE001
        index = {}

    found = []

    def walk(value, trail):
        if isinstance(value, dict):
            for key, inner in value.items():
                if key not in RESERVED and not key.startswith('@'):
                    found.append((key, index.get(tuple(trail + [key])) or 1))
                walk(inner, trail + [key])
        elif isinstance(value, list):
            for position, inner in enumerate(value):
                walk(inner, trail + [position])

    entities = document if isinstance(document, list) else [document]
    for position, entity in enumerate(entities):
        walk(entity, [position])
    return found


def undeclared_attributes(package):
    """Every attribute used in the package's documents and declared nowhere.

    Sorted by term, with every place it appears, so a rename that half
    happened reads as one finding rather than as five.
    """
    from ..cooked.choices import attribute_terms, expand
    from rdflib.namespace import SH

    declared = attribute_terms(package)
    known = {entry.term for entry in declared} | {entry.iri for entry in declared}
    constrained = {str(path) for path in package.shapes.objects(None, SH.path)}
    suite = os.path.abspath(examples_root(package.path))

    seen = {}
    for path in example_files(package):
        in_suite = os.path.abspath(path).startswith(suite + os.sep)
        for term, line in _keys(path):
            iri = expand(package.path, term)
            if term in known or iri in known:
                continue
            entry = seen.setdefault(term, Undeclared(
                term=term, iri=iri,
                severity='info', constrained=iri in constrained))
            entry.places.append((path, line))
            if in_suite:
                # A declared case that uses an undeclared term proves nothing.
                entry.severity = 'error'

    for entry in seen.values():
        entry.message = _message(entry)
    return sorted(seen.values(), key=lambda entry: entry.term)


def _message(entry):
    if entry.constrained:
        return (f'{entry.term} is constrained by a shape but declared by no '
                f'knowledge file. Declare it: nothing else says what it means, '
                f'what it may be carried by, or whether it is a Property or a '
                f'Relationship.')
    where = 'a case' if entry.severity == 'error' else 'the scratchpad'
    return (f'{entry.term} is used in {where} and declared nowhere. No sh:path '
            f'selects it, so every constraint about it stays silent and the '
            f'document reads as validated. Declare it in the knowledge, or '
            f'correct the spelling.')


@dataclass
class UnknownTerm:
    """An `ngsild:` term used by the package and declared by no vocabulary."""
    term: str                                   # the local name
    iri: str
    where: list = field(default_factory=list)   # knowledge | shapes | data
    message: str = ''


def unknown_ngsild_terms(package):
    """Every `ngsild:` IRI the package uses that the vocabulary does not declare.

    The same rule as everywhere else, turned on the encoding itself. An
    attribute declared `rdfs:range ngsild:Propery` is not an error anywhere:
    the range is a term, terms are IRIs, and rdflib will hold it happily. What
    it is NOT is a kind -- so the attribute has no kind, no picker offers the
    right payload key, and nothing says why.

    Upstream declares two classes. The shipped kms uses ten terms. That gap is
    what this reports, and it is why the SDK ships an extended copy.
    """
    from rdflib import URIRef

    from ..cooked.knowledge import _data_graph

    NGSILD = 'https://uri.etsi.org/ngsi-ld/'
    declared = {str(subject) for subject in package.vocabulary.subjects(None, None)
                if isinstance(subject, URIRef)}

    found = {}
    sources = [('knowledge', package.knowledge), ('shapes', package.shapes)]
    try:
        sources.append(('data', _data_graph(package)))
    except Exception:                              # noqa: BLE001
        pass            # a malformed example is the validator's story to tell

    for name, graph in sources:
        for triple in graph:
            for node in triple:
                text = str(node)
                if not isinstance(node, URIRef) or not text.startswith(NGSILD):
                    continue
                if text in declared or len(text) == len(NGSILD):
                    continue
                entry = found.setdefault(
                    text, UnknownTerm(term=text[len(NGSILD):], iri=text))
                if name not in entry.where:
                    entry.where.append(name)

    for entry in found.values():
        entry.message = (
            f'ngsild:{entry.term} is used in the {", ".join(entry.where)} and '
            f'declared by no NGSI-LD vocabulary. Either it is a typo, or the '
            f'vocabulary needs extending -- `ngsild:` in semforge.yaml points '
            f'at the copy this package uses.')
    return sorted(found.values(), key=lambda entry: entry.term)
