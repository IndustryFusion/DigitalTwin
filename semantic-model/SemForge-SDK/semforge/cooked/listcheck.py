"""Does an sh:in list agree with the rest of what the value must be?

sh:in compares RDF terms exactly. An item the other constraints on the same
value forbid can never be given -- and worse, an item can be "right" to the
eye and still never match: `20.5` in Turtle is an xsd:decimal, while an
NGSI-LD document's JSON 20.5 arrives as xsd:double, so `sh:in ( 20.5 )`
rejects every 20.5 there is (measured with pyshacl).

`list_conflicts` reads the items as RDF terms and checks each against the
value's datatype, node kind, class, bounds, lengths and pattern, saying what
is wrong in words. `item_term` is the reading, shared with the writer.
"""

import re

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

NUMBER = re.compile(r'[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?')
QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"(?:@([A-Za-z-]+)|\^\^(\S+))?')
NUMERIC = {XSD.integer, XSD.decimal, XSD.double, XSD.float, XSD.int, XSD.long,
           XSD.short, XSD.nonNegativeInteger, XSD.positiveInteger}


def _expand(package, token):
    token = token.strip()
    if token.startswith('<') and token.endswith('>'):
        return URIRef(token[1:-1])
    prefix, _, name = token.partition(':')
    for graph in (package.shapes, package.knowledge):
        namespace = dict((p, str(n)) for p, n in graph.namespaces()).get(prefix)
        if namespace is not None:
            return URIRef(namespace + name)
    if prefix == 'xsd':
        return URIRef(str(XSD) + name)
    return URIRef(token)


def item_term(package, token):
    """A list item as written -> the RDF term it is."""
    token = token.strip()
    quoted = QUOTED.fullmatch(token)
    if quoted:
        text, lang, datatype = quoted.groups()
        if datatype:
            return Literal(text, datatype=_expand(package, datatype))
        return Literal(text, lang=lang) if lang else Literal(text)
    if token in ('true', 'false'):
        return Literal(token, datatype=XSD.boolean)
    if NUMBER.fullmatch(token):
        if 'e' in token.lower():
            return Literal(token, datatype=XSD.double)
        return Literal(token, datatype=XSD.decimal if '.' in token else XSD.integer)
    return _expand(package, token)


def _number(text):
    try:
        return float(str(text).split('^^')[0].strip('"'))
    except ValueError:
        return None


def _instances(package, cls):
    """Every named instance of a class or a subclass of it."""
    classes, pending = {cls}, [cls]
    while pending:
        for sub in package.knowledge.subjects(RDFS.subClassOf, pending.pop()):
            if sub not in classes:
                classes.add(sub)
                pending.append(sub)
    found = set()
    for each in classes:
        found |= set(package.knowledge.subjects(RDF.type, each))
    return found


def _written(token):
    """An item as a person wrote it: `"150"^^xsd:double` -> 150."""
    quoted = QUOTED.fullmatch(token.strip())
    return quoted.group(1) if quoted and quoted.group(3) else token.strip()


def _short(package, term):
    if isinstance(term, Literal):
        return f'"{term}"' if term.datatype in (None, XSD.string) else str(term)
    from ..validate.normalise import curie
    return curie(package.knowledge, term).split(':')[-1]


def list_conflicts(package, value_params, items):
    """Notes for list items the other constraints on the value forbid."""
    terms = [(token, item_term(package, token)) for token in items]
    notes = []
    datatype = value_params.get('sh:datatype')
    datatype = _expand(package, datatype) if datatype else None
    kind = value_params.get('sh:nodeKind')
    cls = value_params.get('sh:class')
    cls = _expand(package, cls) if cls else None
    members = _instances(package, cls) if cls is not None else None

    for token, term in terms:
        name = _short(package, term)
        if isinstance(term, Literal):
            if datatype is not None and (term.datatype or XSD.string) != datatype:
                said = (term.datatype or XSD.string).split('#')[-1]
                notes.append(f'{name} is xsd:{said}, but the value must be '
                             f'xsd:{datatype.split("#")[-1]}: it can never be given')
            elif datatype is None and term.datatype == XSD.decimal:
                notes.append(f'{name} is written as xsd:decimal; an NGSI-LD number arrives '
                             f'as xsd:double and never equals it — write "{term}"^^xsd:double')
            if kind == 'sh:IRI':
                notes.append(f'{name} is a literal, but the value must be an IRI')
            if members is not None:
                notes.append(f'{name} is a literal, but the value must be a '
                             f'{_short(package, cls)}')
        else:
            if datatype is not None:
                notes.append(f'{name} is an IRI, but the value must be '
                             f'xsd:{datatype.split("#")[-1]}')
            if kind == 'sh:Literal':
                notes.append(f'{name} is an IRI, but the value must be a literal')
            if members is not None and term not in members:
                notes.append(f'{name} is not a {_short(package, cls)}')

    numbers = [(token, term) for token, term in terms
               if isinstance(term, Literal) and term.datatype in NUMERIC]
    for name, test, words in (
            ('sh:minInclusive', lambda v, b: v >= b, '≥'),
            ('sh:minExclusive', lambda v, b: v > b, '>'),
            ('sh:maxInclusive', lambda v, b: v <= b, '≤'),
            ('sh:maxExclusive', lambda v, b: v < b, '<')):
        bound = _number(value_params.get(name, ''))
        if bound is None:
            continue
        for token, term in numbers:
            if not test(float(term), bound):
                notes.append(f'{_written(token)} is outside {words} {bound:g}')
    texts = [term for _, term in terms
             if isinstance(term, Literal) and term.datatype in (None, XSD.string)]
    shortest, longest = (_number(value_params.get('sh:minLength', '')),
                         _number(value_params.get('sh:maxLength', '')))
    pattern = str(value_params.get('sh:pattern', '')).strip('"') or None
    for term in texts:
        if shortest is not None and len(str(term)) < shortest:
            notes.append(f'"{term}" is shorter than {shortest:g} characters')
        if longest is not None and len(str(term)) > longest:
            notes.append(f'"{term}" is longer than {longest:g} characters')
        if pattern:
            try:
                if not re.search(pattern, str(term)):
                    notes.append(f'"{term}" does not match {pattern}')
            except re.error:
                pass
    return notes
