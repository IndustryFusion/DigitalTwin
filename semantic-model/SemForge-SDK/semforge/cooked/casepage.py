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


def _render(value):
    """A payload as a reader wants it: the IRI's local name, the number."""
    if isinstance(value, dict):
        if '@id' in value:
            return _short(value['@id'])
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

    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    try:
        document = json.loads(text)
        index = locate(text)
    except ValueError as exc:
        return [{'id': '', 'type': '', 'error': f'not valid JSON: {exc}',
                 'file': path, 'line': 1, 'attributes': [], 'violations': []}]
    entities = document if isinstance(document, list) else [document]
    cards = []
    for position, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        identifier = str(entity.get('id') or entity.get('@id') or '')
        attributes = _attributes(entity, [position], index, violations, identifier)
        cards.append({
            'id': identifier, 'type': _short(entity.get('type') or entity.get('@type') or ''),
            'file': path, 'line': index.get((position,)) or 1,
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


def _tree_entities(package):
    """{(entity id, absolute file): its Tests-tree row} over every case and
    the model -- the rows Add Attribute, Edit Value and the rest act on, so
    the page edits through the same commands the tree does."""
    from ..editor.server import _serialise_example
    from .examples import build_suite

    found = {}

    def walk(node):
        if node.get('kind') == 'entity' and node.get('file'):
            found.setdefault((node['entity'], os.path.abspath(node['file'])), node)
        for child in node.get('children', []):
            walk(child)

    for root in build_suite(package):
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


def attach_editing(package, files):
    """Every card and row of these files, joined to its Tests-tree row."""
    from .examples import dataset_names
    from .units import units

    names = dataset_names(package)
    symbols = {u['code']: u['symbol'] or u['code'] for u in units(package)}
    entities = _tree_entities(package)
    for file in files:
        for card in file['cards']:
            _display(card.get('attributes') or [], names, symbols)
            node = entities.get((card['id'], os.path.abspath(card['file'])))
            if node is None:
                continue
            card['node'] = _bare(node)
            _attach(card['attributes'], node)


def build_model_page(package):
    """The model data -- main.jsonld or the model files -- as cards, each
    entity with what is wrong with it, edited like a case. No claims: the
    model declares nothing and cannot fail; its violations are information."""
    from ..validate import validate_package

    report = validate_package(package, strict=False)
    violations = {}
    for result in report.violations:
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
    attach_editing(package, files)
    return {
        'kind': 'model', 'name': 'Main', 'case': '', 'expect': '', 'group': '',
        'suite': '',
        'description': 'The model as shipped: what the platform runs on. It declares '
                       'nothing and cannot fail; its violations are information.',
        'passed': True, 'failures': [], 'claims': [], 'unasserted': [],
        'residuePinned': False, 'file': files[0]['path'] if files else '',
        'expectations': '', 'files': files,
        'summary': {'entities': sum(len(f['cards']) for f in files),
                    'violations': len(report.violations), 'includes': 0},
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
    return {'text': text, 'shape': _short(result.shape_curie or result.shape),
            'component': component, 'detail': result.message or ''}


def build_case_page(package, case):
    """The payload the test case page renders. Reads only."""
    from ..expect.runner import constraint_ref, evaluate
    from ..expect.store import compose, examples_root, load_expectations
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs

    example = _find_case(package, case)
    report = validate_graphs(compose(package, example), package.shapes,
                             package.knowledge, strict=False)
    known = known_constraints(package)
    outcome = evaluate(example, report, known)

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
                 'holds': hit is not None,
                 'explained': _explain(hit) if hit else None}
        if key[1] not in known:
            # Named a shape that is gone -- most often a rename typed into
            # the .ttl. What fires on the same resource narrows the guess.
            firing = [ref for (resource, ref) in fired if not key[0] or resource == key[0]]
            claim.update(stale=True, suggest=suggestion(key[1], known, firing),
                         entry=entry_path, index=position)
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
    attach_editing(package, files)
    return {
        'case': example.path, 'name': os.path.basename(example.path),
        'description': example.description, 'expect': example.expect,
        'group': example.group, 'suite': example.suite,
        'passed': outcome.passed, 'failures': list(outcome.failures),
        'claims': claims, 'unasserted': unasserted,
        'residuePinned': bool(example.residue),
        'file': os.path.abspath(own), 'expectations': expectations_file,
        'files': files,
        'summary': {'entities': sum(len(f['cards']) for f in files),
                    'violations': len(report.violations),
                    'includes': len(example.include)},
    }
