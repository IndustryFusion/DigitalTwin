#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""The shape page: what one shape checks, and what it reaches.

The type page reads constraints by type ("what must a Filter carry"). A shape
is the other unit: what SHACL actually evaluates, and the only home a shape
has when it targets something other than one entity type -- a named node, the
subjects of a predicate, a SPARQL query -- or nothing, being reached through
sh:node. Built from the same rows the type page uses, so an attribute reads
the same on both.
"""

import os
import re


from rdflib import URIRef
from rdflib.namespace import RDF, RDFS, SH

from ..errors import PackageError
from ..validate.normalise import curie, local
from ..validate.results import Status
from .shapes import is_rule_only, target_short, targets, used_by
from .typepage import (PENDING, _attribute_rows, _cases, _coverage, _examples_root,
                       _rules, _short)

# The nodes a page lists by name; past this it says how many more.
LISTED = 50


def _resolve(package, shape):
    from ..validate.shapes import every_node_shape

    wanted = str(shape or '').strip('<>')
    for candidate in every_node_shape(package.shapes):
        if wanted in (str(candidate), curie(package.shapes, candidate)) or \
                wanted == str(candidate).rsplit('/', 1)[-1]:
            return candidate
    raise PackageError(f'{shape} is not a shape in this package')


def _reach(package, shape, graph):
    """The focus nodes this shape selects in one data graph. A shape with no
    target of its own reaches whatever the shapes using it at the top level
    reach."""
    from ..validate.applicable import focus_nodes

    nodes = set(focus_nodes(shape, package.shapes, graph, package.knowledge))
    if not targets(package, shape):
        for user in used_by(package, shape):
            if (URIRef(user), SH.node, shape) in package.shapes:
                nodes |= set(focus_nodes(URIRef(user), package.shapes, graph,
                                         package.knowledge))
    return {str(node) for node in nodes}


def _types_of(graph, nodes):
    return {str(o) for node in nodes for o in graph.objects(URIRef(node), RDF.type)}


SEVERITY = {str(SH.Violation): 'violation', str(SH.Warning): 'warning',
            str(SH.Info): 'info'}


def _query(package, holder, predicate):
    """A SPARQL body as written, its sh:prefixes declarations put back in
    front so it reads the way it runs."""
    graph = package.shapes
    body = graph.value(holder, predicate)
    if body is None:
        return ''
    lines = []
    for prefixes in graph.objects(holder, SH.prefixes):
        for declaration in graph.objects(prefixes, SH.declare):
            prefix = graph.value(declaration, SH.prefix)
            namespace = graph.value(declaration, SH.namespace)
            if prefix is not None and namespace is not None:
                lines.append(f'PREFIX {prefix}: <{namespace}>')
    return '\n'.join(lines + [str(body).strip()])


def _severity(value, default='violation'):
    """sh:Violation -> 'violation'; a package's own term (the kms's
    base:severityWarning) -> its name, 'warning'."""
    if value is None:
        return default
    if str(value) in SEVERITY:
        return SEVERITY[str(value)]
    name = str(value).rstrip('/#').rsplit('/', 1)[-1].rsplit('#', 1)[-1]
    name = re.sub(r'^severity', '', name, flags=re.IGNORECASE)
    return name[:1].lower() + name[1:] if name else default


def _checks(package, shape):
    """The shape's SPARQL constraints and rules: what each says it checks,
    how severe, and the query itself -- read-only, edited in the .ttl."""
    graph = package.shapes
    severity = _severity(graph.value(shape, SH.severity))
    out = []
    for holder in graph.objects(shape, SH.sparql):
        message = graph.value(holder, SH.message)
        # Whether anyone SAID how severe: SHACL's default is sh:Violation, and
        # a default shown like a declared value reads as a verdict.
        declared = graph.value(holder, SH.severity) is not None or \
            graph.value(shape, SH.severity) is not None
        from .severity import describe
        value = graph.value(holder, SH.severity) or graph.value(shape, SH.severity)
        out.append({'kind': 'constraint', 'message': str(message or ''),
                    'severity': describe(package, value)['label'] if value is not None
                    else severity,
                    'severityDeclared': declared,
                    'query': _query(package, holder, SH.select)})
    for holder in graph.objects(shape, SH.rule):
        comment = next((str(c) for c in graph.objects(holder, RDFS.comment)), '')
        out.append({'kind': 'rule', 'message': comment, 'severity': '',
                    'query': _query(package, holder, SH.construct)})
    return out


def build_shape_page(package, shape, verdicts=None):
    """The payload the shape page renders. Reads only.

    `verdicts` as for build_type_page: PENDING builds the structure with
    "evaluating" where a verdict belongs; without it, validated here.
    """
    from ..expect.runner import run_tests
    from ..sanity import known_constraints
    from ..validate import validate_package
    from .choices import attribute_terms, entity_types
    from .tree import shape_node

    shape = _resolve(package, shape)
    name = curie(package.shapes, shape)
    node = shape_node(package, shape)
    declared = targets(package, shape)
    users = used_by(package, shape)

    cases = _cases(package, verdicts)
    coverage = _coverage(cases)
    kind_of = {a.iri: a.kind for a in attribute_terms(package) if a.kind}

    if verdicts is PENDING:
        report = None
    elif verdicts is not None:
        report = verdicts.model
    else:
        report = validate_package(package, strict=False)
    pending = report is None
    mine = [] if pending else [v for v in report.violations if str(v.shape) == str(shape)]
    violated = {}
    for violation in mine:
        violated.setdefault((name, violation.attribute or ''), []).append(
            str(violation.resource))

    attributes = []
    for child in (node.children if node else []):
        if child.kind == 'attribute':
            attributes += _attribute_rows(package, child, kind_of, 0, coverage,
                                          violated)
    rules = _rules(package, [node], coverage) if node else []

    # What it reaches: in the model, and in every case.
    reached = sorted(_reach(package, shape, package.model))
    known = {entry.iri: entry.label for entry in entity_types(package)[0]}
    types = _types_of(package.model, reached)
    cases_pending = any(r is None for _, _, r in cases)
    outcomes = {} if cases_pending else {o.example: o for o in run_tests(
        [(example, case_report) for example, _, case_report in cases],
        known_constraints(package))}
    exercised = []
    for example, graph, case_report in cases:
        nodes = _reach(package, shape, graph)
        if not nodes:
            continue
        types |= _types_of(graph, nodes)
        firing = [] if case_report is None else \
            [v for v in case_report.violations if str(v.shape) == str(shape)]
        fired = None if case_report is None else len(firing)
        # Holds only where something was checked: an entity without any of
        # the shape's attributes satisfies it of nothing (Result.vacuous).
        held = None if case_report is None else any(
            r.status is Status.CONFORMANT and not r.vacuous and str(r.shape) == str(shape)
            for r in case_report.results)
        outcome = outcomes.get(example.path)
        exercised.append({
            'case': example.path, 'description': example.description,
            'expect': example.expect, 'entities': sorted(nodes)[:LISTED],
            'fired': fired, 'held': held,
            'firedOn': sorted({str(v.resource) for v in firing}),
            'passed': None if cases_pending else bool(outcome and outcome.passed),
            'file': os.path.join(_examples_root(package), example.path)})

    problems = {}
    for violation in mine:
        problems.setdefault(str(violation.resource), []).append(
            f'{violation.attribute or name} · '
            f'{str(violation.component).replace("ConstraintComponent", "")}')

    fired_anywhere = any(case['fired'] for case in exercised)
    return {
        'iri': str(shape), 'name': name, 'label': _short(name),
        'definedAt': node.defined_at if node else '',
        'targets': declared,
        'target': target_short(package, shape, declared, users),
        'usedBy': [{'iri': u, 'name': curie(package.shapes, URIRef(u))} for u in users],
        'rule': is_rule_only(node),
        'checks': _checks(package, shape),
        # The page edits the shape itself: + Attribute and every row action
        # write into it, as the type page's write into the type's own shape.
        'ownShape': str(shape), 'ownShapeName': name,
        # New test… needs an entity of a type: the class the shape targets.
        'testType': next((t['value'] for t in declared
                          if t['kind'] in ('class', 'implicit')), ''),
        # What carries the attributes, for prompts ("present on every Filter?").
        'subject': next((local(t['value']) for t in declared
                         if t['kind'] in ('class', 'implicit')),
                        f'focus node of {_short(name)}'),
        # New case… writes a case asserting this; only a SPARQL constraint has one.
        'canNewCase': (shape, SH.sparql, None) in package.shapes and bool(declared),
        'attributes': attributes, 'rules': rules,
        # Entity types are links to their pages; anything else is a name.
        'types': sorted([{'iri': t, 'label': known[t], 'page': True} if t in known
                         else {'iri': t, 'label': _short(t), 'page': False}
                         for t in types], key=lambda t: t['label'].lower()),
        'reach': {'model': len(reached),
                  'nodes': [{'id': n, 'violations': None if pending else problems.get(n, [])}
                            for n in reached[:LISTED]],
                  'more': max(0, len(reached) - LISTED)},
        'exercisedBy': exercised,
        'summary': {
            'reached': len(reached), 'violations': None if pending else len(mine),
            'cases': len(exercised),
            'casesFailing': sum(1 for e in exercised if e['passed'] is False),
            'neverFired': None if cases_pending
            else not fired_anywhere and bool(attributes or rules),
        },
    }
