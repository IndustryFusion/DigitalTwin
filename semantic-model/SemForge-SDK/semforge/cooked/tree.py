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

import os
from dataclasses import dataclass, field

from rdflib.namespace import SH

from ..errors import PackageError
from ..rdfio import (find_block, property_blocks, remove_parameter,
                     set_parameter)
from ..validate.normalise import curie, local
from ..validate.shapes import node_shapes

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

VALUE_PATHS = {'ngsild:hasValue', 'ngsild:hasObject', 'ngsild:hasValueList',
               'ngsild:hasJSON'}

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
                value=value.strip()[:60], defined_at=where))
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
        else:
            node.children.append(_attribute_node(child, shape, chain, locate))
    return node


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
        for target in package.shapes.objects(shape, SH.targetClass):
            by_class.setdefault(target, []).append(shape)

    roots = []
    for cls in sorted(by_class, key=str):
        node = CookedNode(kind='type', label=local(cls), target_class=str(cls))
        own = 0
        for shape in by_class[cls]:
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


def _write_verified(source_path, text):
    """Write only after the result parses.

    A cooked edit that produces invalid Turtle would take the file with it, and
    the whole point of editing spans rather than reserialising is that the file
    survives.
    """
    from rdflib import Graph

    Graph().parse(data=text, format='turtle')
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
    updated = add_property_constraint(
        holder, shape, attribute, [(parameter, value)])
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
