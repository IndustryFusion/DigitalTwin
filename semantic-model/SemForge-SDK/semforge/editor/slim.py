"""The trees in summary form: one row per meaningful thing, said once.

The full trees print the SHACL encoding a parameter per row, repeat every
value in the row's description, and prefix almost every label with a
namespace the reader already knows -- 192 rows for the kms's constraints,
nine levels in the model. The entity type page is now where a type is READ
and edited; the trees' job is to FIND things. So this pass, applied to the
payloads the server already builds, keeps the structure and drops the noise:

  Constraints  parameter and value-layer rows fold into the attribute row's
               description, in the type page's vocabulary
               ("required · one · → FilterCartridge"); a type row says how
               many attributes and rules it has.
  Model        the read-only `type` row folds into the entity row; a value
               is said once, without the attribute's kind after it.
  Knowledge    "ShapeA + ShapeB + ShapeC" becomes "3 shapes"; an entity id
               that appears in several files is one row, its files beneath.
  Everywhere   a prefix is dropped where the local name is unambiguous in
               that tree (the two CartridgeShapes keep theirs).

It works on the serialised dicts, so the builders and everything that tests
them are untouched, and `full` mode is exactly what it always was.
"""

import copy
import re

from ..cooked.typepage import presence, value_text

CURIE = re.compile(r'(?<![\w/#:.-])([A-Za-z][\w.-]*):([A-Za-z_][\w.-]*)')
KIND_WORDS = {'Property', 'Relationship', 'GeoProperty', 'JsonProperty',
              'ListProperty', 'LanguageProperty', 'VocabProperty'}


# --- prefixes -------------------------------------------------------------------

def _locals(nodes, found=None):
    """{local name: {prefix}} over every label and description in a tree."""
    found = {} if found is None else found
    for node in nodes:
        for text in (node.get('label', ''), node.get('detail', ''),
                     node.get('value', '')):
            for prefix, name in CURIE.findall(str(text or '')):
                if prefix not in ('urn', 'http', 'https'):
                    found.setdefault(name, set()).add(prefix)
        _locals(node.get('children', []), found)
    return found


def _shorten(text, unique):
    def replace(match):
        prefix, name = match.group(1), match.group(2)
        if prefix in ('urn', 'http', 'https') or name not in unique:
            return match.group(0)
        return name
    return CURIE.sub(replace, str(text))


def drop_prefixes(nodes):
    """Labels and descriptions without the prefix wherever the local name is
    unambiguous in this tree. The full term stays in `term` for tooltips."""
    names = _locals(nodes)
    unique = {name for name, prefixes in names.items() if len(prefixes) == 1}

    def walk(node):
        for key in ('label', 'detail'):
            if not node.get(key):
                continue
            shortened = _shorten(node[key], unique)
            if shortened == node[key]:
                continue
            if key == 'label':
                node.setdefault('term', node[key])
            node[key] = shortened
        for child in node.get('children', []):
            walk(child)
    for node in nodes:
        walk(node)
    return nodes


# --- constraints -------------------------------------------------------------------

def _summary(node):
    """'required · one · → FilterCartridge' from an attribute node's children."""
    own = {c['parameter']: c['value'] for c in node.get('children', [])
           if c.get('kind') == 'constraint' and c.get('parameter')}
    slot = next((c for c in node.get('children', []) if c.get('kind') == 'slot'), None)
    value = {}
    raw = []
    if slot is not None:
        for child in slot.get('children', []):
            if child.get('kind') == 'constraint' and child.get('parameter'):
                value[child['parameter']] = child['value']
            elif child.get('kind') == 'raw':
                raw.append((child['label'].replace(' (raw only)', ''),
                            child.get('value', '')))
    kind = 'Relationship' if slot is not None and \
        str(slot.get('detail', '')).endswith('hasObject') else 'Property'
    said = presence(own.get('sh:minCount'), own.get('sh:maxCount'))
    if slot is not None:
        said += ' · ' + value_text(kind, value, raw)
    return said


def _inverse_of(node):
    """The attribute an inverse path walks back over, or ''."""
    text = ' '.join(str(node.get(key, '')) for key in ('label', 'detail'))
    if 'inversePath' not in text and '] )' not in text:
        return ''
    names = [name.split(':')[-1] for name in
             re.findall(r'sh:inversePath\s+([\w.:-]+)', text)
             if not name.startswith('ngsild:')]
    if not names:
        names = [w.split(':')[-1] for w in re.findall(r'[\w.-]+:[\w.-]+', text)
                 if not w.startswith(('ngsild:', 'sh:'))]
    return names[-1] if names else ''


def _count(node, kind):
    return sum((1 if child.get('kind') == kind else 0) + _count(child, kind)
               for child in node.get('children', []))


def slim_constraints(roots, payload=None):
    roots = copy.deepcopy(roots)

    def walk(node):
        if node.get('kind') == 'attribute':
            summary = _summary(node)
            origin = node.get('inheritedClass', '')
            inverse = _inverse_of(node)
            if inverse:
                # A path walked backwards -- the kms's "one cartridge per
                # filter" rule. Its label in the full tree is the raw path.
                node['term'] = node.get('label')
                node['label'] = f'inverse of {inverse}'
            node['detail'] = summary + (f' · from {origin.rsplit("/", 1)[-1]}'
                                        if node.get('inheritedFrom') and origin else '')
            node['children'] = [c for c in node.get('children', [])
                                if c.get('kind') == 'attribute']
        else:
            node['children'] = [c for c in node.get('children', [])
                                if c.get('kind') not in ('constraint', 'slot')]
            if node.get('kind') == 'shape' and node['children'] and all(
                    c.get('kind') == 'raw' for c in node['children']):
                # A shape that is only a query: one row saying so, rather than
                # "0 attribute(s)" over a row explaining it is not a form.
                node['detail'] = ' · '.join(
                    c['label'] for c in node['children']) + \
                    (f' · {node["detail"].split(" — ")[0]}'
                     if node.get('inheritedFrom') else '')
                node['children'] = []
                node['rule'] = True
        for child in node['children']:
            walk(child)

    for root in roots:
        # Counted before the fold: rule rows become their shape's description.
        rules = sum(1 for shape in root.get('children', [])
                    for child in shape.get('children', [])
                    if child.get('kind') == 'raw')
        walk(root)
        attributes = _count(root, 'attribute')
        root['detail'] = ' · '.join(part for part in (
            f'{attributes} attribute(s)' if attributes else '',
            f'{rules} rule(s)' if rules else '') if part) or 'nothing constrained'
    if payload and payload.get('types'):
        roots = types_tree(roots, payload['types'])
    return drop_prefixes(roots)


def types_tree(by_type, types):
    """The Types view: the entity type hierarchy, each type with its OWN
    attributes and one Rules row, its subtypes beneath it.

    Shapes are not a level here -- they have their own view, where a shape
    that targets no class is found too. Inherited attributes are not repeated
    under every subtype; the type page shows them, marked."""
    shaped = {root.get('targetClass'): root for root in by_type}
    children_of = {}
    for entry in types:
        children_of.setdefault(entry.get('parent', ''), []).append(entry)

    def own_rows(root):
        attributes, rules = [], []
        seen = {}
        for shape in (root or {}).get('children', []):
            if shape.get('inheritedFrom'):
                continue
            for child in shape.get('children', []):
                if child.get('kind') != 'attribute':
                    continue
                # Two own shapes on one attribute: one row (the type page
                # shows what holds when both apply, and each shape's part).
                key = tuple(child.get('path') or [child.get('label')])
                if key in seen:
                    first = seen[key]
                    first['shapeCount'] = first.get('shapeCount', 1) + 1
                    # Not the first shape's presence: alone it may say
                    # "optional" where together they say "required".
                    first['detail'] = (f'{first["shapeCount"]} shapes, all apply — '
                                       f'open for what holds')
                    continue
                seen[key] = child
                attributes.append(child)
            raw = [c for c in shape.get('children', []) if c.get('kind') == 'raw']
            if shape.get('rule') or raw:
                rules.append({
                    'kind': 'rule', 'label': shape['label'], 'shape': shape.get('shape'),
                    'detail': shape.get('detail', '') if shape.get('rule')
                    else ' · '.join(c['label'] for c in raw),
                    'definedAt': shape.get('definedAt', ''), 'children': []})
        return attributes, rules

    def node_for(entry, seen):
        root = shaped.get(entry['iri'])
        attributes, rules = own_rows(root)
        children = list(attributes)
        if rules:
            children.append({'kind': 'rules', 'label': 'Rules',
                             'detail': f'{len(rules)}', 'children': rules})
        for sub in sorted(children_of.get(entry['iri'], []), key=lambda e: e['label']):
            if sub['iri'] not in seen:
                children.append(node_for(sub, seen | {sub['iri']}))
        detail = ' · '.join(part for part in (
            f'{_count({"children": attributes}, "attribute")} attribute(s)'
            if attributes else '',
            f'{len(rules)} rule(s)' if rules else '') if part)
        return {'kind': 'type', 'label': entry['label'], 'targetClass': entry['iri'],
                'detail': detail, 'definedAt': (root or {}).get('definedAt', ''),
                'children': children}

    known = {entry['iri'] for entry in types}
    out = [node_for(entry, {entry['iri']})
           for entry in sorted(children_of.get('', []), key=lambda e: e['label'])]
    # A class some shape targets that the knowledge does not make an entity
    # type: shown at the top level rather than dropped.
    for root in by_type:
        if root.get('targetClass') not in known:
            out.append(node_for({'iri': root.get('targetClass'),
                                 'label': root.get('label', '')}, set()))
    return out


# --- the model ------------------------------------------------------------------------

def _value_once(detail):
    """'base:state_ON · Property · 1 violation(s)' -> 'base:state_ON · 1 violation(s)'.

    A plain string value loses its JSON quotes: `"urn:cartridge:1"` reads as
    urn:cartridge:1 in a tree, and the quotes said nothing a reader needs."""
    parts = [part for part in str(detail or '').split(' · ')
             if part.strip() not in KIND_WORDS]
    if parts and re.fullmatch(r'"[^"\\]*"', parts[0].strip()):
        parts[0] = parts[0].strip()[1:-1]
    return ' · '.join(parts)


def slim_model(roots, payload=None):
    roots = copy.deepcopy(roots)

    def walk(node):
        node['children'] = [c for c in node.get('children', [])
                            if c.get('kind') != 'type']
        if node.get('kind') in ('attribute', 'instance', 'dataset'):
            node['detail'] = _value_once(node.get('detail'))
        for child in node['children']:
            walk(child)

    for root in roots:
        walk(root)
    return drop_prefixes(tests_view(roots))


def tests_view(roots):
    """The Instances view: two groups, Main (the model's own data) first and
    Tests (the cases) after it -- both are instance data, judged differently.

    Main says in one line how many entities it holds and whether any is
    violated. A suite reads by its shape ("FilterShape", not
    "test_FilterShape"); the directory stays in the tooltip."""
    out, data = [], None
    for root in roots:
        if root.get('kind') == 'group' and root.get('label') == 'Tests':
            for suite in root.get('children', []):
                if suite.get('kind') == 'suite' and \
                        str(suite.get('label', '')).startswith('test_'):
                    suite['term'] = suite['label']
                    suite['label'] = suite['label'][len('test_'):]
            out.append(root)
        elif root.get('kind') == 'group' and root.get('label') == 'Main':
            data = root
        else:
            out.append(root)
    if data is not None:
        entities = [n for n in _nodes(data) if n.get('kind') == 'entity']
        violations = 0
        for entity in entities:
            found = re.search(r'(\d+) violation', str(entity.get('detail', '')))
            violations += int(found.group(1)) if found else 0
        data['detail'] = f'{len(entities)} entities · ' + (
            f'{violations} violation(s)' if violations else 'all valid')
        data['severity'] = 'warning' if violations else ''
        out.insert(0, data)
    return out


def _nodes(node):
    yield node
    for child in node.get('children', []):
        yield from _nodes(child)


# --- the knowledge -----------------------------------------------------------------------

def _shape_count(detail):
    """'ShapeA + ShapeB · 3 instance(s)' -> '2 shape(s) · 3 instance(s)'."""
    parts = str(detail or '').split(' · ')
    if parts and parts[0] and ('Shape' in parts[0] or ' + ' in parts[0]):
        count = len(parts[0].split(' + '))
        parts[0] = f'{count} shape(s)' if count > 1 else parts[0]
    return ' · '.join(parts)


def slim_knowledge(roots, payload=None):
    roots = copy.deepcopy(roots)

    def walk(node):
        if node.get('kind') == 'class':
            node['detail'] = _shape_count(node.get('detail'))
            if node.get('role') == 'vocabulary':
                # MachineState's members are the values an attribute takes.
                node['detail'] = re.sub(r'\b(\d+) member\(s\)', r'\1 values',
                                        node['detail'])
        children = node.get('children', [])
        grouped, order = {}, []
        for child in children:
            if child.get('kind') == 'instance':
                if child['label'] not in grouped:
                    grouped[child['label']] = []
                    order.append(('instance', child['label']))
                grouped[child['label']].append(child)
            else:
                order.append(('node', child))
        rebuilt = []
        for what, item in order:
            if what == 'node':
                rebuilt.append(item)
                continue
            places = grouped[item]
            if len(places) == 1:
                rebuilt.append(places[0])
                continue
            # One id, several files: one row, the files beneath it. The row
            # keeps the first file's location so a click still lands somewhere.
            row = dict(places[0])
            row['detail'] = f'in {len(places)} files'
            row['children'] = [dict(place, label=place.get('detail') or place['label'],
                                    detail='') for place in places]
            rebuilt.append(row)
        node['children'] = rebuilt
        for child in node['children']:
            walk(child)

    # The entity type hierarchy is the Types view's; here it would be the
    # same tree a second time, answering differently.
    roots = [root for root in roots if not (
        root.get('kind') == 'group' and root.get('label') == 'Entity types')]
    for root in roots:
        walk(root)
    return drop_prefixes(roots)


def slim_shapes(roots, payload=None):
    """Shape names without their prefix where the local name is unique."""
    return drop_prefixes(copy.deepcopy(roots))


SLIM = {'constraints': slim_constraints, 'model': slim_model, 'shapes': slim_shapes,
        'knowledge': slim_knowledge}
