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

"""The entity type page: everything about one type, on one screen.

The sidebar trees print the SHACL encoding a parameter per row -- Filter alone
is 39 rows -- and split "what is a Filter, and is it healthy?" across three
views. This assembles the answer once: where the type sits, every attribute it
must or may carry (its own and inherited, sub-attributes under their parent),
the rules that judge it, which cases exercise it, and what is wrong with its
instances in the model.

It reads the constraint tree rather than the shapes graph, so the page and the
tree cannot disagree about what a shape says; it only re-presents it, in the
vocabulary of the model rather than of SHACL:

    sh:minCount 1 · sh:maxCount 1               required · one
    hasObject · sh:class C                      → C
    hasValue · sh:class C                       one of C
    sh:or of number datatypes                   number
    sh:minInclusive 0 · sh:maxInclusive 100     0 – 100

Anything the vocabulary does not cover is shown verbatim, never dropped.
Protocol-free, like the rest of cooked/: the LSP server serialises the result.
"""

import os
import re

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, SH

from ..errors import PackageError
from ..ngsild.kinds import is_relationship
from ..validate.normalise import curie

NUMBER_TYPES = {'xsd:double', 'xsd:decimal', 'xsd:integer', 'xsd:float',
                'xsd:int', 'xsd:long', 'xsd:short', 'xsd:nonNegativeInteger',
                'xsd:positiveInteger'}
DATATYPE_WORDS = {'xsd:string': 'text', 'xsd:boolean': 'true / false',
                  'xsd:dateTime': 'date and time', 'xsd:date': 'date',
                  'xsd:anyURI': 'URL', 'rdf:JSON': 'JSON'}
COUNT_PARAMETERS = {'sh:minCount', 'sh:maxCount'}
# Parameters the vocabulary renders; anything else on a slot is shown verbatim.
RENDERED = COUNT_PARAMETERS | {'sh:class', 'sh:datatype', 'sh:nodeKind',
                               'sh:minInclusive', 'sh:maxInclusive',
                               'sh:minExclusive', 'sh:maxExclusive', 'sh:in',
                               'sh:minLength', 'sh:maxLength', 'sh:pattern'}


# --- the vocabulary ---------------------------------------------------------------

def _short(term):
    """`iffBaseEntities:Filter` -> `Filter`; inside one package the prefix
    rarely tells the reader anything."""
    return str(term).strip('<>').rsplit('/', 1)[-1].rsplit('#', 1)[-1].split(':')[-1]


def _number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return str(text)
    return str(int(value)) if value.is_integer() else str(value)


def presence(minimum, maximum):
    """The cardinality of an attribute, as a person would say it."""
    low = int(float(minimum)) if minimum not in (None, '') else 0
    high = int(float(maximum)) if maximum not in (None, '') else None
    if high == 0:
        return 'forbidden'
    if low == 0 and high == 1:
        return 'optional'
    if low == 0 and high is None:
        return 'any number'
    if low == 1 and high == 1:
        return 'required · one'
    if high is None:
        return f'at least {low}'
    if low == high:
        return f'exactly {low}'
    return f'{low} to {high}' if low else f'at most {high}'


def _numbers_only(alternatives):
    """Is an sh:or a choice between number datatypes only? The kms writes
    `( [sh:datatype xsd:double] [sh:datatype xsd:integer] )` for "a number"."""
    found = re.findall(r'sh:datatype\s+([\w:]+)', str(alternatives))
    return bool(found) and all(datatype in NUMBER_TYPES for datatype in found)


def value_text(kind, parameters, raw):
    """What the value must be: `→ Filter`, `one of MachineState`, `number ·
    0 – 100`. `parameters` are the value layer's {name: value}; `raw` the
    parameters the tree could only show verbatim (sh:or and the like)."""
    parts = []
    cls = parameters.get('sh:class')
    datatype = parameters.get('sh:datatype')
    if cls:
        parts.append(f'→ {_short(cls)}' if kind == 'Relationship'
                     else f'one of {_short(cls)}')
    elif datatype:
        parts.append('number' if datatype in NUMBER_TYPES
                     else DATATYPE_WORDS.get(datatype, datatype))
    elif any(name == 'sh:or' and _numbers_only(value) for name, value in raw):
        parts.append('number')
    low_in, low_ex = parameters.get('sh:minInclusive'), parameters.get('sh:minExclusive')
    high_in, high_ex = parameters.get('sh:maxInclusive'), parameters.get('sh:maxExclusive')
    if low_in is not None and high_in is not None and low_ex is None and high_ex is None:
        parts.append(f'{_number(low_in)} – {_number(high_in)}')
    else:
        # An exclusive bound says so: "> 0" is not "≥ 0".
        bounds = [f'≥ {_number(low_in)}' if low_in is not None else '',
                  f'> {_number(low_ex)}' if low_ex is not None else '',
                  f'≤ {_number(high_in)}' if high_in is not None else '',
                  f'< {_number(high_ex)}' if high_ex is not None else '']
        if any(bounds):
            parts.append(' and '.join(b for b in bounds if b))
    shortest, longest = parameters.get('sh:minLength'), parameters.get('sh:maxLength')
    if shortest is not None and longest is not None:
        parts.append(f'{_number(shortest)} – {_number(longest)} characters')
    elif shortest is not None:
        parts.append(f'at least {_number(shortest)} characters')
    elif longest is not None:
        parts.append(f'at most {_number(longest)} characters')
    if parameters.get('sh:pattern'):
        parts.append(f'matching {str(parameters["sh:pattern"]).strip(chr(34))}')
    # sh:in is structure (a list), so it may arrive with the raw parameters.
    listed = parameters.get('sh:in') or dict(raw or []).get('sh:in')
    if listed:
        from .tree import list_items

        from .listcheck import QUOTED

        def said(item):
            quoted = QUOTED.fullmatch(item)
            return quoted.group(1) if quoted else _short(item)
        parts.append('one of: ' + ' · '.join(said(v) for v in list_items(listed)))
    if not parts:
        parts.append('an entity' if kind == 'Relationship' else 'any value')
    return ' · '.join(parts)


# --- the type --------------------------------------------------------------------

def _type_entry(package, entity_type):
    from .choices import entity_types

    wanted = str(entity_type or '').strip('<>')
    for entry in entity_types(package)[0]:
        if wanted in (entry.iri, entry.term, entry.label):
            return entry
    raise PackageError(f'{entity_type} is not an entity type this package '
                       f'declares')


def _ancestors(package, iri):
    """[root, ..., parent] -- the breadcrumb."""
    chain, current, seen = [], URIRef(iri), set()
    while current not in seen:
        seen.add(current)
        parents = [p for p in package.knowledge.objects(current, RDFS.subClassOf)
                   if isinstance(p, URIRef)]
        if not parents:
            break
        current = parents[0]
        chain.insert(0, str(current))
    return chain


def _family(package, iri):
    """The type and everything below it: an instance of a Plasmacutter is an
    instance of a Cutter for every page that asks."""
    found, pending = {str(iri)}, [URIRef(iri)]
    while pending:
        current = pending.pop()
        for child in package.knowledge.subjects(RDFS.subClassOf, current):
            if str(child) not in found:
                found.add(str(child))
                pending.append(child)
    return found


# --- attributes, from the constraint tree --------------------------------------------

def _params(node):
    """{parameter: value} of a tree node's direct constraint children, and the
    raw-only ones as [(name, text)]."""
    params, raw = {}, []
    for child in node.children:
        if child.kind == 'constraint' and child.parameter:
            params[child.parameter] = child.value
        elif child.kind == 'raw' and not child.label.startswith('SPARQL'):
            # By its parameter: the label of an sh:or the tree could read says
            # what it means (`value: Property or ListProperty`), not its name.
            raw.append((child.parameter or child.label.replace(' (raw only)', ''),
                        child.value))
    return params, raw


def _units_of(node):
    """(codes, required) of an attribute node's unit constraint -- the nested
    sh:property on ngsild:unitCode -- or ([], False)."""
    from .tree import list_items

    unit = next((c for c in node.children if c.kind == 'unit'), None)
    if unit is None:
        return [], False
    listed = next((c.value for c in unit.children if c.parameter == 'sh:in'), '')
    least = next((c.value for c in unit.children if c.parameter == 'sh:minCount'), '0')
    codes = [item.strip().strip('"') for item in list_items(listed)] if listed else []
    return codes, str(least).strip() not in ('', '0')


CONNECTIVE_NAMES = ('sh:or', 'sh:and', 'sh:xone', 'sh:not')
PLAIN_PAYLOADS = ('hasValue', 'hasObject')


def _value_of(package, node):
    """The attribute's value as its forms (cooked/valueforms.py) -- the one
    reader the page, the value editor and the constraints view share."""
    from ..rdfio.frozen import derived
    from .valueforms import Value, read_value

    # Kept with the shapes graph: an edit gives the package a new one.
    known = derived(package.shapes, 'row_values', dict, depends=(package.knowledge,),
                    key=(package.path,))
    key = (node.shape, tuple(node.path_chain))
    if key in known:
        return known[key]
    index = package.index('shapes')
    holder = index.file_for(URIRef(node.shape)) if node.shape else None
    if holder is None:
        value = Value((), '', editable=False, reason='its shape is in no shapes file')
    else:
        try:
            value = read_value(package, index.source_of(holder), node.shape,
                               list(node.path_chain))
        except PackageError as exc:
            value = Value((), '', editable=False, reason=str(exc))
    known[key] = value
    return value


def _value_fields(value, kind):
    """What a row says about its value, from the value alone. Changing it is
    the attribute editor's (attributepanel.js), which reads the value itself."""
    from .expression import to_json
    from .valueforms import say

    forms = value.forms
    one = forms[0] if len(forms) == 1 else None
    connectives = one is not None and one.payload in PLAIN_PAYLOADS and \
        len(one.root.children) > 1
    return {
        'kinds': [f.kind for f in forms] or [kind],
        'forms': [{'kind': f.kind, 'payload': f.payload, 'mayBeEmpty': f.may_be_empty}
                  for f in forms],
        'value': say(value) if forms else ('an entity' if kind == 'Relationship'
                                           else 'any value'),
        'valueEditable': value.editable,
        'valueLocked': '' if value.editable else f'edited in the .ttl: {value.reason}',
        # The expression, as a tree under the value, when it is one.
        'expression': to_json(one.root, kind) if connectives else None,
    }


def _attribute_rows(package, node, kind_of, depth, coverage, violated):
    """One row per attribute node, its sub-attributes after it."""
    from .units import unit_text

    own, raw_outer = _params(node)
    units, unit_required = _units_of(node)
    slot = next((c for c in node.children if c.kind == 'slot'), None)
    value_params, raw = _params(slot) if slot is not None else ({}, [])
    token = node.detail or node.label
    iri = str(_resolve_token(package, token))
    value = _value_of(package, node)
    kind = kind_of.get(iri) or (
        'Relationship' if any(is_relationship(f.kind) for f in value.forms) else 'Property')
    shape_name = curie(package.shapes, URIRef(node.shape)) if node.shape else ''
    # Verbatim is for what the words could NOT say: what an editable value
    # says is in its words (connectives included); one SemForge does not edit
    # is shown as written.
    extra = [f'{name} {text}' for name, text in raw + raw_outer
             if name != 'sh:severity' and not (value.editable and name in CONNECTIVE_NAMES)]
    extra += [f'{name} {text}' for name, text in value_params.items()
              if name not in RENDERED and not (value.editable and name in (
                  'sh:hasValue', 'sh:flags'))]
    tested = coverage.get((shape_name, _short(token)), 'untested')
    # Every parameter with the address an edit needs: its sh:path chain (the
    # value layer's includes the slot) and its name. "Edit a parameter" and
    # "Override" act on exactly these.
    parameters = [{'parameter': c.parameter, 'value': c.value,
                   'path': list(c.path_chain), 'layer': layer}
                  for layer, holder in (('attribute', node), ('value', slot))
                  if holder is not None
                  for c in holder.children
                  if c.kind == 'constraint' and c.parameter]
    # How serious its results are: said by the level's label, SHACL's
    # default (violation) when the property shape declares none.
    from .severity import describe
    # The tree keeps sh:severity among the parameters it does not render.
    severity_token = own.get('sh:severity') or next(
        (value for name, value in raw_outer if name == 'sh:severity'), None)
    severity = describe(package, str(_resolve_token(package, severity_token))
                        if severity_token else None)
    fields = _value_fields(value, kind)
    from .tree import _short as path_label     # a complex path reads as a property path
    rows = [{
        'attribute': iri, 'label': path_label(token), 'term': token, 'kind': kind,
        'presence': presence(own.get('sh:minCount'), own.get('sh:maxCount')),
        'value': ' · '.join(p for p in (
            fields['value'],
            f'in {unit_text(package, units)}' if units else '',
            'unit required' if unit_required else '') if p),
        # The units its instances may say (ngsild:unitCode), and whether one
        # is required -- what Unit… edits.
        'units': units, 'unitRequired': unit_required,
        'verbatim': extra,
        'shape': node.shape, 'shapeName': shape_name,
        'inherited': bool(node.inherited_from),
        'inheritedFrom': _short(node.inherited_class) if node.inherited_class else '',
        'depth': depth, 'tested': tested,
        'severity': severity['label'], 'severityDeclared': bool(severity_token),
        'severityKnown': severity['known'],
        'path': list(node.path_chain), 'parameters': parameters,
        # Kinds, forms, editable or not, the expression, the list switch:
        # all from the one value (_value_fields).
        **{k: v for k, v in fields.items() if k != 'value'},
        # The value's sh:in list, item by item, for the Constraints… editor.
        'inList': _in_list(raw, value_params, slot),
        # What the list contradicts on the same value, said on the row.
        'notes': _list_notes(package, raw, value_params, slot),
        'violations': violated.get((shape_name, _short(token)), []) +
        violated.get((shape_name, _short(token) + '.unitCode'), []),
        'definedAt': node.defined_at,
    }]
    for child in node.children:
        if child.kind == 'attribute':
            rows += _attribute_rows(package, child, kind_of, depth + 1,
                                    coverage, violated)
    return rows


def _in_list(raw, value_params, slot):
    """{'items', 'path', 'value'} of the value layer's sh:in, or None."""
    from .tree import list_items

    text = dict(raw).get('sh:in') or value_params.get('sh:in')
    if not text or slot is None:
        return None
    return {'items': list_items(text), 'path': list(slot.path_chain), 'value': text}


def _list_notes(package, raw, value_params, slot):
    from .listcheck import list_conflicts

    found = _in_list(raw, value_params, slot)
    return list_conflicts(package, value_params, found['items']) if found else []


def _resolve_token(package, token):
    from .constrain import _resolve

    return _resolve(package, token) or token


# --- rules -----------------------------------------------------------------------

def _rule_text(package, shape):
    """What a SPARQL shape is for: its sh:message, its comment, or nothing."""
    graph = package.shapes
    for sparql in graph.objects(URIRef(shape), SH.sparql):
        for message in graph.objects(sparql, SH.message):
            if isinstance(message, Literal) and '{' not in str(message):
                return str(message)
    for holder in [URIRef(shape)] + list(graph.objects(URIRef(shape), SH.rule)):
        for comment in graph.objects(holder, RDFS.comment):
            return str(comment)
    return ''


def _rules(package, shape_nodes, coverage):
    rows = []
    for shape_node in shape_nodes:
        for child in shape_node.children:
            if child.kind != 'raw' or not child.label.startswith('SPARQL'):
                continue
            name = curie(package.shapes, URIRef(shape_node.shape))
            is_rule = child.label == 'SPARQL rule'
            rows.append({
                'shape': shape_node.shape, 'shapeName': name,
                'kind': 'rule' if is_rule else 'constraint',
                'text': _rule_text(package, shape_node.shape),
                'inherited': bool(shape_node.inherited_from),
                'inheritedFrom': _short(shape_node.inherited_class)
                if shape_node.inherited_class else '',
                # A rule CONSTRUCTS; "never fired" would be a category error.
                'tested': '' if is_rule else coverage.get((name, ''), 'untested'),
                'definedAt': child.defined_at or shape_node.defined_at})
    return rows


# --- the data ----------------------------------------------------------------------

def _cases(package, verdicts=None):
    """[(example, graph, report)] for every declared case.

    The report comes from `verdicts` (editor/verdicts.py), None while they are
    being computed; without `verdicts` at all each case is validated here.
    """
    from ..expect.store import compose, load_expectations
    from ..validate.orchestrator import validate_graphs

    out = []
    for example in load_expectations(package.path).examples:
        try:
            graph = compose(package, example)
        except PackageError:
            continue
        if verdicts is PENDING:
            report = None
        elif verdicts is not None:
            report = verdicts.cases.get(example.path)
        else:
            report = validate_graphs(graph, package.shapes, package.knowledge, strict=False)
        out.append((example, graph, report))
    return out


class _Evaluating(dict):
    """Coverage while the verdicts are computed: every row says so."""

    def get(self, key, default=None):
        return 'evaluating'


# Passed as `verdicts` to build a page before any are known.
PENDING = object()


def _coverage(cases):
    if any(report is None for _, _, report in cases):
        return _Evaluating()
    return _known_coverage(cases)


def _known_coverage(cases):
    """{(shape CURIE, attribute local name or ''): 'both ways' | 'fires only'
    | 'never fired'} across every case, per attribute rather than per
    parameter: the page asks whether an attribute's constraints are tested."""
    from ..expect import coverage

    out = {}
    for entry in coverage([(example, report) for example, _, report in cases]):
        parts = entry.constraint.split('/')
        # hasX.hasValue and hasX.unitCode are hasX's own: its value's and its
        # unit's constraints count toward the attribute's row.
        key = (parts[0], parts[1].split('.')[0] if len(parts) == 3 else '')
        status = ('both ways' if entry.has_firing and entry.has_conforming
                  else 'fires only' if entry.has_firing else 'never fired')
        rank = {'never fired': 0, 'fires only': 1, 'both ways': 2}
        if key not in out or rank[status] > rank[out[key]]:
            out[key] = status
    return out


def _also_checked_by(package, family, cases):
    """Shapes with no class target that reach an entity of this type -- in
    the model or in any case. A shape is not tied to a type: one targeting
    the subjects of hasValve judges every pump that has a valve, and the
    pump's page would otherwise never mention it."""
    from ..validate.shapes import every_node_shape, node_shapes
    from .shapepage import _reach
    from .shapes import target_short, targets

    classed = set(node_shapes(package.shapes))
    graphs = [package.model] + [graph for _, graph, _ in cases]
    out = []
    for shape in every_node_shape(package.shapes):
        if shape in classed:
            continue
        condition = _applies(package, shape, family, targets(package, shape))
        reached = set()
        for graph in graphs:
            for node in _reach(package, shape, graph):
                if {str(o) for o in graph.objects(URIRef(node), RDF.type)} & family:
                    reached.add(node)
        if condition is None and not reached:
            continue
        out.append({'shape': str(shape),
                    'shapeName': curie(package.shapes, shape),
                    'target': target_short(package, shape),
                    'condition': condition if condition is not None
                    else _condition(package, shape),
                    'reached': len(reached)})
    return out


def _lineage(package, iri):
    """The type and every class above it."""
    found, pending = {str(iri)}, [URIRef(iri)]
    while pending:
        for parent in package.knowledge.objects(pending.pop(), RDFS.subClassOf):
            if isinstance(parent, URIRef) and str(parent) not in found:
                found.add(str(parent))
                pending.append(parent)
    return found


def _condition(package, shape):
    """When a shape that does not target the type by class applies to one of
    its entities, in words."""
    from .shapes import targets, used_by

    declared = targets(package, shape)
    if not declared:
        users = used_by(package, shape)
        return ('only where ' + ', '.join(_short(curie(package.shapes, URIRef(u)))
                                          for u in users) + ' reaches it') if users \
            else 'never: nothing targets it'
    words = []
    for target in declared:
        if target['kind'] == 'subjectsOf':
            words.append(f'only when it has {_short(target["value"])}')
        elif target['kind'] == 'objectsOf':
            words.append('only when a Relationship points at it')
        elif target['kind'] == 'node':
            words.append(f'only for {target["value"]}')
        elif target['kind'] == 'sparql':
            words.append('only for the entities its SPARQL target selects')
        elif target['kind'] in ('class', 'implicit'):
            words.append('every one')
    return ' or '.join(words)


def _applies(package, shape, family, declared):
    """The condition under which a shape with no class target applies to
    entities of this type, decided from the model alone -- or None when only
    the data can say (a named node, a SPARQL target)."""
    lineage = set()
    for member in family:
        lineage |= _lineage(package, member)
    for target in declared:
        if target['kind'] == 'implicit' and target['value'] in lineage:
            return ''                      # it IS a class over this type
        if target['kind'] == 'subjectsOf':
            from .choices import domains_of
            domains = {str(d) for d in domains_of(package.knowledge,
                                                  URIRef(target['value']))}
            if domains & lineage:
                return f'only when it has {_short(target["value"])}'
        if target['kind'] == 'objectsOf' and \
                target['value'] == 'https://uri.etsi.org/ngsi-ld/hasObject':
            pointed = {str(c) for c in package.shapes.objects(None, SH['class'])}
            if pointed & lineage:
                return 'only when a Relationship points at it'
    return None


def build_type_page(package, entity_type, verdicts=None):
    """The payload the entity type page renders. Reads only.

    `verdicts` (editor/verdicts.py) carries the validation of the main model and
    every case; PENDING builds the page without them -- the structure at once,
    "evaluating" where a verdict belongs. Without it, validated here.
    """
    from ..expect.runner import constraint_ref, run_tests
    from ..sanity import known_constraints
    from ..validate import validate_package
    from .choices import attribute_terms
    from .tree import build_tree

    entry = _type_entry(package, entity_type)
    family = _family(package, entry.iri)
    root = next((r for r in build_tree(package) if r.target_class == entry.iri), None)
    shape_nodes = root.children if root is not None else []

    cases = _cases(package, verdicts)
    coverage = _coverage(cases)
    kind_of = {a.iri: a.kind for a in attribute_terms(package) if a.kind}

    # What is wrong in the MAIN model, per (shape, attribute), for this type.
    if verdicts is PENDING:
        report = None
    elif verdicts is not None:
        report = verdicts.model
    else:
        report = validate_package(package, strict=False)
    pending = report is None
    from ..rdfio.relative import as_written

    # Keyed by the id as written, as a violation names its entity.
    model_types = {as_written(s): {str(o) for o in package.model.objects(s, RDF.type)}
                   for s in set(package.model.subjects(RDF.type, None))}
    violated = {}
    for violation in ([] if pending else report.violations):
        if model_types.get(str(violation.resource), set()) & family:
            shape = violation.shape_curie or _short(violation.shape)
            violated.setdefault((shape, violation.attribute or ''), []).append(
                str(violation.resource))

    attributes = []
    for shape_node in shape_nodes:
        for child in shape_node.children:
            if child.kind == 'attribute':
                attributes += _attribute_rows(package, child, kind_of, 0,
                                              coverage, violated)

    cases_pending = any(r is None for _, _, r in cases)
    outcomes = {} if cases_pending else {
        o.example: o for o in run_tests(
            [(example, report) for example, _, report in cases],
            known_constraints(package))}
    exercised = []
    for example, graph, case_report in cases:
        typed = sorted({as_written(s) for s, o in graph.subject_objects(RDF.type)
                        if str(o) in family})
        if not typed:
            continue
        outcome = outcomes.get(example.path)
        exercised.append({
            'case': example.path, 'description': example.description,
            'expect': example.expect, 'entities': typed,
            'passed': None if cases_pending else bool(outcome and outcome.passed),
            'file': os.path.join(_examples_root(package), example.path)})

    instances = []
    for subject, types in sorted(model_types.items()):
        if types & family:
            problems = [] if pending else [v for v in report.violations
                                           if str(v.resource) == subject]
            instances.append({'id': subject, 'type': _short(next(iter(types & family))),
                              'violations': None if pending else
                              [f'{constraint_ref(v)}' for v in problems]})

    rules = _rules(package, shape_nodes, coverage)

    # Every constraint that applies, not only the class-targeted ones: a
    # shape on "whatever has hasValve" judges a pump with a valve, and its
    # attributes and rules belong on the pump's page -- marked with the shape
    # and the condition, and edited on that shape's page.
    from .tree import shape_node

    also = _also_checked_by(package, family, cases)
    for via in also:
        node = shape_node(package, via['shape'])
        if node is None:
            continue
        for child in node.children:
            if child.kind != 'attribute':
                continue
            for row in _attribute_rows(package, child, kind_of, 0, coverage, violated):
                row.update(inherited=True, inheritedFrom='', via=via['shapeName'],
                           condition=via['condition'])
                attributes.append(row)
        for rule in _rules(package, [node], coverage):
            rule.update(inherited=True, inheritedFrom='', via=via['shapeName'],
                        condition=via['condition'])
            rules.append(rule)
    # Several shapes on one attribute: one row, what holds when all apply.
    from .accumulate import accumulate

    attributes = accumulate(attributes, package)
    own_shapes = [n.label for n in shape_nodes if not n.inherited_from]
    from .constrain import own_shape
    own = own_shape(package, entry.iri)
    return {
        'iri': entry.iri, 'term': entry.term, 'label': entry.label,
        'crumbs': [_short(a) for a in _ancestors(package, entry.iri)],
        'subtypes': sorted(_short(c) for c in family - {entry.iri}),
        'ownShapes': own_shapes,
        # The shape ＋ Attribute and Override write into: the type's own
        # structural shape, never an inherited one.
        'ownShape': own or '',
        'ownShapeName': curie(package.shapes, URIRef(own)) if own else '',
        'shapeAt': next((n.defined_at for n in shape_nodes
                         if not n.inherited_from), ''),
        'attributes': attributes, 'rules': rules,
        'alsoCheckedBy': also,
        'exercisedBy': exercised, 'instances': instances,
        'summary': {
            'cases': len(exercised),
            'casesFailing': sum(1 for e in exercised if e['passed'] is False),
            'instances': len(instances),
            'instancesViolating': None if pending else
            sum(1 for i in instances if i['violations']),
            'neverFired': sum(1 for a in attributes if a['tested'] == 'never fired')
            + sum(1 for r in rules if r['tested'] == 'never fired'),
        },
    }


def _examples_root(package):
    from ..expect.store import examples_root

    return examples_root(package.path)
