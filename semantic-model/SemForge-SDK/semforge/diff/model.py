"""Model-level differences, classified rather than textual (section 11).

A textual diff of shacl.ttl says a line changed. What an author needs is
"minCount 1 -> 0, which WEAKENS this constraint, and here is the example that
now passes when it should not".

Direction is decidable for the parameter lattice and undecidable in general for
a SPARQL body. Where it is undecidable this says so -- `impact-unknown` -- rather
than guessing, and the behavioural layer (impact.py) settles it empirically by
running the examples.
"""

from dataclasses import dataclass
from enum import Enum

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, SH

from ..validate.applicable import PARAMETERS
from ..validate.normalise import curie, inverse_predicate, local
from ..validate.shapes import node_shapes, query_texts

# Which way a bound moves when it WEAKENS the constraint.
WEAKER_WHEN = {
    'MinCountConstraintComponent': 'decreases',
    'MinInclusiveConstraintComponent': 'decreases',
    'MinExclusiveConstraintComponent': 'decreases',
    'MinLengthConstraintComponent': 'decreases',
    'MaxCountConstraintComponent': 'increases',
    'MaxInclusiveConstraintComponent': 'increases',
    'MaxExclusiveConstraintComponent': 'increases',
    'MaxLengthConstraintComponent': 'increases',
}
COMPONENT_OF = {name: parameter for parameter, name in PARAMETERS.items()}


class Direction(Enum):
    WEAKENED = 'weakened'
    STRENGTHENED = 'strengthened'
    UNKNOWN = 'impact-unknown'


@dataclass(frozen=True)
class Change:
    # kind is one of: constraint-added, constraint-removed, parameter-changed,
    # shape-added, shape-removed, rule-added, rule-removed, rule-body-changed
    kind: str
    shape: str
    attribute: str = ''
    slot: str = ''            # '' for the attribute itself, 'value' for its value
    component: str = ''
    before: str = ''
    after: str = ''
    direction: Direction = Direction.UNKNOWN

    @property
    def constraint(self):
        parts = [local(self.shape)]
        if self.attribute:
            parts.append(self.attribute + ('.value' if self.slot == 'value' else ''))
        if self.component:
            parts.append(self.component)
        return '/'.join(parts)

    def __str__(self):
        detail = ''
        if self.before or self.after:
            detail = f' ({self.before or "-"} -> {self.after or "-"})'
        return f'{self.kind}: {self.constraint}{detail} [{self.direction.value}]'


def _fingerprint(value, graph, depth=0):
    """A label-free description of a constraint value.

    sh:or, sh:and and sh:node carry blank nodes, whose LABELS differ between two
    parses of the same file -- so comparing them directly reports every shape as
    changed on every diff. What matters is the structure, so that is what is
    compared: predicates and values, sorted, recursively.
    """
    if isinstance(value, Literal):
        return str(value)
    if isinstance(value, URIRef):
        return local(value)
    if not isinstance(value, BNode) or depth > 6:
        return '<node>'
    if (value, RDF.first, None) in graph:
        items = []
        node = value
        while node is not None and node != RDF.nil:
            item = graph.value(node, RDF.first)
            if item is None:
                break
            items.append(_fingerprint(item, graph, depth + 1))
            node = graph.value(node, RDF.rest)
        return '(' + ' '.join(items) + ')'
    parts = sorted(
        f'{local(predicate)}={_fingerprint(obj, graph, depth + 1)}'
        for predicate, obj in graph.predicate_objects(value))
    return '[' + ' '.join(parts) + ']'


def _attribute_for(path, shapes_graph, inherited):
    from ..validate.applicable import NGSILD_VALUE_PATHS
    from rdflib import BNode, URIRef

    if isinstance(path, URIRef) and str(path) not in NGSILD_VALUE_PATHS:
        return local(path)
    if isinstance(path, BNode):
        predicate = inverse_predicate(path, shapes_graph)
        if predicate is not None:
            return local(predicate)
    return inherited


def _walk(node, shapes_graph, attribute, slot, seen, out, shape):
    """Fingerprint every constraint below a shape node.

    `slot` separates a constraint on the ATTRIBUTE (how many instances) from one
    on its VALUE (what the value may be). Both are reached under the same
    attribute name, so without it the two collapse into one key -- and a change
    to one of them is masked by the other, which is how a real minCount edit
    went undetected the first time this ran.
    """
    if node in seen:
        return
    seen.add(node)
    for parameter, component in PARAMETERS.items():
        for value in shapes_graph.objects(node, parameter):
            out[(shape, attribute, slot, component)] = _fingerprint(value, shapes_graph)
    for child in shapes_graph.objects(node, SH.property):
        path = shapes_graph.value(child, SH.path)
        name = _attribute_for(path, shapes_graph, attribute)
        child_slot = 'value' if name == attribute and slot == '' and \
            attribute != '' else slot
        _walk(child, shapes_graph, name, child_slot, seen, out, shape)


def describe(shapes_graph):
    """{(shape, attribute, component): value} plus {shape: [rule bodies]}.

    The fingerprint a diff compares. Values are lexical so that `1` and `1.0`
    are visibly different rather than silently equal.
    """
    constraints = {}
    rules = {}
    for shape in node_shapes(shapes_graph):
        _walk(shape, shapes_graph, '', '', set(), constraints, str(shape))
        if (shape, SH.sparql, None) in shapes_graph:
            constraints[(str(shape), '', '', 'SPARQLConstraintComponent')] = 'sparql'
        bodies = query_texts(shapes_graph, shape)
        if bodies:
            rules[str(shape)] = sorted(' '.join(b.split()) for b in bodies)
    return constraints, rules


def _direction(component, before, after):
    """Which way a parameter change moves the constraint."""
    rule = WEAKER_WHEN.get(component)
    if rule is None:
        # A datatype, class or pattern change is not on a lattice: neither
        # value is more permissive than the other in general.
        return Direction.UNKNOWN
    try:
        moved_up = float(after) > float(before)
    except (TypeError, ValueError):
        return Direction.UNKNOWN
    if float(after) == float(before):
        return Direction.UNKNOWN
    weakened = moved_up if rule == 'increases' else not moved_up
    return Direction.WEAKENED if weakened else Direction.STRENGTHENED


def semantic_diff(before_graph, after_graph):
    """Classified changes between two shapes graphs."""
    before_constraints, before_rules = describe(before_graph)
    after_constraints, after_rules = describe(after_graph)

    before_shapes = {str(s) for s in node_shapes(before_graph)}
    after_shapes = {str(s) for s in node_shapes(after_graph)}

    changes = []
    for shape in sorted(after_shapes - before_shapes):
        changes.append(Change(kind='shape-added', shape=shape,
                              direction=Direction.STRENGTHENED))
    for shape in sorted(before_shapes - after_shapes):
        changes.append(Change(kind='shape-removed', shape=shape,
                              direction=Direction.WEAKENED))

    for key in sorted(set(before_constraints) | set(after_constraints)):
        shape, attribute, slot, component = key
        if shape not in before_shapes or shape not in after_shapes:
            continue                      # already reported as shape add/remove
        old = before_constraints.get(key)
        new = after_constraints.get(key)
        if old == new:
            continue
        if old is None:
            changes.append(Change(
                kind='constraint-added', shape=shape, attribute=attribute,
                slot=slot, component=component, after=new,
                direction=Direction.STRENGTHENED))
        elif new is None:
            changes.append(Change(
                kind='constraint-removed', shape=shape, attribute=attribute,
                slot=slot, component=component, before=old,
                direction=Direction.WEAKENED))
        else:
            changes.append(Change(
                kind='parameter-changed', shape=shape, attribute=attribute,
                slot=slot, component=component, before=old, after=new,
                direction=_direction(component, old, new)))

    for shape in sorted(set(before_rules) | set(after_rules)):
        old = before_rules.get(shape)
        new = after_rules.get(shape)
        if old == new:
            continue
        if old is None:
            kind, direction = 'rule-added', Direction.UNKNOWN
        elif new is None:
            kind, direction = 'rule-removed', Direction.WEAKENED
        else:
            # A changed SPARQL body is not on any lattice. Saying so is the
            # honest answer; impact.py settles it by running the examples.
            kind, direction = 'rule-body-changed', Direction.UNKNOWN
        changes.append(Change(kind=kind, shape=shape, direction=direction))
    return changes


def format_changes(changes, shapes_graph=None):
    lines = []
    for change in changes:
        name = curie(shapes_graph, change.shape) if shapes_graph is not None \
            else local(change.shape)
        attribute = change.attribute + ('.value' if change.slot == 'value' else '')
        suffix = '/'.join(p for p in (attribute, change.component) if p)
        detail = f' ({change.before or "-"} -> {change.after or "-"})' \
            if change.before or change.after else ''
        lines.append(f'{change.kind:<18} {name}'
                     f'{"/" + suffix if suffix else ""}{detail}'
                     f'  [{change.direction.value}]')
    return lines
