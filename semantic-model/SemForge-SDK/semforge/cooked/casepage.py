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

"""The test case page: what a case claims, whether it holds, what it uses.

In the Model tree a case is up to nine levels deep -- the case, its includes,
their entities, attributes, instances, sub-attributes, values -- and whether
it passes is a word in a description. A case answers three questions, so the
page answers them in that order:

  claims    the expectation (valid / invalid) and each assert, each marked
            holds or does not; then whatever fired that the case does not
            assert, because an unasserted violation is either a second bug
            the case found or a sign the data is not what it means to be
  outcome   pass or fail, with the runner's own failure messages
  data      one card per entity, in the case's own file and in each include
            (with the cases that share it), every violation attached to the
            attribute it is about

It runs the case exactly as `semforge test` does -- compose, validate,
evaluate against the declared constraints -- so the page and the CLI cannot
disagree about whether it passes.
"""

import json
import os
import re

from ..errors import PackageError

PREFIXED = re.compile(r'^[A-Za-z][\w.-]*:[A-Za-z_][\w.-]*$')

# What a component means, said about the attribute it judged. The SHACL
# engine's own message names blank nodes and paths ("Less than 1 values on
# [ <...hasValue> ... ]->...hasXXXWorkpiece"); it stays as the tooltip.
EXPLAIN = {
    'MinCount': '{a} is required but missing',
    'MaxCount': '{a} appears more often than allowed',
    'Class': '{a} has a value of the wrong type',
    'Datatype': '{a} has the wrong kind of value',
    'NodeKind': '{a} has the wrong kind of value',
    'MinInclusive': '{a} is below its minimum',
    'MaxInclusive': '{a} is above its maximum',
    'MinExclusive': '{a} is below its minimum',
    'MaxExclusive': '{a} is above its maximum',
    'In': '{a} is not one of the allowed values',
    'Pattern': '{a} does not match its pattern',
    'Or': '{a} matches none of its allowed forms',
    'Node': '{a}: the referenced entity does not conform to the declaration',
}

RESERVED = {'id', '@id', 'type', '@type', '@context'}
VALUE_KEYS = ('value', 'object', 'json', 'valueList', '@value', '@id')
META_KEYS = {'observedAt', 'datasetId', 'unitCode', 'createdAt', 'modifiedAt'}


def _short(term):
    return str(term).rsplit('/', 1)[-1].rsplit('#', 1)[-1].split(':')[-1]


def _find_case(package, case):
    """The declared Example for a case path (relative or absolute)."""
    from ..expect.store import load_expectations

    root = os.path.abspath(package.examples_dir)
    wanted = os.path.abspath(case) if os.path.isabs(case) else \
        os.path.abspath(os.path.join(root, case))
    for example in load_expectations(package.path).examples:
        if os.path.abspath(os.path.join(root, example.path)) == wanted \
                or example.path == case:
            return example
    raise PackageError(f'{case} is not a declared test case. Cases are declared '
                       f'in an expectations.yaml under examples/.')


def page_of_file(package, path):
    """Where the entities of a data file are shown: the case it is, '' for the
    Main page when it is the model's, else the first case that includes it.
    A relative path is the package's."""
    from ..expect.store import examples_root, load_expectations

    root = examples_root(package.path)
    wanted = os.path.realpath(os.path.join(package.path, path))
    examples = load_expectations(package.path).examples

    def case(example):
        return os.path.abspath(os.path.join(root, example.path))

    for example in examples:
        if os.path.realpath(case(example)) == wanted:
            return case(example)
    if wanted in [os.path.realpath(p) for p in package.files('model')]:
        return ''
    for example in examples:
        for included in example.include:
            # Where the case reads it (store.compose): under examples/ first.
            read = os.path.join(root, included)
            if not os.path.exists(read):
                read = os.path.join(package.path, included)
            if os.path.realpath(read) == wanted:
                return case(example)
    raise PackageError(f'{os.path.basename(path)} is neither a file of the main model nor a test '
                       'case or one a case includes, so no page has its graph.')


def _target(payload):
    """The one id a relationship points at, as written; '' for a list."""
    if isinstance(payload, dict) and isinstance(payload.get('@id'), str):
        return payload['@id']
    return payload if isinstance(payload, str) else ''


def _render(value):
    """A payload as a reader wants it: the IRI's local name, the number."""
    if isinstance(value, dict):
        if '@id' in value:
            return _short(value['@id'])
        if '@value' in value:
            # A declared value -- a double, a timestamp (#961) -- reads as its value.
            return _render(value['@value'])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return '[' + ', '.join(_render(v) for v in value) + ']'
    if isinstance(value, str):
        # Only a prefixed name loses its prefix: a timestamp has colons too.
        return _short(value) if PREFIXED.match(value) and \
            not value.startswith('urn:') else value
    return json.dumps(value)


def _attributes(node, address, index, violations, entity):
    """Rows for an entity's (or an attribute's) attributes, sub-attributes
    nested, each with the violations about it."""
    from .examples import value_type

    rows = []
    for key, instances in node.items():
        if key in RESERVED or key in VALUE_KEYS or key in META_KEYS:
            continue
        name = _short(key)
        members = instances if isinstance(instances, list) else [instances]
        latest = _latest(members)
        for position, member in enumerate(members):
            where = address + [key] + ([position] if isinstance(instances, list) else [])
            line = index.get(tuple(address + [key])) or 0
            if not isinstance(member, dict):
                rows.append({'name': name, 'term': key, 'kind': '', 'value': _render(member),
                             'line': line, 'violations': violations.pop((entity, name), []),
                             'children': [], 'dataset': ''})
                continue
            payload = next((member[k] for k in VALUE_KEYS if k in member), None)
            rows.append({
                'name': name, 'term': key, 'kind': str(member.get('type', '')),
                'value': _render(payload) if payload is not None else '',
                'valueType': value_type(member['value']) if 'value' in member else '',
                'target': _target(payload),
                'dataset': str(member.get('datasetId', '')),
                'unitCode': str(member.get('unitCode', '')),
                # When it was observed, where to change that, and whether
                # validation reads it: only the latest of its datasetId counts.
                'observedAt': str(member.get('observedAt', '')),
                'stamp': {'attributePath': address[1:] + [key],
                          'index': position if isinstance(instances, list) else 0},
                'latestAt': latest.get(str(member.get('datasetId', '@none')), ('', 0))[0],
                'superseded': latest.get(str(member.get('datasetId', '@none')),
                                         ('', position))[1] != position,
                # Distinct datasetIds: observations of one are one instance.
                'instances': len({str(m.get('datasetId', '@none')) for m in members
                                  if isinstance(m, dict)}),
                'line': line,
                # Its own, and its unit's (hasLength.unitCode): the unit is its metadata.
                'violations': violations.pop((entity, name), []) +
                violations.pop((entity, name + '.unitCode'), []),
                'children': _attributes(member, where, index, violations, entity)})
    return rows


def _latest(members):
    """{datasetId: (its latest observedAt, the position validation reads)}:
    the latest -- an unstamped one counting as now -- the last of a tie."""
    from ..ngsild.timestamps import key

    out = {}
    for position, member in enumerate(members):
        if not isinstance(member, dict):
            continue
        dataset = str(member.get('datasetId', '@none'))
        best = out.get(dataset)
        if best is None or key(member) >= best[2]:
            out[dataset] = (str(member.get('observedAt', '')), position, key(member))
    return {d: (stamp, position) for d, (stamp, position, _) in out.items()}


def _cards(path, role, shared_by, violations):
    """One card per entity in a file."""
    from .jsonloc import locate
    from .removeentity import digest_of

    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    try:
        document = json.loads(text)
        index = locate(text)
    except ValueError as exc:
        return [{'id': '', 'type': '', 'error': f'not valid JSON: {exc}',
                 'file': path, 'line': 1, 'attributes': [], 'violations': []}]
    entities = document if isinstance(document, list) else [document]
    digest, cards = digest_of(text), []
    for position, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        identifier = str(entity.get('id') or entity.get('@id') or '')
        attributes = _attributes(entity, [position], index, violations, identifier)
        cards.append({
            'id': identifier, 'type': _short(entity.get('type') or entity.get('@type') or ''),
            'file': path, 'line': index.get((position,)) or 1,
            'position': position, 'digest': digest,
            'attributes': attributes,
            # Violations about the entity as a whole, or about an attribute
            # it does not carry -- a missing attribute is exactly that.
            'violations': violations.pop((identifier, None), []),
        })
    return cards


# --- the rows the editing commands act on --------------------------------------------

def _bare(node):
    """A Tests-tree row without its children: what a command needs."""
    return {k: v for k, v in node.items() if k != 'children'}


def _tree_entities(package, verdicts=None):
    """{(entity id, absolute file): its Tests-tree row} over every case and
    the model -- the rows Add Attribute, Edit Value and the rest act on, so
    the page edits through the same commands the tree does."""
    from ..editor.views import _serialise_example
    from .examples import build_suite

    found = {}

    def walk(node):
        if node.get('kind') == 'entity' and node.get('file'):
            found.setdefault((node['entity'], os.path.abspath(node['file'])), node)
        for child in node.get('children', []):
            walk(child)

    for root in build_suite(package, verdicts=verdicts):
        walk(_serialise_example(root))
    return found


def _attach(rows, holder):
    """Give each card row the tree rows it edits through: `node`, whose
    value Edit Value changes, and `attributeNode`, which sub-attributes and
    observations are added to."""
    attributes = [c for c in holder.get('children', []) if c.get('kind') == 'attribute']
    seen = {}
    for row in rows:
        node = next((a for a in attributes
                     if [s for s in a.get('attributePath', []) if isinstance(s, str)][-1:]
                     == [row['term']]), None)
        if node is None:
            continue
        # Several datasetIds: the tree has one row per datasetId, so a card
        # row is joined to ITS datasetId's -- by position it would land on
        # another instance as soon as one datasetId has several observations,
        # and an edit or a removal would hit that one.
        datasets = [c for c in node.get('children', []) if c.get('kind') == 'dataset']
        if datasets:
            wanted = row.get('dataset') or '@none'
            target = next((c for c in datasets if c.get('datasetId') == wanted), node)
        else:
            position = seen.get(row['term'], 0)
            seen[row['term']] = position + 1
            instances = [c for c in node.get('children', []) if c.get('kind') == 'instance']
            target = instances[position] if position < len(instances) else node
        row['node'] = _bare(target)
        row['attributeNode'] = _bare(node)
        if row.get('children'):
            _attach(row['children'], target)


def _display(rows, names, symbols):
    """attribute[prefix:name] for an instance under a datasetId; the name
    itself stays as it is -- violations and the tree are keyed by it. A unit
    reads by its symbol (°C), a code nothing knows as itself."""
    from .examples import instance_label

    for row in rows:
        row['display'] = instance_label(row['name'], row.get('dataset') or '', names)
        if row.get('unitCode'):
            row['unitText'] = symbols.get(row['unitCode']) or row['unitCode']
        _display(row.get('children') or [], names, symbols)


def attach_editing(package, files, verdicts=None):
    """Every card and row of these files, joined to its Tests-tree row."""
    from .examples import dataset_names
    from .units import units

    from .choices import expand

    names = dataset_names(package)
    symbols = {u['code']: u['symbol'] or u['code'] for u in units(package)}
    entities = _tree_entities(package, verdicts)
    for file in files:
        for card in file['cards']:
            # The id as the graph has it: a type or shape page names it so.
            card['iri'] = expand(package.path, card['id']) if card['id'] else ''
            _display(card.get('attributes') or [], names, symbols)
            node = entities.get((card['id'], os.path.abspath(card['file'])))
            if node is None:
                continue
            card['node'] = _bare(node)
            _attach(card['attributes'], node)


def _model_report(package, verdicts):
    """The main model's report: from `verdicts`, None while PENDING, else validated."""
    from ..validate import validate_package
    from .typepage import PENDING

    if verdicts is PENDING:
        return None
    if verdicts is not None:
        return verdicts.model
    return validate_package(package, strict=False)


def _case_report(package, example, verdicts):
    """One case's report: from `verdicts` (None while PENDING, or for a case
    they do not cover yet), else validated here."""
    from ..expect.store import compose
    from ..validate.orchestrator import validate_graphs
    from .typepage import PENDING

    if verdicts is PENDING:
        return None
    if verdicts is not None:
        return verdicts.cases.get(example.path)
    return validate_graphs(compose(package, example), package.shapes,
                           package.knowledge, strict=False)


def _model_files(package, report):
    """The model's files as cards, each violation of `report` on the row it
    is about -- or on its card, when the entity does not carry the attribute
    (a missing one). `report` None: still evaluating, no violations."""
    violations = {}
    for result in ([] if report is None else report.violations):
        violations.setdefault((str(result.resource), result.attribute or None),
                              []).append(_explain(result))
    files = []
    for path in package.files('model'):
        if not path.endswith(('.jsonld', '.json')):
            continue
        files.append({'role': 'model', 'path': os.path.abspath(path),
                      'relative': os.path.relpath(path, package.path), 'sharedBy': [],
                      'cards': _cards(path, 'model', [], violations)})
    # What is about an attribute the entity does not carry: on its card.
    for card in (c for f in files for c in f['cards']):
        for (resource, attribute) in list(violations):
            if resource == card['id']:
                card['violations'].extend(violations.pop((resource, attribute)))
    return files


def located_violations(package, report):
    """Every violation of the model, where it is written: [{file, line,
    entity, attribute, text, shape}] -- the row it is about, or its entity's
    line. What the Main page shows on its rows, for the Problems panel."""
    out = []

    def rows(card, attributes, file):
        for row in attributes:
            for violation in row['violations']:
                out.append({'file': file, 'line': row['line'] or card['line'],
                            'entity': card['id'], 'attribute': row['name'],
                            'text': violation['text'], 'shape': violation['shape']})
            rows(card, row.get('children') or [], file)

    for model in _model_files(package, report):
        for card in model['cards']:
            file = card.get('file') or model['path']
            for violation in card['violations']:
                out.append({'file': file, 'line': card['line'], 'entity': card['id'],
                            'attribute': '', 'text': violation['text'],
                            'shape': violation['shape']})
            rows(card, card['attributes'], file)
    return out


def build_model_page(package, verdicts=None):
    """The model data -- main.jsonld or the model files -- as cards, each
    entity with what is wrong with it, edited like a case. No claims: the
    model declares nothing and cannot fail; its violations are information.
    `verdicts` as for build_type_page."""
    report = _model_report(package, verdicts)
    files = _model_files(package, report)
    attach_editing(package, files, verdicts)
    return {
        'kind': 'model', 'name': 'Main', 'case': '', 'expect': '', 'group': '',
        'suite': '',
        'description': 'The model as shipped: what the platform runs on. It declares '
                       'nothing and cannot fail; its violations are information.',
        'passed': True, 'failures': [], 'claims': [], 'unasserted': [],
        'residuePinned': False, 'file': files[0]['path'] if files else '',
        'expectations': '', 'files': files,
        'summary': {'entities': sum(len(f['cards']) for f in files),
                    'violations': None if report is None else len(report.violations),
                    'includes': 0},
    }


def _explain(result):
    """{'text', 'shape', 'detail'}: what is wrong, by whom, and the engine's
    own words for whoever wants them."""
    component = result.component.replace('ConstraintComponent', '')
    attribute = result.attribute or 'the entity'
    if component == 'SPARQL':
        text = result.message or 'a SPARQL constraint fired'
    else:
        text = EXPLAIN.get(component, '{a}: ' + component).format(a=attribute)
    causes = [_explain_cause(cause) for cause in getattr(result, 'cause', ())]
    if causes:
        # The node constraint's cause, on the referenced entity: the page and the Problems panel show it
        text += ': ' + '; '.join(f"{cause['resource']} {cause['text']}" for cause in causes)
    return {'text': text, 'shape': _short(result.shape_curie or result.shape),
            'component': component, 'detail': result.message or '', 'causes': causes}


def _explain_cause(cause):
    """{'resource', 'attribute', 'component', 'text', 'detail'} for one inner violation."""
    component = cause.component.replace('ConstraintComponent', '')
    attribute = cause.attribute or 'the entity'
    return {'resource': cause.resource, 'attribute': cause.attribute, 'component': component,
            'text': EXPLAIN.get(component, '{a}: ' + component).format(a=attribute),
            'detail': cause.message}


def build_case_page(package, case, verdicts=None):
    """The payload the test case page renders. Reads only. `verdicts` as for
    build_type_page; while this case has none, its claims say so (holds:
    None) rather than failing."""
    from ..expect.runner import constraint_ref, evaluate
    from ..expect.store import examples_root, load_expectations
    from ..sanity import known_constraints
    from ..validate.results import Report

    example = _find_case(package, case)
    report = _case_report(package, example, verdicts)
    pending = report is None
    if pending:
        report = Report()
    known = known_constraints(package)
    outcome = None if pending else evaluate(example, report, known)

    fired = {}
    for result in report.violations:
        fired.setdefault((str(result.resource), constraint_ref(result)), result)

    from ..expect.stale import suggestion

    claims = []
    asserted = set()
    # Where each assert is written: its entry's own `path` and its position.
    entry_path = os.path.relpath(os.path.join(package.examples_dir, example.path),
                                 os.path.dirname(example.source)) if example.source else ''
    for position, item in enumerate(example.asserts):
        key = (str(item.get('resource', '')), str(item.get('constraint', '')))
        asserted.add(key)
        hit = fired.get(key) if key[0] else next(
            (r for (resource, ref), r in fired.items() if ref == key[1]), None)
        claim = {'constraint': key[1], 'resource': key[0],
                 'holds': None if pending else hit is not None,
                 'explained': _explain(hit) if hit else None,
                 # Where it is written: what Remove and Rename act on.
                 'entry': entry_path, 'index': position}
        if hit is None and key[1] not in known:
            # Named a shape that is gone -- most often a rename typed into
            # the .ttl. What fires on the same resource narrows the guess.
            firing = [ref for (resource, ref) in fired if not key[0] or resource == key[0]]
            claim.update(stale=True, suggest=suggestion(key[1], known, firing))
        claims.append(claim)
    unasserted = [{'constraint': ref, 'resource': resource,
                   'explained': _explain(result)}
                  for (resource, ref), result in sorted(fired.items())
                  if (resource, ref) not in asserted
                  and ('', ref) not in asserted]

    # Violations to attach: (entity, attribute local name) -> [violation]. An
    # attribute the entity does not carry (a missing one) is attached to its
    # parent attribute when it is a sub-attribute, else to the entity's card.
    violations = {}
    for result in report.violations:
        violations.setdefault((str(result.resource), result.attribute or None),
                              []).append(_explain(result))

    root = examples_root(package.path)
    own = os.path.join(root, example.path)
    sharing = {}
    for other in load_expectations(package.path).examples:
        for included in other.include:
            sharing.setdefault(included, []).append(other.path)

    files = [{'role': 'case', 'path': os.path.abspath(own), 'relative': example.path,
              'sharedBy': [], 'cards': _cards(own, 'case', [], violations)}]
    for included in example.include:
        path = os.path.join(root, included)
        if not os.path.exists(path):
            path = os.path.join(package.path, included)
        others = [c for c in sharing.get(included, []) if c != example.path]
        files.append({'role': 'include', 'path': os.path.abspath(path),
                      'relative': included, 'sharedBy': others,
                      'cards': _cards(path, 'include', others, violations)})

    # Whatever is left attached to nothing: an attribute the entity does not
    # carry. A missing SUB-attribute goes on the attribute it belongs inside
    # (hasXXXWorkpiece on hasState); anything else on the entity's card,
    # where a reader looks for "what is missing here".
    from .choices import attribute_terms

    parents = {entry.label: [_short(p) for p in entry.parents]
               for entry in attribute_terms(package) if entry.parents}
    for card in (c for f in files for c in f['cards']):
        rows = {row['name']: row for row in card['attributes']}
        for (resource, attribute) in list(violations):
            if resource != card['id']:
                continue
            found = violations.pop((resource, attribute))
            holder = next((rows[p] for p in parents.get(attribute, []) if p in rows), None)
            (holder['violations'] if holder else card['violations']).extend(found)

    expectations_file = example.source
    attach_editing(package, files, verdicts)
    return {
        'case': example.path, 'name': os.path.basename(example.path),
        'description': example.description, 'expect': example.expect,
        'group': example.group, 'suite': example.suite,
        'passed': None if pending else outcome.passed,
        'failures': [] if pending else list(outcome.failures),
        'claims': claims, 'unasserted': unasserted,
        'residuePinned': bool(example.residue),
        'file': os.path.abspath(own), 'expectations': expectations_file,
        'files': files,
        'summary': {'entities': sum(len(f['cards']) for f in files),
                    'violations': None if pending else len(report.violations),
                    'includes': len(example.include)},
    }


def assertable(package, case, verdicts=None):
    """What a case could assert: every constraint that judges one of its
    entities and is not asserted yet, whether it fires or holds now -- read
    from the case's own results, so it is whatever SHACL the shapes use.

    [{'constraint', 'resource', 'fires', 'text'}], what fires first."""
    from ..expect.runner import constraint_ref
    from ..validate.results import Status

    example = _find_case(package, case)
    if verdicts is not None and example.path not in verdicts.cases:
        verdicts = None                # asked for now: the run is not awaited
    report = _case_report(package, example, verdicts)
    asserted = example.asserted_keys()
    out = {}
    for result in report.evaluated:
        resource, ref = str(result.resource), constraint_ref(result)
        if (resource, ref) in asserted or ('', ref) in asserted:
            continue
        fires = result.status is Status.VIOLATED
        if (resource, ref) not in out or fires:
            out[(resource, ref)] = {'constraint': ref, 'resource': resource, 'fires': fires,
                                    'text': _explain(result)['text'] if fires else ''}
    return sorted(out.values(), key=lambda o: (not o['fires'], o['resource'], o['constraint']))


def attribute_cases(package, shape, attribute, verdicts=None):
    """The test cases that have something to say about one attribute: those
    in which one of its constraints fires, is asserted, or holds of a value
    the case really has.

    `shape` is the shape's CURIE, `attribute` the row's label. [{'case',
    'file', 'expect', 'description', 'passed' (None: evaluating), 'fires',
    'asserts' (component names)}]; what fires or is asserted first."""
    from ..expect.runner import constraint_ref, evaluate
    from ..expect.store import examples_root, load_expectations
    from ..sanity import known_constraints
    from ..validate.results import Status

    def about(ref):
        parts = ref.split('/')
        # hasX.hasValue and hasX.unitCode are hasX's own.
        return len(parts) == 3 and parts[0] == shape and \
            (parts[1] == attribute or parts[1].split('.')[0] == attribute)

    def component(ref):
        return ref.rsplit('/', 1)[-1].replace('ConstraintComponent', '')

    root = examples_root(package.path)
    known = known_constraints(package)
    out = []
    for example in load_expectations(package.path).examples:
        asserts = sorted({component(str(a.get('constraint', ''))) for a in example.asserts
                          if about(str(a.get('constraint', '')))})
        report = None if verdicts is None else verdicts.cases.get(example.path)
        fires, present = set(), False
        for result in report.evaluated if report is not None else ():
            if not about(constraint_ref(result)):
                continue
            if result.status is Status.VIOLATED:
                fires.add(component(constraint_ref(result)))
            elif not result.vacuous:
                present = True
        if not (asserts or fires or present):
            continue
        out.append({'case': example.path, 'file': os.path.abspath(os.path.join(root, example.path)),
                    'expect': example.expect, 'description': example.description,
                    'passed': None if report is None else evaluate(example, report, known).passed,
                    'fires': sorted(fires), 'asserts': asserts})
    return sorted(out, key=lambda c: (not (c['asserts'] or c['fires']), c['case']))
