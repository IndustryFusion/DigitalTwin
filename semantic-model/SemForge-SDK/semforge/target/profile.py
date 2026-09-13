"""Target profile descriptors and the static capability check (section 9.1).

A profile says what a compilation target can express, as data. The check runs
BEFORE the compiler is invoked, so a capability problem is a constraint-level
diagnostic with a file and a line -- something an author can act on -- rather
than a stack trace from a code generator.

Invariant C1: unsupported fails loudly, and reports every problem at once. The
failure mode it replaces is undetectable from outside, because an uncompiled
constraint produces no alert and no alert is exactly what a satisfied constraint
produces.
"""

import re
from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import SH

from ..errors import Diagnostic
from ..ngsild import DataView
from ..validate.applicable import NGSILD_VALUE_PATHS, PARAMETERS
from ..validate.normalise import local

ATTRIBUTE_PREDICATE = re.compile(r'\b(?:iff\w*|ex):\w+\s*(?:\[|\?)')


@dataclass
class Profile:
    name: str
    max_subproperty_depth: int = 2      # levels BELOW the attribute
    components: set = field(default_factory=set)
    unsupported: list = field(default_factory=list)
    supports_history_view: bool = False

    @property
    def max_levels(self):
        """Attribute plus sub-attributes: depth 2 means three levels."""
        return self.max_subproperty_depth + 1


def builtin_profile(name='shacl2flink'):
    """The shacl2flink profile, as its own documentation describes it.

    max_subproperty_depth mirrors MAX_SUBPROPERTY_DEPTH in
    shacl2flink/lib/utils.py, which is 2 -- deliberately not set higher than a
    real model has needed, because every level costs one more join of
    attributes_view for every deployment.
    """
    if name != 'shacl2flink':
        raise KeyError(f'unknown profile: {name}')
    return Profile(
        name='shacl2flink',
        max_subproperty_depth=2,
        components={
            'MinCountConstraintComponent', 'MaxCountConstraintComponent',
            'DatatypeConstraintComponent', 'NodeKindConstraintComponent',
            'ClassConstraintComponent', 'MinInclusiveConstraintComponent',
            'MaxInclusiveConstraintComponent', 'MinExclusiveConstraintComponent',
            'MaxExclusiveConstraintComponent', 'MinLengthConstraintComponent',
            'MaxLengthConstraintComponent', 'PatternConstraintComponent',
            'InConstraintComponent', 'HasValueConstraintComponent',
            'NodeConstraintComponent', 'OrConstraintComponent',
            'AndConstraintComponent', 'NotConstraintComponent',
            'SPARQLConstraintComponent',
        },
        # "sh:xone inside the value shape of ngsi-ld:hasValue is not supported.
        # Only sh:or is descended into at the value level."
        unsupported=[('XoneConstraintComponent', 'value-shape',
                      'only sh:or is descended into at the value level')],
        supports_history_view=True)


def _depth_walk(node, shapes_graph, level, seen):
    """(shape node, level, has_constraint) for every property shape below."""
    if node in seen:
        return []
    seen.add(node)
    out = []
    for child in shapes_graph.objects(node, SH.property):
        path = shapes_graph.value(child, SH.path)
        named = isinstance(path, URIRef) and str(path) not in NGSILD_VALUE_PATHS
        child_level = level + 1 if named else level
        constraints = [name for parameter, name in PARAMETERS.items()
                       if (child, parameter, None) in shapes_graph]
        if named:
            out.append((child, path, child_level, constraints))
        out.extend(_depth_walk(child, shapes_graph, child_level, seen))
    return out


def check_package(package, profile, index=None):
    """Diagnostics for everything the profile cannot express.

    Reports all of them; the caller decides whether to stop.
    """
    from ..validate import shapes as shape_views

    shapes_graph = package.shapes
    index = index or package.index('shapes')
    found = []

    for shape in shape_views.node_shapes(shapes_graph):
        locator = index.locator(shape)

        for child, path, level, constraints in _depth_walk(
                shape, shapes_graph, 0, set()):
            if level > profile.max_levels:
                found.append(Diagnostic(
                    code='SF-CAP-001', category='capability', severity='error',
                    subject=str(shape), locator=locator,
                    message=(f'{local(shape)}: the path to {local(path)} is '
                             f'{level} levels deep; the {profile.name} profile '
                             f'compiles at most {profile.max_levels}')))
            unknown = [c for c in constraints if c not in profile.components]
            if unknown:
                found.append(Diagnostic(
                    code='SF-CAP-002', category='capability', severity='error',
                    subject=str(shape), locator=locator,
                    message=(f'{local(shape)}: {local(path)} uses '
                             f'{", ".join(sorted(unknown))}, which the '
                             f'{profile.name} profile does not compile')))
            for component, context, reason in profile.unsupported:
                if component in constraints and context == 'value-shape':
                    found.append(Diagnostic(
                        code='SF-CAP-003', category='capability', severity='error',
                        subject=str(shape), locator=locator,
                        message=(f'{local(shape)}: {component} on '
                                 f'{local(path)} is not supported -- {reason}')))
            if not constraints and not list(shapes_graph.objects(child, SH.property)):
                # shacl2flink rejects a property shape that names an attribute
                # and produces no constraint at all: it would compile to
                # nothing, and nothing is indistinguishable from conformance.
                found.append(Diagnostic(
                    code='SF-CAP-004', category='capability', severity='error',
                    subject=str(shape), locator=locator,
                    message=(f'{local(shape)}: the property shape for '
                             f'{local(path)} declares no constraint; it would '
                             f'compile to nothing and never be evaluated')))

        found.extend(_check_mixed_view(shape, shapes_graph, locator))
    return found


def _check_mixed_view(shape, shapes_graph, locator):
    """Refuse a query that would need per-variable view selection.

    The platform resolves AGGREGATED variables to the raw attributes table and
    everything else to attributes_view, per variable inside one query
    (lib/bgp_translation_utils.replace_attributes_table_expression). pyshacl
    evaluates one graph and cannot: the history graph multiplies rows for the
    non-aggregated variable, the current graph collapses the aggregate.

    The test is deliberately conservative -- an aggregating query that also
    reads more than one attribute is refused. Over-refusing costs an author an
    explicit acknowledgement; under-refusing computes a plausible wrong number
    and reports it as a verdict.
    """
    from ..validate.shapes import aggregates, view_of

    if view_of(shapes_graph, shape) is not DataView.HISTORY:
        return []
    out = []
    for text in _query_texts(shapes_graph, shape):
        if not aggregates(text):
            continue
        attributes = set(ATTRIBUTE_PREDICATE.findall(text))
        if len(re.findall(r'\b\w+:\w+\s*\[', text)) > 1 or len(attributes) > 1:
            out.append(Diagnostic(
                code='SF-CAP-005', category='capability', severity='error',
                subject=str(shape), locator=locator,
                message=(f'{local(shape)}: aggregates over one attribute while '
                         f'reading others. The target selects a data view per '
                         f'VARIABLE; a single-graph evaluation cannot, so this '
                         f'shape cannot be validated offline. Split it, or '
                         f'aggregate over a single attribute.')))
    return out


def _query_texts(shapes_graph, shape):
    from ..validate.shapes import query_texts
    return query_texts(shapes_graph, shape)
