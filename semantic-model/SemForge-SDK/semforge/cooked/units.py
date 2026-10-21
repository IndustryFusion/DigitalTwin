"""Units: the curated Rec 20 catalogue, the package's own units, and what the
shapes and the data say about them.

A unit is a `qudt:Unit` with its UN/CEFACT common code
(`qudt:uneceCommonCode "CEL"`), a name (`rdfs:label`), a symbol
(`qudt:symbol`) and the quantity it measures (`qudt:hasQuantityKind
quantitykind:Temperature`). The SDK ships about 120 of them (ngsild/units.py),
read-only like SHACL's severities; a package adds its own to its knowledge
with the same terms.

In a shape, the units an attribute's instances may say sit on the attribute
node, where the attribute's metadata is:

    sh:property [ sh:path iffBaseEntities:hasTemperature ;
        sh:property [ sh:path ngsild:hasValue ; ... ] ,
                    [ sh:path ngsild:unitCode ; sh:in ( "CEL" ) ; sh:minCount 1 ] ]

pyshacl validates it; shacl2flink skips it for now (it compiles a nested
property only with a payload of its own), like the severity labels -- part of
the deferred alignment.

In the data, `unitCode` is set per instance -- every observation of one
datasetId says the same unit, so it is set on all of them together.
"""

import json
import re

from rdflib import URIRef
from rdflib.namespace import RDFS

from ..errors import PackageError
from ..ngsild.units import CATALOGUE, QUANTITYKIND, QUDT, quantity_words
from ..validate.normalise import curie, local

CODE = re.compile(r'^[A-Z0-9]{1,3}$')


# --- the catalogue -----------------------------------------------------------------------

def _entry(code, name, symbol, quantity, builtin, iri='', term=''):
    return {'code': code, 'name': name, 'symbol': symbol, 'quantity': quantity,
            'quantityLabel': quantity_words(quantity) if quantity else '',
            'builtin': builtin, 'iri': iri, 'term': term}


def own_units(package):
    """The package's own units: every subject with a qudt:uneceCommonCode."""
    graph = package.knowledge
    out = []
    for unit, code in graph.subject_objects(QUDT.uneceCommonCode):
        kind = graph.value(unit, QUDT.hasQuantityKind)
        out.append(_entry(str(code), str(graph.value(unit, RDFS.label) or code),
                          str(graph.value(unit, QUDT.symbol) or ''),
                          local(kind) if kind is not None else '', False, str(unit),
                          curie(graph, unit) if isinstance(unit, URIRef) else ''))
    return sorted(out, key=lambda e: e['code'])


def units(package):
    """Every unit the package can say: the catalogue's, then its own."""
    return [_entry(*row, True) for row in CATALOGUE] + own_units(package)


def find_unit(package, code):
    return next((u for u in units(package) if u['code'] == str(code).strip()), None)


def search_units(package, text=''):
    """Units matching `text` by code, name, symbol or quantity -- "temperature"
    finds CEL, FAH and KEL; "celsius" finds CEL -- the closest first."""
    words = str(text or '').strip().lower().split()
    if not words:
        return units(package)
    scored = []
    for unit in units(package):
        haystack = ' '.join((unit['code'], unit['name'], unit['symbol'],
                             unit['quantityLabel'])).lower()
        if not all(word in haystack for word in words):
            continue
        whole = ' '.join(words)
        rank = 0 if unit['code'].lower() == whole else \
            1 if unit['name'].lower().startswith(whole) else \
            2 if whole in unit['quantityLabel'] else 3
        scored.append((rank, unit['code'], unit))
    return [unit for _, _, unit in sorted(scored, key=lambda s: (s[0], s[1]))]


def quantities(package):
    """Every quantity a unit is known for, as QUDT names it."""
    return sorted({u['quantity'] for u in units(package) if u['quantity']})


def unit_text(package, codes):
    """How a list of codes reads in a sentence: `°C` or `°C, °F`."""
    found = {u['code']: u for u in units(package)}
    return ', '.join((found[c]['symbol'] or c) if c in found else c for c in codes)


def _bind(path, prefix, namespace):
    """An @prefix line for `namespace` in the file at `path`, when the file
    speaks neither the namespace nor the prefix yet."""
    from ..package.prefixes import PREFIX_LINE

    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    lines = list(PREFIX_LINE.finditer(text))
    if any(m.group(3) == namespace or (m.group(2) or '') == prefix for m in lines):
        return
    line = f'@prefix {prefix}: <{namespace}> .\n'
    if lines:
        at = lines[-1].end()
        at = at + 1 if text[at:at + 1] == '\n' else at
        text = text[:at] + line + text[at:]
    else:
        text = line + '\n' + text
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)


def _quantity(quantity):
    """'volume flow rate' or 'VolumeFlowRate' -> 'VolumeFlowRate'."""
    text = str(quantity or '').strip()
    if not text:
        raise PackageError('a unit measures a quantity, e.g. Temperature')
    if ' ' in text or text[:1].islower():
        text = ''.join(word[:1].upper() + word[1:] for word in text.split())
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', text):
        raise PackageError(f'"{quantity}" is not a quantity name: letters and digits, '
                           f'e.g. Temperature or VolumeFlowRate')
    return text


def add_unit(package, code, name, quantity, symbol='', namespace=None):
    """A unit of the package's own, in its knowledge, with the catalogue's
    terms -- for a code the curated set does not have. Returns the entry."""
    from .knowledge import _turtle_name, bind_namespace
    from .vocabulary import _append, _space_for

    code = str(code or '').strip().upper()
    if not CODE.match(code):
        raise PackageError(f'"{code}" is not a UN/CEFACT common code: one to three '
                           f'capital letters or digits, e.g. CEL')
    known = find_unit(package, code)
    if known:
        raise PackageError(f'{code} is already {known["name"]}'
                           + (' (the curated set)' if known['builtin'] else ''))
    if not str(name or '').strip():
        raise PackageError('a unit has a name, e.g. degree Celsius')
    kind = _quantity(quantity)
    iri = URIRef(_space_for(package, namespace) + code)
    if (iri, None, None) in package.knowledge:
        raise PackageError(f'{curie(package.knowledge, iri)} is already declared')
    path = package.sources['knowledge']
    bind_namespace(package, path, iri)
    _bind(path, 'qudt', str(QUDT))
    _bind(path, 'quantitykind', str(QUANTITYKIND))
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    lines = [f'{_turtle_name(text, iri)} a {_turtle_name(text, QUDT.Unit)}',
             f'    {_turtle_name(text, RDFS.label)} {json.dumps(str(name).strip())}']
    if str(symbol or '').strip():
        lines.append(f'    {_turtle_name(text, QUDT.symbol)} '
                     f'{json.dumps(str(symbol).strip(), ensure_ascii=False)}')
    lines += [f'    {_turtle_name(text, QUDT.uneceCommonCode)} {json.dumps(code)}',
              f'    {_turtle_name(text, QUDT.hasQuantityKind)} '
              f'{_turtle_name(text, QUANTITYKIND[kind])}']
    line = _append(path, lines, iri)
    return dict(_entry(code, str(name).strip(), str(symbol or '').strip(), kind, False,
                       str(iri)), file=path, line=line)


# --- the shapes ------------------------------------------------------------------------

def _unit_group(group):
    from .tree import _is_unit_path

    return next((c for c in group.children if _is_unit_path(c.path)), None)


def _codes_of(block):
    from .tree import list_items

    found = block.parameter('sh:in') if block is not None else None
    if not found:
        return []
    return [item.strip().strip('"') for item in list_items(found[2])]


def attribute_units(package, shape, path_chain):
    """{'codes', 'required'}: the units an attribute's instances may say, as
    its shape writes them, and whether one is required."""
    from .constrain import _group_in

    holder = package.index('shapes').file_for(URIRef(str(shape)))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    block = _unit_group(_group_in(text, str(shape), list(path_chain)))
    if block is None:
        return {'codes': [], 'required': False}
    least = block.parameter('sh:minCount')
    return {'codes': _codes_of(block),
            'required': bool(least and str(least[2]).strip() not in ('0', ''))}


def set_units(package, shape, path_chain, codes, required=False):
    """Write which units an attribute's instances may say -- or, with no codes,
    take the unit constraint out. Every code must be a known unit."""
    from .constrain import _add_line, _group_in
    from .remove_attribute import _remove_span
    from .tree import _term, _write_verified

    codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    unknown = [c for c in codes if find_unit(package, c) is None]
    if unknown:
        raise PackageError(f'{", ".join(unknown)}: not a unit this package knows -- '
                           f'add it as one of its own first (New unit…)')
    shape = str(shape)
    holder = package.index('shapes').file_for(URIRef(shape))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    chain = list(path_chain)
    group = _group_in(text, shape, chain)
    block = _unit_group(group)
    if codes:
        listed = ' '.join(json.dumps(c) for c in codes)
        written = (f'[ sh:path {_term(package, text, "ngsild:unitCode")} ; '
                   f'sh:in ( {listed} )' + (' ; sh:minCount 1' if required else '') + ' ]')
        if block is not None:
            text = text[:block.start] + written + text[block.end:]
        else:
            text = _add_line(text, group, 'sh:property', written)
    elif block is not None:
        text = _without(text, block, group) or \
            _remove_span(text, block, group.start + 1, group.end - 1)
    else:
        return {'file': holder, 'changed': False}
    _write_verified(holder, text)
    return {'file': holder, 'changed': True}


def _without(text, block, group):
    """The text without `; sh:property [ unit ]` as Unit… writes it -- the
    separator and the space before it too, so adding and removing a unit
    leaves the file as it was. None for any other layout."""
    predicate = text.rfind('sh:property', group.start, block.start)
    if predicate == -1 or text[predicate + len('sh:property'):block.start].strip():
        return None
    after = block.end
    while after < group.end and text[after].isspace():
        after += 1
    if text[after:after + 1] == ',':
        return None                        # one of several objects: not ours
    start = predicate
    while start > group.start and text[start - 1].isspace():
        start -= 1
    if text[start - 1:start] != ';':
        return None
    start -= 1
    while start > group.start and text[start - 1] in ' \t':
        start -= 1
    return text[:start] + text[block.end:]


# --- the data --------------------------------------------------------------------------

def set_unit_code(package, entity_id, attribute_path, dataset_id, code, file=None):
    """Set (or, with no code, remove) the unitCode of one instance -- every
    observation of its datasetId, since they are one instance."""
    from .examples import (DEFAULT_DATASET, _group_by_dataset, _instances_at,
                           _read_document, _target_file, _write)

    code = str(code or '').strip()
    if code and find_unit(package, code) is None:
        raise PackageError(f'{code}: not a unit this package knows -- add it as one '
                           f'of its own first (New unit…)')
    source = _target_file(package, file)
    text, document, entities = _read_document(source)
    holder, key, instances = _instances_at(entities, entity_id, attribute_path)
    groups = _group_by_dataset(instances)
    wanted = str(dataset_id or '') or DEFAULT_DATASET
    if wanted not in groups:
        raise PackageError(f'{entity_id}: {key} has no instance with datasetId {wanted}')
    for _, instance in groups[wanted]:
        if instance.get('type', 'Property') == 'Relationship':
            raise PackageError(f'{key} is a Relationship: it points at an entity and '
                               f'has no unit')
        if code:
            instance['unitCode'] = code
        else:
            instance.pop('unitCode', None)
    _write(source, document, text)
    return {'file': source, 'code': code, 'changed': len(groups[wanted])}
