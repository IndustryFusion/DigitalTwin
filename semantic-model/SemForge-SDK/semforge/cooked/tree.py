"""The cooked view over a package's constraints (manifest section 2.2).

Raw and cooked are two views of ONE state, so this is a projection of the shapes
file rather than a model beside it. Every node addresses a real span of text,
and every edit rewrites that span -- which is what makes invariant S1 hold by
construction: there is nothing the cooked view can express that raw cannot,
because a cooked edit IS a raw edit.

The tree it builds:

    Filter                      entity type (sh:targetClass)
    └── hasStrength             attribute
        ├── count 1..1          constraints on the ATTRIBUTE: how many instances
        ├── nodeKind BlankNode
        └── value               the value slot
            ├── 0.0 <= x        constraints on the VALUE: what it may be
            └── <= 100.0

Two things are deliberately visible but not editable here. Connectives
(sh:or, sh:node) are structure rather than a parameter, and SPARQL bodies are
not plausibly a form. Both are shown with their raw text so the tree does not
lie about what a shape contains -- invariant S2: content the cooked view cannot
project is preserved and marked, never hidden and never dropped.
"""

import json
import os
import re
from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import RDFS, SH

from ..errors import PackageError
from ..rdfio import (find_block, property_blocks, remove_parameter,
                     set_parameter)
from ..validate.normalise import curie, local
from ..validate.shapes import class_targets, node_shapes

# Parameters a form can honestly offer: one name, one scalar value.
EDITABLE = {
    'sh:minCount': ('count', 'integer'),
    'sh:maxCount': ('count', 'integer'),
    'sh:datatype': ('datatype', 'iri'),
    'sh:class': ('class', 'iri'),
    'sh:nodeKind': ('nodeKind', 'iri'),
    'sh:minInclusive': ('range', 'number'),
    'sh:maxInclusive': ('range', 'number'),
    'sh:minExclusive': ('range', 'number'),
    'sh:maxExclusive': ('range', 'number'),
    'sh:minLength': ('length', 'integer'),
    'sh:maxLength': ('length', 'integer'),
    'sh:pattern': ('pattern', 'string'),
}

# Structure, not parameters. Shown so the tree is honest; edited in raw.
RAW_ONLY = {'sh:or', 'sh:and', 'sh:xone', 'sh:not', 'sh:node', 'sh:in'}

from ..ngsild.kinds import PAYLOAD_NAMES as _PAYLOADS  # noqa: E402

VALUE_PATHS = {f'ngsild:{name}' for name in _PAYLOADS}

# An NGSI-LD attribute IS a blank node carrying hasValue/hasObject, so
# `sh:nodeKind sh:BlankNode` on a forward attribute path restates the encoding
# rather than deciding anything. It is hidden here and completed on export.
#
# Two things it is NOT. At the VALUE level nodeKind is a real choice --
# sh:IRI for a relationship target, sh:Literal for a plain value, and the kms
# uses both. And an INVERSE path does not reach an attribute node at all: it
# walks back to the entity that points here, which is an IRI. CartridgeShape's
# exclusivity constraint is exactly that case, and BlankNode there would be
# wrong rather than redundant.
IMPLIED_NODE_KIND = 'sh:BlankNode'


def forward_attribute_path(path):
    """True when a path names one NGSI-LD attribute going forwards."""
    text = (path or '').strip()
    if not text or text.startswith(('(', '[')):
        return False          # a sequence or an inverse: not an attribute node
    return text not in VALUE_PATHS


@dataclass
class CookedNode:
    kind: str                  # type | attribute | slot | constraint | raw
    label: str
    detail: str = ''
    shape: str = ''            # owning shape IRI
    path_chain: list = field(default_factory=list)
    parameter: str = ''
    value: str = ''
    editable: bool = False
    children: list = field(default_factory=list)
    inherited_from: str = ''   # the shape that declares it, when not this one
    inherited_class: str = ''  # the ancestor class that shape targets
    defined_at: str = ''       # file:line of the declaring shape
    target_class: str = ''     # for a type node, the class it stands for

    @property
    def address(self):
        """What an edit needs: which shape, which nesting, which parameter."""
        return {'shape': self.shape, 'path': list(self.path_chain),
                'parameter': self.parameter}


def _line_counter(text):
    """offset -> 1-based line. Built once; the tree asks for it per node.

    Every node needs a location, not just the shapes: selecting an attribute or
    a single constraint should move the .ttl editor to it, and a tree that can
    only point at whole shapes makes the reader hunt for the line themselves.
    """
    starts = [0]
    for index, char in enumerate(text):
        if char == '\n':
            starts.append(index + 1)

    def line_of(offset):
        low, high = 0, len(starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low + 1

    return line_of


def _at(path, line_of, offset):
    return f'{path}:{line_of(offset)}'


def _constraint_nodes(block, shape, chain, locate=None, is_value_slot=False):
    nodes = []
    implied = (not is_value_slot) and forward_attribute_path(block.path)
    for name in sorted(block.parameters):
        if name == 'sh:order':
            continue
        start, _, value = block.parameters[name]
        if (name == 'sh:nodeKind' and implied
                and value.strip() == IMPLIED_NODE_KIND):
            # Restates the encoding; showing it is noise. A DIFFERENT nodeKind
            # here is a modelling error and stays visible.
            continue
        where = locate(start) if locate else ''
        if name in RAW_ONLY:
            nodes.append(CookedNode(
                kind='raw', label=f'{local(name)} (raw only)',
                detail='structure, not a parameter — edit in the .ttl',
                shape=shape, path_chain=list(chain), parameter=name,
                value=value.strip(), defined_at=where))
        elif name in EDITABLE:
            nodes.append(CookedNode(
                kind='constraint', label=local(name), detail=value,
                shape=shape, path_chain=list(chain), parameter=name,
                value=value, editable=True, defined_at=where))
        else:
            nodes.append(CookedNode(
                kind='raw', label=local(name), detail=value,
                shape=shape, path_chain=list(chain), parameter=name,
                value=value, defined_at=where))
    return nodes


def _short(path):
    """`iffBaseEntities:hasFilter` and `<http://…/hasFilter>` both read hasFilter."""
    return local(path.strip('<>')).split(':')[-1]


def _attribute_node(block, shape, chain, locate=None):
    chain = chain + [block.path]
    node = CookedNode(kind='attribute', label=_short(block.path),
                      detail=block.path, shape=shape, path_chain=list(chain),
                      defined_at=locate(block.start) if locate else '')
    node.children.extend(_constraint_nodes(block, shape, chain, locate, False))

    for child in block.children:
        if child.path in VALUE_PATHS:
            slot = CookedNode(
                kind='slot', label='value',
                detail=_short(child.path), shape=shape,
                path_chain=chain + [child.path],
                defined_at=locate(child.start) if locate else '')
            slot.children.extend(
                _constraint_nodes(child, shape, chain + [child.path], locate,
                                  True))
            node.children.append(slot)
        elif _is_unit_path(child.path):
            # The attribute's unitCode: which units its instances may say
            # (sh:in) and whether one is required -- metadata of the attribute,
            # not a sub-attribute of it.
            unit = CookedNode(
                kind='unit', label='unit', detail=_short(child.path), shape=shape,
                path_chain=chain + [child.path],
                defined_at=locate(child.start) if locate else '')
            unit.children.extend(
                _constraint_nodes(child, shape, chain + [child.path], locate, True))
            node.children.append(unit)
        else:
            node.children.append(_attribute_node(child, shape, chain, locate))
    return node


UNIT_CODE = 'https://uri.etsi.org/ngsi-ld/unitCode'


def _is_unit_path(path):
    """ngsild:unitCode as the shapes write it -- prefixed or in full."""
    text = str(path).strip('<>')
    return text == UNIT_CODE or text.endswith(':unitCode') and \
        text.split(':')[0] in ('ngsild', 'ngsi-ld')


def _ancestors(graph, cls):
    """cls and every class above it, through rdfs:subClassOf."""
    from rdflib.namespace import RDFS

    found = [cls]
    seen = {cls}
    pending = [cls]
    while pending:
        for parent in graph.objects(pending.pop(), RDFS.subClassOf):
            if parent not in seen:
                seen.add(parent)
                found.append(parent)
                pending.append(parent)
    return found


def _mark_inherited(node, shape, cls, locator):
    """Stamp a subtree as inherited and make it read-only here.

    Each node keeps its OWN location. Overwriting them all with the shape's
    would send every jump to the same line, which is precisely what makes
    "go to definition" useless on a nested constraint.
    """
    node.inherited_from = str(shape)
    node.inherited_class = str(cls)
    node.defined_at = node.defined_at or locator
    node.editable = False
    for child in node.children:
        _mark_inherited(child, shape, cls, locator)


def _shape_node(package, shape, text, index, line_of=None):
    block = index.block_for(shape)
    if block is None:
        return None
    groups = property_blocks(text, block)

    def locate(offset):
        return _at(index.path, line_of, offset) if line_of else ''

    node = CookedNode(kind='shape', label=curie(package.shapes, shape),
                      detail=f'{len(groups)} attribute(s)', shape=str(shape),
                      defined_at=index.locator(shape))
    for group in groups:
        node.children.append(_attribute_node(group, str(shape), [], locate))
    if (shape, SH.sparql, None) in package.shapes:
        node.children.append(CookedNode(
            kind='raw', label='SPARQL constraint',
            detail='a query body is not a form — edit in the .ttl',
            shape=str(shape), defined_at=index.locator(shape)))
    if (shape, SH.rule, None) in package.shapes:
        node.children.append(CookedNode(
            kind='raw', label='SPARQL rule',
            detail='a rule body is not a form — edit in the .ttl',
            shape=str(shape), defined_at=index.locator(shape)))
    return node


def shape_node(package, shape):
    """One shape as a cooked node, whatever it targets -- or None when it is
    not a statement in the shapes files (a shape only named, never written)."""
    index = package.index('shapes')
    path = index.file_for(URIRef(shape))
    if path is None:
        return None
    text = index.source_of(path)
    return _shape_node(package, URIRef(shape), text, index.indexes[path],
                       _line_counter(text))


def build_tree(package):
    """Entity types -> attributes -> constraints, inherited ones included.

    A shape targeting Machine applies to every Filter too: sh:targetClass goes
    through the subclass closure, and pyshacl duly evaluates MachineShape's
    hasState against urn:filter:1. Showing Filter with only its own two
    attributes made the tree lie by omission -- the constraint was there, just
    declared elsewhere.

    So a type carries what its own shapes declare AND what it inherits, the
    latter marked with where it comes from and not editable in place. Editing it
    there would be a lie of a different kind: SHACL CONJOINS, so a constraint
    added to the subtype cannot relax the one above it (see override_effect).
    """
    # Per file, because a role may be a directory: the text a shape is read
    # from has to be the text it was WRITTEN in, or the spans address the wrong
    # document.
    index = package.index('shapes')
    texts = {path: index.source_of(path) for path in index.paths}
    counters = {path: _line_counter(text) for path, text in texts.items()}

    def source_of(shape):
        path = index.file_for(shape)
        if path is None:
            return None, '', None
        return path, texts[path], counters[path]

    by_class = {}
    for shape in node_shapes(package.shapes):
        for target in class_targets(package.shapes, shape):
            by_class.setdefault(target, []).append(shape)

    # A subtype with no shape of its own is still judged by its ancestors'
    # shapes (class targets include subclasses), so it is a type here too --
    # with only inherited shapes. Leaving it out hid a new subtype, and its
    # page said nothing constrains it.
    classes, pending = set(by_class), list(by_class)
    while pending:
        for child in package.knowledge.subjects(RDFS.subClassOf, pending.pop()):
            if isinstance(child, URIRef) and child not in classes:
                classes.add(child)
                pending.append(child)

    roots = []
    for cls in sorted(classes, key=str):
        node = CookedNode(kind='type', label=local(cls), target_class=str(cls))
        own = 0
        for shape in by_class.get(cls, []):
            path, text, line_of = source_of(shape)
            if path is None:
                continue
            child = _shape_node(package, shape, text, index.indexes[path],
                                line_of)
            if child is not None:
                node.children.append(child)
                own += 1

        inherited = 0
        for ancestor in _ancestors(package.knowledge, cls)[1:]:
            for shape in by_class.get(ancestor, []):
                path, text, line_of = source_of(shape)
                if path is None:
                    continue
                child = _shape_node(package, shape, text, index.indexes[path],
                                    line_of)
                if child is None:
                    continue
                _mark_inherited(child, shape, ancestor, index.locator(shape))
                child.detail = (f'inherited from {local(ancestor)} — '
                                f'{child.detail}')
                node.children.append(child)
                inherited += 1

        node.detail = f'{own} shape(s)' + (f', {inherited} inherited'
                                           if inherited else '')
        roots.append(node)
    return roots


def _locate(package, shape, path_chain):
    index = package.index('shapes')
    source_path, block = index.block_for(shape)
    if block is None:
        raise PackageError(
            f'{shape} is not a statement in '
            + ', '.join(os.path.basename(p) for p in index.paths))
    text = index.source_of(source_path)
    target = find_block(property_blocks(text, block), path_chain)
    if target is None:
        raise PackageError(
            f'no property shape at {" / ".join(path_chain)} in {local(shape)}')
    return source_path, text, target


def impossible_counts(graph):
    """[(sh:path, sh:minCount, sh:maxCount)] for every property shape that asks
    for more instances than it allows -- no data can ever satisfy it."""
    out = []
    for node, low in graph.subject_objects(SH.minCount):
        for high in graph.objects(node, SH.maxCount):
            try:
                least, most = int(low), int(high)
            except (TypeError, ValueError):
                continue
            if least > most:
                out.append((str(graph.value(node, SH.path) or ''), least, most))
    return sorted(out)


def _write_verified(source_path, text):
    """Write only after the result parses -- and asks nothing impossible.

    A cooked edit that produces invalid Turtle would take the file with it, and
    the whole point of editing spans rather than reserialising is that the file
    survives. An edit that leaves sh:minCount above sh:maxCount parses fine
    and can never be satisfied, so it is refused here, where every cooked write
    passes; one the file already had is left to the sanity finding.
    """
    from rdflib import Graph

    graph = Graph().parse(data=text, format='turtle')
    impossible = impossible_counts(graph)
    if impossible:
        before = []
        if os.path.exists(source_path):
            try:
                before = impossible_counts(Graph().parse(source_path, format='turtle'))
            except Exception:                      # noqa: BLE001
                before = []
        for found in before:
            if found in impossible:
                impossible.remove(found)
    if impossible:
        path, least, most = impossible[0]
        raise PackageError(
            f'{local(path) if path else "a property shape"} would need at least {least} '
            f'and at most {most} instances -- no data can satisfy that. Nothing written.')
    with open(source_path, 'w', encoding='utf-8') as handle:
        handle.write(text)


def apply_edit(package, shape, path_chain, parameter, value):
    """Set one constraint parameter. Returns (path, bytes changed)."""
    if parameter not in EDITABLE:
        raise PackageError(
            f'{parameter} is not editable in the cooked view: it is structure '
            f'rather than a parameter. Edit it in the .ttl.')
    source_path, text, target = _locate(package, shape, path_chain)
    updated = set_parameter(text, target, parameter, value)
    _write_verified(source_path, updated)
    return source_path, sum(1 for a, b in zip(text, updated) if a != b) or \
        abs(len(updated) - len(text))


# Where a parameter may go: a count on either layer, everything else on the
# value -- a datatype or a range on the attribute node constrains the blank
# node itself and can never be satisfied.
ATTRIBUTE_LAYER = {'sh:minCount', 'sh:maxCount'}
SLOTS = tuple(f'ngsild:{name}' for name in _PAYLOADS)


def _term(package, text, value):
    """A prefixed name or IRI as THIS file can write it."""
    from rdflib import URIRef

    from .knowledge import _turtle_name

    value = str(value).strip()
    if value.startswith('<') and value.endswith('>'):
        iri = value[1:-1]
    elif ':' in value and not value.startswith(('http://', 'https://', 'urn:')):
        prefix, _, name = value.partition(':')
        # The shapes' prefixes first; a vocabulary value is usually written
        # with the knowledge's (myModelKnowledge:state_ON).
        namespace = dict((p, str(n)) for p, n in package.shapes.namespaces()).get(prefix) \
            or dict((p, str(n)) for p, n in package.knowledge.namespaces()).get(prefix) \
            or {'xsd': 'http://www.w3.org/2001/XMLSchema#',
                'sh': 'http://www.w3.org/ns/shacl#'}.get(prefix)
        if namespace is None:
            raise PackageError(f'{value}: the prefix "{prefix}" is not declared')
        iri = namespace + name
    else:
        iri = value
    return _turtle_name(text, URIRef(iri))


LIST_ITEM = re.compile(r'"(?:[^"\\]|\\.)*"(?:@[A-Za-z-]+|\^\^\S+)?|<[^>]*>|[^\s(),]+')
NUMBER = re.compile(r'[-+]?\d+(\.\d+)?([eE][-+]?\d+)?')


def list_items(text):
    """`( a "b c" 1 )` -> ['a', '"b c"', '1']: an sh:in list as written."""
    inner = str(text or '').strip()
    if inner.startswith('(') and inner.endswith(')'):
        inner = inner[1:-1]
    return LIST_ITEM.findall(inner)


def _list_value(package, text, value, datatype=None):
    """An sh:in list as Turtle. Items come as a list, or one text separated by
    commas; each is a number, true/false, a "quoted" text, or a prefixed name
    or IRI -- anything else is taken as text and quoted.

    sh:in compares terms exactly, and a JSON 20.5 in an NGSI-LD document is an
    xsd:double -- never equal to Turtle's 20.5, an xsd:decimal. So a number
    with a fraction is written typed: with the value's sh:datatype when it
    has one, else as xsd:double. A whole number stays as written, as a JSON
    whole number arrives (xsd:integer), unless the datatype says otherwise."""
    if isinstance(value, str):
        items = [i.strip() for i in re.findall(r'"(?:[^"\\]|\\.)*"|[^,]+', value)]
    else:
        items = [str(i).strip() for i in value or []]
    rendered = []
    for item in items:
        if not item:
            continue
        if NUMBER.fullmatch(item):
            whole = re.fullmatch(r'[-+]?\d+', item) is not None
            typed = datatype if datatype and datatype not in ('xsd:integer', 'xsd:int') \
                else (None if whole else 'xsd:double')
            term = f'"{item}"^^{_term(package, text, typed)}' if typed else item
        elif item in ('true', 'false') or \
                (item.startswith('"') and item.endswith('"') and len(item) > 1):
            term = item
        elif item.startswith('<') or re.fullmatch(r'[A-Za-z][\w.-]*:[^\s"]+', item):
            term = _term(package, text, item)
        else:
            term = json.dumps(item)
        if term not in rendered:
            rendered.append(term)
    if not rendered:
        raise PackageError('an empty sh:in admits no value at all; remove it instead')
    return '( ' + ' '.join(rendered) + ' )'


def _parameter_value(package, text, parameter, value, datatype=None):
    """The Turtle for a parameter's value, refusing one SHACL would reject."""
    if parameter == 'sh:in':
        return _list_value(package, text, value, datatype)
    kind = EDITABLE[parameter][1]
    raw = str(value).strip()
    if kind == 'integer':
        if not re.fullmatch(r'\d+', raw):
            raise PackageError(f'{parameter} takes a whole number ≥ 0, not "{raw}"')
        return raw
    if kind == 'number':
        try:
            float(raw)
        except ValueError:
            raise PackageError(f'{parameter} takes a number, not "{raw}"') from None
        return raw
    if kind == 'string':
        if raw.startswith('"') and raw.endswith('"') and len(raw) > 1:
            return raw
        return json.dumps(raw)
    return _term(package, text, raw)


def _bounds_note(target_text):
    """A note when the bounds now on one value admit nothing."""
    found = dict(re.findall(r'(sh:(?:min|max)(?:Inclusive|Exclusive))\s+([-+0-9.eE]+)',
                            target_text))
    low = [(float(v), k) for k, v in found.items() if k.startswith('sh:min')]
    high = [(float(v), k) for k, v in found.items() if k.startswith('sh:max')]
    for low_value, low_name in low:
        for high_value, high_name in high:
            empty = low_value > high_value or (low_value == high_value and (
                'Exclusive' in low_name or 'Exclusive' in high_name))
            if empty:
                return (f'{low_name} {low_value:g} and {high_name} {high_value:g} '
                        f'admit no value: every entity carrying it now violates')
    return ''


def add_constraint(package, shape, path_chain, parameter, value, layer='value'):
    """Add a constraint parameter to an attribute, or replace its value when
    it is already there. `path_chain` is the attribute's path; `layer` says
    whether it goes on the attribute node or on its value.

    A value layer the attribute does not have yet is created
    (`sh:property [ sh:path ngsild:hasValue ; ... ]`). Returns
    {'file', 'action': 'added' | 'replaced', 'note'}.
    """
    from .constrain import _add_line

    if parameter not in EDITABLE and parameter != 'sh:in':
        raise PackageError(f'{parameter} is not a constraint the editor writes; '
                           f'edit it in the .ttl')
    if layer == 'attribute' and parameter not in ATTRIBUTE_LAYER:
        raise PackageError(f'{parameter} on the attribute node would constrain the '
                           f'blank node itself and can never hold; it goes on the value')
    chain = list(path_chain)
    if layer == 'value':
        located = None
        for slot in SLOTS:
            try:
                located = _locate(package, shape, chain + [slot])
                break
            except PackageError:
                continue
        if located is None:
            # No value layer yet: create one around the parameter.
            source_path, text, target = _locate(package, shape, chain)
            from .choices import attribute_terms
            from .typepage import _resolve_token

            iri = str(_resolve_token(package, chain[-1]))
            kind = next((a.kind for a in attribute_terms(package) if a.iri == iri), '')
            slot = 'ngsild:hasObject' if kind == 'Relationship' else 'ngsild:hasValue'
            rendered = _parameter_value(package, text, parameter, value)
            block = f'[ sh:path {_term(package, text, slot)} ; {parameter} {rendered} ]'
            updated = _add_line(text, target, 'sh:property', block)
            _write_verified(source_path, updated)
            return {'file': source_path, 'action': 'added', 'note': ''}
        source_path, text, target = located
    else:
        source_path, text, target = _locate(package, shape, chain)
    datatype = target.parameter('sh:datatype')
    rendered = _parameter_value(package, text, parameter, value,
                                datatype[2] if datatype else None)
    if target.parameter(parameter) is None:
        updated, action = _add_line(text, target, parameter, rendered), 'added'
    else:
        updated, action = set_parameter(text, target, parameter, rendered), 'replaced'
    _write_verified(source_path, updated)
    # The block as it now reads, for the bounds and the list checks.
    after = updated[target.start:target.end + len(updated) - len(text)]
    notes = [n for n in (_bounds_note(after),
                         _list_note(package, updated, shape, chain, layer)) if n]
    return {'file': source_path, 'action': action, 'note': '; '.join(notes)}


def _list_note(package, text, shape, chain, layer):
    """What an sh:in list on the value now contradicts, in one line."""
    from .listcheck import list_conflicts

    if layer != 'value':
        return ''
    try:
        _, block = _found_in(text, shape, chain)
    except PackageError:
        return ''
    if block is None or block.parameter('sh:in') is None:
        return ''
    params = {name: found[2] for name, found in block.parameters.items()}
    found = list_conflicts(package, params, list_items(params['sh:in']))
    return '; '.join(found)


def _found_in(text, shape, chain):
    """The value block of the attribute at `chain` in `text`, or (…, None)."""
    from ..rdfio import TurtleIndex

    statement = TurtleIndex(text).block_for(str(shape))
    if statement is None:
        raise PackageError(f'{shape} is not in the text')
    for slot in SLOTS:
        block = find_block(property_blocks(text, statement), list(chain) + [slot])
        if block is not None:
            return slot, block
    return None, None


def remove_constraint(package, shape, path_chain, parameter):
    source_path, text, target = _locate(package, shape, path_chain)
    updated = remove_parameter(text, target, parameter)
    _write_verified(source_path, updated)
    return source_path, len(text) - len(updated)


# Which way a bound moves when it WEAKENS a constraint. Reused from the
# semantic diff, because the question is the same one asked at edit time --
# keyed there by CONSTRAINT COMPONENT, while a cooked node carries the SHACL
# PARAMETER, so the two have to be bridged.
from ..diff.model import WEAKER_WHEN            # noqa: E402
from ..validate.applicable import PARAMETERS    # noqa: E402

WEAKER_BY_PARAMETER = {
    f'sh:{str(parameter).rsplit("#", 1)[-1]}': WEAKER_WHEN[component]
    for parameter, component in PARAMETERS.items() if component in WEAKER_WHEN
}


def override_effect(parameter, inherited_value, new_value):
    """'stricter' | 'weaker' | 'same' | 'unknown' for a proposed override.

    SHACL has no override. A constraint declared on Filter is CONJOINED with the
    one MachineShape declares, not substituted for it -- proven: adding
    `hasState minCount 0` to FilterShape leaves MachineShape's `minCount 1`
    firing exactly as before.

    So an override can tighten and cannot relax, and the only honest thing to do
    with a weaker value is say it will have no effect.
    """
    if str(inherited_value).strip() == str(new_value).strip():
        return 'same'
    rule = WEAKER_BY_PARAMETER.get(parameter)
    if rule is None:
        return 'unknown'
    try:
        moved_up = float(new_value) > float(inherited_value)
    except (TypeError, ValueError):
        return 'unknown'
    weakened = moved_up if rule == 'increases' else not moved_up
    return 'weaker' if weakened else 'stricter'


def override_constraint(package, shape, path_chain, parameter, value):
    """Declare an inherited constraint explicitly on this type's own shape.

    Adds rather than replaces, which is what SHACL means by it.
    """
    from ..rdfio import add_parameter, add_property_constraint

    source_path, text, target = None, None, None
    try:
        source_path, text, target = _locate(package, shape, path_chain)
    except PackageError:
        target = None

    if target is not None:
        updated = add_parameter(text, target, parameter, value) \
            if target.parameter(parameter) is None \
            else set_parameter(text, target, parameter, value)
        _write_verified(source_path, updated)
        return source_path, 'added-to-existing'

    # The attribute is not on this shape at all: add the whole property block.
    attribute = path_chain[0] if path_chain else None
    if attribute is None:
        raise PackageError('cannot override without an attribute path')
    # Again the file that holds the shape: adding a property to FilterShape has
    # to land where FilterShape is, whichever document that is.
    holder = package.index('shapes').file_for(shape)
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    if len(path_chain) == 1:
        parameters = [(parameter, value)]
    elif len(path_chain) == 2:
        # A value-layer parameter (sh:class on hasObject, a range on
        # hasValue): it goes inside a value layer of the new property shape.
        # Put on the attribute node it would constrain the blank node itself
        # and could never be satisfied.
        parameters = [('sh:property', [('sh:path', path_chain[1]),
                                       (parameter, value)])]
    else:
        raise PackageError(
            'overriding a constraint inside a sub-attribute the shape does not '
            'carry yet is not supported; add the attribute first')
    updated = add_property_constraint(holder, shape, attribute, parameters)
    _write_verified(holder, updated)
    return holder, 'added-attribute'


def flatten(nodes, depth=0):
    """Depth-first, for tests and for a text rendering of the tree."""
    for node in nodes:
        yield depth, node
        yield from flatten(node.children, depth + 1)


def render(nodes):
    lines = []
    for depth, node in flatten(nodes):
        mark = '*' if node.editable else ' '
        detail = f'  {node.detail}' if node.detail else ''
        lines.append(f'{"  " * depth}{mark} {node.label}{detail}')
    return lines
