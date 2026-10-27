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

"""A test for one attribute: valid, or making one of its constraints fire.

Asked from the attribute itself -- a row in the Entity Types & Constraints view, a row on the
type page -- because that is where the question arises: "hasPressure is new,
what proves its constraints work?". The answer is one case per constraint
that can fire, and one where everything holds.

The case is a scene with an entity of the type: copied from a valid case
that has one (its includes written into the file), else from the model, else
written fresh with every required attribute given a valid value. The
attribute is then set to a valid value -- and, for a test that should fire,
broken the way the constraint forbids: left out, a text where a number is
expected, one past a bound, an IRI that is not one of the class's values.
Most constraints can be broken mechanically, so the test is finished when it
is written; where one cannot, the case says what to edit and fails until
then. Either way it is run once, and the result says which it is.
"""

import json
import os
import re

from rdflib import RDF, RDFS, URIRef

from ..errors import PackageError
from ..validate.normalise import local
from .store import EXPECTATIONS, _yaml, compose, examples_root, load_expectations

NUMBERS = {'xsd:double', 'xsd:decimal', 'xsd:float', 'xsd:integer', 'xsd:int',
           'xsd:long', 'xsd:short', 'xsd:nonNegativeInteger', 'xsd:positiveInteger'}
INTEGERS = {'xsd:integer', 'xsd:int', 'xsd:long', 'xsd:short',
            'xsd:nonNegativeInteger', 'xsd:positiveInteger'}
STAMP = '2026-01-01T00:00:00.000Z'


# --- the attribute ---------------------------------------------------------------------

def _row(package, entity_type, path):
    """(type entry, the type page's row for the attribute at `path`)."""
    from ..cooked.choices import attribute_terms
    from ..cooked.tree import build_tree
    from ..cooked.typepage import _attribute_rows, _type_entry, _value_of

    entry = _type_entry(package, entity_type)
    root = next((r for r in build_tree(package) if r.target_class == entry.iri), None)
    wanted = list(path or [])
    for shape in (root.children if root is not None else []):
        for node in shape.children:
            if node.kind == 'attribute' and list(node.path_chain) == wanted:
                kind_of = {a.iri: a.kind for a in attribute_terms(package) if a.kind}
                row = _attribute_rows(package, node, kind_of, 0, {}, {})[0]
                return entry, dict(row, formConditions=_form_conditions(
                    _value_of(package, node)))
    if len(wanted) > 1:
        raise PackageError('a test for a sub-attribute is not offered yet; write it '
                           'by hand, inside its parent attribute')
    raise PackageError(f'{" / ".join(wanted) or "that attribute"} is not an attribute '
                       f'of {entry.label}')


def _form_conditions(value):
    """{parameter: value} the one value must meet, read from its forms: an
    OPC UA Variable says them inside `sh:or ( [hasValue …] [hasValueList …] )`,
    where the row's own parameters do not reach. The one-value form is the one
    a test fills; a choice inside it (double or integer) takes its first."""
    from ..cooked.expression import Leaf, Op

    forms = [f for f in value.forms if not f.is_list] or list(value.forms)
    found = {}
    pending = [forms[0].root] if forms else []
    while pending:
        node = pending.pop(0)
        if isinstance(node, Leaf):
            for key, said in node.conditions:
                found.setdefault(key, said)
        elif isinstance(node, Op) and node.op == 'and':
            pending.extend(node.children)
        elif isinstance(node, Op) and node.op in ('or', 'xone') and node.children:
            pending.append(node.children[0])
    return found


def _params(row):
    attribute = {p['parameter']: p['value'] for p in row['parameters']
                 if p['layer'] == 'attribute'}
    value = {p['parameter']: p['value'] for p in row['parameters']
             if p['layer'] == 'value'}
    return attribute, value


def _value_conditions(row):
    """What a valid value must meet: the row's own value parameters, and
    what its forms say. Only for making a valid value -- a condition inside
    an sh:or never fires as itself (the sh:or does), so the breakers keep to
    `_params`."""
    _, value = _params(row)
    for key, said in (row.get('formConditions') or {}).items():
        value.setdefault(key, said)
    return value


def _number(text):
    try:
        return float(str(text).split('^^')[0].strip('"'))
    except ValueError:
        return None


def _counts(row):
    """(sh:minCount, sh:maxCount or None) of the attribute itself.

    What they count is INSTANCES: an NGSI-LD attribute is identified by
    (entity, name, datasetId), so n instances are n datasetIds -- the
    platform counts distinct live datasetIds, and observations of one
    datasetId are one instance.
    """
    attribute, _ = _params(row)
    low = int(_number(attribute.get('sh:minCount', 0)) or 0)
    high = _number(attribute.get('sh:maxCount')) \
        if attribute.get('sh:maxCount') is not None else None
    return low, (int(high) if high is not None else None)


def _dataset_space(package):
    """The namespace generated datasetIds live in -- urn:<package>:dataset: --
    registered for the package if it is not yet: a datasetId reads
    attribute[prefix:name], so its namespace needs a prefix (myModelDataset)."""
    from ..cooked.examples import dataset_names
    from ..package.prefixes import add_namespace, canonical_map

    name = re.sub(r'[^a-z0-9]+', '-', os.path.basename(os.path.abspath(package.path)).lower())
    space = f'urn:{name}:dataset:'
    if space in dataset_names(package):
        return space
    words = [w for w in name.split('-') if w]
    base = (words[0] + ''.join(w.capitalize() for w in words[1:]) if words else 'package') \
        + 'Dataset'
    taken = canonical_map(package.path)
    prefix, number = base, 2
    while prefix in taken:
        prefix, number = f'{base}{number}', number + 1
    add_namespace(package.path, prefix, space)
    return space


def _dataset_iri(package, number):
    """The datasetId of a generated case's `number`th instance (2, 3, ...);
    the first is the default instance, which carries none."""
    return f'{_dataset_space(package)}{number}'


def _instances(package, attribute, count):
    """`count` instances of `attribute`: the default one (no datasetId), then
    one per datasetId. A single instance stays a plain object, none is None."""
    if count <= 0:
        return None
    base = {k: v for k, v in attribute.items() if k != 'datasetId'}
    out = [dict(base)] + [dict(base, datasetId=_dataset_iri(package, number))
                          for number in range(2, count + 1)]
    return out[0] if count == 1 else out


# What each breakable constraint is, in words, and how to break it.
def _breakers(row):
    """{component: (words, how)} for the constraints this attribute can fire,
    `how` None when it cannot be broken mechanically.

    Counts are broken AT the boundary: one instance fewer than sh:minCount,
    one more than sh:maxCount, each its own datasetId -- two instances say
    nothing about a maximum of 3."""
    attribute, value = _params(row)
    low, high = _counts(row)
    out = {}
    if low >= 2:
        out['MinCountConstraintComponent'] = (
            f'too few: {low - 1} instance(s) where {low} are required, each its own '
            f'datasetId', 'fewer')
    elif low >= 1:
        out['MinCountConstraintComponent'] = ('missing: the attribute is left out', 'omit')
    elif int(_number(value.get('sh:minCount', 0)) or 0) >= 1:
        out[_slot(row) + 'MinCountConstraintComponent'] = (
            'no value: the attribute carries none', 'novalue')
    if high is not None:
        out['MaxCountConstraintComponent'] = (
            f'more than {high}: {high + 1} instances, each its own datasetId', 'more')
    datatype = value.get('sh:datatype')
    if datatype:
        out['DatatypeConstraintComponent'] = (
            f'a number where {datatype} is expected' if datatype == 'xsd:string'
            else f'a text where {datatype} is expected', 'datatype')
    for name, words in (('sh:minInclusive', 'below the minimum {}'),
                        ('sh:maxInclusive', 'above the maximum {}'),
                        ('sh:minExclusive', 'at or below {}'),
                        ('sh:maxExclusive', 'at or above {}')):
        if name in value and _number(value[name]) is not None:
            component = name[3].upper() + name[4:] + 'ConstraintComponent'
            out[component] = (words.format(value[name]), name)
    if value.get('sh:class'):
        out['ClassConstraintComponent'] = (
            f'not a {value["sh:class"].split(":")[-1]}: an IRI that is not one', 'class')
    kind = value.get('sh:nodeKind')
    if kind == 'sh:IRI' and row['kind'] == 'Relationship':
        # A Relationship's `object` is read as an IRI whatever it says.
        out[_slot(row) + 'NodeKindConstraintComponent'] = (
            'not an IRI: a Relationship always points at one, so break it by hand',
            None)
    elif kind in ('sh:IRI', 'sh:Literal'):
        out[_slot(row) + 'NodeKindConstraintComponent'] = (
            'a text where an IRI is expected' if kind == 'sh:IRI'
            else 'an IRI where a literal is expected', 'nodekind')
    elif attribute.get('sh:nodeKind'):
        out['NodeKindConstraintComponent'] = (
            'not an attribute node (edit the data by hand)', None)
    if 'sh:in' in value or any(name == 'sh:in' for name in row.get('verbatim', [])):
        out['InConstraintComponent'] = ('a value not in the list', 'in')
    # The unit: its constraints are named after the attribute's unitCode
    # (hasTemperature.unitCode), so their keys say so -- see _ref.
    if row.get('units'):
        out[UNIT_KEY + 'InConstraintComponent'] = (
            f'a unit not allowed: one where {", ".join(row["units"])} is expected', 'unit')
        if row.get('unitRequired'):
            out[UNIT_KEY + 'MinCountConstraintComponent'] = (
                'no unit: its unitCode left out', 'nounit')
    return out


UNIT_KEY = '.unitCode/'


def _slot(row):
    """The key prefix of a constraint on the attribute's VALUE that its node
    could carry too (MinCount, MaxCount, NodeKind): such a constraint is named
    hasX.hasValue -- hasX.hasObject for a Relationship -- so an attribute's
    sh:minCount and its value's are two references (validate.normalise.LAYERED)."""
    return '.hasObject/' if row.get('kind') == 'Relationship' else '.hasValue/'


def _ref(row, key):
    """The constraint a breaker makes fire: Shape/attribute/Component, or --
    for a key starting with "." -- Shape/attribute.unitCode/Component (its unit)
    or Shape/attribute.hasValue/Component (its value)."""
    if key.startswith('.'):
        return f'{row["shapeName"]}/{row["label"]}{key}'
    return f'{row["shapeName"]}/{row["label"]}/{key}'


def _wrong_unit(package, allowed):
    """A unit outside `allowed`, of the same quantity when there is one --
    FAH where CEL is expected -- so the case breaks the unit and nothing else."""
    from ..cooked.units import units

    known = units(package)
    quantity = {u['quantity'] for u in known if u['code'] in allowed}
    same = [u['code'] for u in known if u['quantity'] in quantity and u['code'] not in allowed]
    other = [u['code'] for u in known if u['code'] not in allowed]
    return (same or other or ['XXX'])[0]


SUFFIX = {'omit': 'missing', 'novalue': 'no-value', 'more': 'too-many', 'fewer': 'too-few',
          'unit': 'wrong-unit', 'nounit': 'no-unit',
          'datatype': 'wrong-datatype', 'sh:minInclusive': 'too-low',
          'sh:maxInclusive': 'too-high', 'sh:minExclusive': 'too-low',
          'sh:maxExclusive': 'too-high', 'class': 'wrong-class',
          'nodekind': 'wrong-kind', 'in': 'not-in-list'}


def _suggested(attribute, how, valid=False):
    """hasPressure + too-high -> 'pressure-too-high'."""
    base = re.sub(r'^has(?=[A-Z])', '', attribute)
    base = re.sub(r'(?<!^)(?=[A-Z])', '-', base).lower()
    return f'{base}-{"valid" if valid else SUFFIX.get(how, "fires")}'


def attribute_test_options(package, entity_type, path):
    """What a test for this attribute can prove: valid, or one constraint firing."""
    from ..sanity import known_constraints

    entry, row = _row(package, entity_type, path)
    known = known_constraints(package)
    options = [{'purpose': 'valid', 'label': 'valid',
                'detail': f'{row["label"]} present, with a valid value: the case conforms',
                'automatic': True, 'name': _suggested(row['label'], None, valid=True)}]
    for key, (words, how) in sorted(_breakers(row).items()):
        constraint = _ref(row, key)
        component = key.rsplit('/', 1)[-1]
        if constraint not in known:
            continue
        options.append({'purpose': constraint,
                        'label': 'fires: ' + ('unit ' if key.startswith(UNIT_KEY) else
                                              'value ' if key.startswith('.') else '')
                        + component.replace('ConstraintComponent', ''),
                        'detail': words + ('' if how else ' — you edit the data'),
                        'automatic': bool(how), 'name': _suggested(row['label'], how)})
    return {'type': entry.label, 'attribute': row['label'], 'shape': row['shapeName'],
            'options': options}


# --- values ------------------------------------------------------------------------------

def _vocabulary_value(package, cls_curie):
    """A member of a vocabulary class, as the model writes it."""
    from ..cooked.choices import model_term

    cls = package.shapes.namespace_manager.expand_curie(cls_curie) \
        if ':' in cls_curie and not cls_curie.startswith('http') else URIRef(cls_curie)
    members = sorted((s for s in package.knowledge.subjects(RDF.type, URIRef(cls))
                      if isinstance(s, URIRef)), key=str)
    return model_term(package, members[0]) if members else None


def _valid(package, row, scene):
    """('value'|'object', a value every constraint on it accepts)."""
    value = _value_conditions(row)
    if row['kind'] == 'Relationship':
        target = value.get('sh:class', '')
        name = target.split(':')[-1]
        for document in scene:
            types = document.get('type')
            types = types if isinstance(types, list) else [types]
            if any(str(t).split(':')[-1] == name for t in types if t):
                return 'object', document.get('id')
        return 'object', f'urn:example:{name.lower() or "entity"}:1'
    if value.get('sh:class'):
        member = _vocabulary_value(package, value['sh:class'])
        return 'value', {'@id': member or 'urn:example:value'}
    datatype = value.get('sh:datatype', '')
    if datatype in NUMBERS or any(k in value for k in (
            'sh:minInclusive', 'sh:maxInclusive', 'sh:minExclusive', 'sh:maxExclusive')):
        low = _number(value.get('sh:minInclusive', value.get('sh:minExclusive', '')))
        high = _number(value.get('sh:maxInclusive', value.get('sh:maxExclusive', '')))
        if low is not None and high is not None:
            number = (low + high) / 2
        elif low is not None:
            number = low + 1
        elif high is not None:
            number = high - 1
        else:
            number = 1.0
        if datatype in INTEGERS:
            return 'value', int(number)
        return 'value', float(number)
    if datatype == 'xsd:boolean':
        return 'value', True
    if datatype in ('xsd:dateTime', 'xsd:date'):
        return 'value', {'@type': 'xsd:dateTime', '@value': STAMP}
    return 'value', 'text'


def _break(how, row, attribute, package=None):
    """Change a valid attribute so its constraint fires; None to leave it out.
    The count breakers return the instances, at the boundary."""
    _, value = _params(row)
    key = 'object' if 'object' in attribute else 'value'
    low, high = _counts(row)
    if how == 'omit':
        return None
    if how == 'fewer':
        return _instances(package, attribute, low - 1)
    if how == 'more':
        return _instances(package, attribute, high + 1)
    if how == 'novalue':
        return {k: v for k, v in attribute.items() if k not in ('value', 'object')}
    if how == 'unit':
        return dict(attribute, unitCode=_wrong_unit(package, row['units']))
    if how == 'nounit':
        return {k: v for k, v in attribute.items() if k != 'unitCode'}
    if how == 'datatype':
        broken = 1 if value.get('sh:datatype') == 'xsd:string' else 'not a number'
        return dict(attribute, **{key: broken})
    if how in ('sh:minInclusive', 'sh:minExclusive'):
        return dict(attribute, **{key: _number(value[how]) - (1 if how.endswith('Inclusive') else 0)})
    if how in ('sh:maxInclusive', 'sh:maxExclusive'):
        return dict(attribute, **{key: _number(value[how]) + (1 if how.endswith('Inclusive') else 0)})
    if how == 'class':
        target = 'urn:example:not-a-' + value['sh:class'].split(':')[-1].lower()
        return dict(attribute, **({'object': target} if key == 'object'
                                  else {'value': {'@id': target}}))
    if how == 'nodekind':
        return dict(attribute, **{key: 'text' if value.get('sh:nodeKind') == 'sh:IRI'
                                  else {'@id': 'urn:example:iri'}})
    if how == 'in':
        return dict(attribute, **{key: 'not-in-the-list'})
    raise PackageError(f'no way to break {how}')


# --- the scene ---------------------------------------------------------------------------

def _family(package, iri):
    found, pending = {str(iri)}, [URIRef(iri)]
    while pending:
        for child in package.knowledge.subjects(RDFS.subClassOf, pending.pop()):
            if str(child) not in found:
                found.add(str(child))
                pending.append(child)
    return found


def _documents(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else [data]


def _scene(package, entry):
    """(documents, entity id, where from): a scene with an entity of the type.

    Only a case expected valid is a scene: an invalid one is broken on
    purpose, and a test started from it inherits the breakage -- on the OPC
    UA pumps a valid hasVoltage case came out with power-factor-too-many's
    two power factors."""
    from ..rdfio.relative import as_written
    from .newcase import _model_document

    family = _family(package, entry.iri)
    root = examples_root(package.path)
    examples = sorted((e for e in load_expectations(package.path).examples
                       if e.expect == 'valid'), key=lambda e: e.path)
    for example in examples:
        try:
            graph = compose(package, example)
        except PackageError:
            continue
        typed = sorted({as_written(s) for s, o in graph.subject_objects(RDF.type)
                        if str(o) in family})
        if not typed:
            continue
        documents = []
        for relative in list(example.include) + [example.path]:
            path = os.path.join(root, relative)
            if not os.path.exists(path):
                path = os.path.join(package.path, relative)
            documents += _documents(path)
        ids = [d.get('id') or d.get('@id') for d in documents]
        entity = next((t for t in typed if t in ids), None)
        if entity is not None:
            return documents, entity, example.path
    typed = sorted({as_written(s) for s, o in package.model.subject_objects(RDF.type)
                    if str(o) in family})
    for entity in typed:
        document = _model_document(package, entity)
        if document is None:
            continue
        # The entities it points at come along: a relationship's sh:class is
        # judged on its target, and alone in the case the target has no type.
        # One that points outside the model is no scene.
        scene = [document]
        for target in _targets(document):
            found = _model_document(package, target) if target != entity else document
            if found is None:
                scene = None
                break
            if found not in scene:
                scene.append(found)
        if scene:
            return scene, entity, 'the model'
    return None, None, None


def _targets(node):
    """The ids an entity's relationships point at, sub-attributes included."""
    found = []
    for key, value in (node.items() if isinstance(node, dict) else []):
        if key in ('@context', 'id', '@id', 'type', '@type'):
            continue
        for item in value if isinstance(value, list) else [value]:
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'Relationship' and isinstance(item.get('object'), str):
                found.append(item['object'])
            found += _targets(item)
    return list(dict.fromkeys(found))


def _fresh(package, entry):
    """One new entity of the type, every required attribute given a valid value."""
    from ..cooked.choices import model_term
    from ..cooked.tree import build_tree
    from ..package.context import context_config

    # The @context the package's own documents use, so the new one resolves
    # the same way; else the published one semforge.yaml names.
    context = None
    for path in package.files('model'):
        if path.endswith(('.jsonld', '.json')):
            try:
                found = _documents(path)
            except (OSError, ValueError):
                continue
            context = next((d['@context'] for d in found
                            if isinstance(d, dict) and '@context' in d), None)
            if context is not None:
                break
    if context is None:
        context = context_config(package.path).published or None
    if not context:
        raise PackageError('nothing to start from: no case or model entity of this '
                           'type, and no context in semforge.yaml to write a new one')
    name = re.sub(r'[^a-z0-9]+', '-', os.path.basename(os.path.abspath(package.path)).lower())
    document = {'id': f'urn:{name}:{local(entry.iri).lower()}:test',
                'type': model_term(package, URIRef(entry.iri))}
    root = next((r for r in build_tree(package) if r.target_class == entry.iri), None)
    for shape in (root.children if root is not None else []):
        for node in shape.children:
            if node.kind != 'attribute' or len(node.path_chain) != 1:
                continue
            _, row = _row(package, entry.iri, node.path_chain)
            attribute, _ = _params(row)
            low, _ = _counts(row)
            if low >= 1:
                field, value = _valid(package, row, [document])
                document[model_term(package, URIRef(row['attribute']))] = _instances(
                    package, {'type': row['kind'] or 'Property', field: value}, low)
    document['@context'] = context
    return [document], document['id'], 'a new entity'


# --- the case ----------------------------------------------------------------------------

def new_attribute_test(package, entity_type, path, purpose, name):
    """Write a test for one attribute and declare it. `purpose` is 'valid'
    or a constraint reference from `attribute_test_options`.

    Returns {'file', 'case', 'expect', 'constraint', 'resource', 'source',
    'automatic', 'passes', 'failures'}."""
    from ..cooked.choices import model_term
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs
    from .newcase import _slug
    from .runner import run_tests

    entry, row = _row(package, entity_type, path)
    breakers = _breakers(row)
    if purpose == 'valid':
        component, how, words = None, None, 'present and valid'
    else:
        component = str(purpose).rsplit('/', 1)[-1]
        key = next((k for k in breakers if _ref(row, k) == purpose), None)
        if key is None:
            raise PackageError(f'{purpose} is not a constraint of {row["label"]} '
                               f'that a test can make fire')
        words, how = breakers[key]

    documents, entity, source = _scene(package, entry)
    if documents is None:
        documents, entity, source = _fresh(package, entry)

    term = model_term(package, URIRef(row['attribute']))
    target = next(d for d in documents if (d.get('id') or d.get('@id')) == entity)
    existing = None
    for key in list(target):
        if key in (term, row['attribute'], row['term']):
            existing = target.pop(key)
            term = key                     # keep the key the scene spells it with
    if isinstance(existing, list):
        existing = existing[0] if existing else None
    if isinstance(existing, dict) and ('value' in existing or 'object' in existing):
        # The scene's own attribute is valid there, sub-attributes and all;
        # a test changes only what its constraint needs.
        attribute = dict(existing)
    else:
        field, value = _valid(package, row, documents)
        attribute = {'type': row['kind'] or 'Property', field: value}
        if any(isinstance(v, dict) and 'observedAt' in v for v in target.values()):
            attribute['observedAt'] = STAMP
    if row.get('units') and attribute.get('unitCode') not in row['units']:
        # A valid instance says one of the units its shape allows.
        attribute['unitCode'] = row['units'][0]
    # As many instances as the attribute requires, each its own datasetId; a
    # broken value is broken in the first, the others stay valid.
    required = max(_counts(row)[0], 1)
    if how in ('omit', 'fewer', 'more'):
        attribute = _break(how, row, attribute, package)
    elif how:
        broken = _break(how, row, attribute, package)
        rest = _instances(package, attribute, required) if required > 1 else None
        attribute = [broken] + rest[1:] if rest else broken
    else:
        attribute = _instances(package, attribute, required)
    if attribute is not None:
        position = list(target).index('@context') if '@context' in target else len(target)
        items = list(target.items())
        items.insert(position, (term, attribute))
        target.clear()
        target.update(items)

    good = purpose == 'valid'
    root = examples_root(package.path)
    local_shape = row['shapeName'].split(':')[-1]
    directory = os.path.join(root, f'test_{local_shape}', 'good' if good else 'bad')
    slug = _slug(name)
    path_out = os.path.join(directory, f'{slug}.jsonld')
    if os.path.exists(path_out):
        raise PackageError(f'{os.path.relpath(path_out, root)} already exists')
    os.makedirs(directory, exist_ok=True)
    with open(path_out, 'w', encoding='utf-8') as handle:
        json.dump(documents, handle, indent=2, ensure_ascii=False)
        handle.write('\n')

    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    expectations = os.path.join(directory, EXPECTATIONS)
    if os.path.exists(expectations):
        with open(expectations, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or CommentedMap()
    else:
        raw = CommentedMap()
        raw.yaml_set_start_comment(
            'Cases in this directory are expected to CONFORM.' if good else
            'Cases in this directory are expected to VIOLATE, and to say which '
            'constraint.')
    if not raw.get('examples'):
        raw['examples'] = CommentedSeq()
    entry_yaml = CommentedMap()
    entry_yaml['path'] = f'{slug}.jsonld'
    started = f'Started from {source}.' if source != 'a new entity' else \
        'A new entity, its required attributes given valid values.'
    entry_yaml['description'] = (
        f'{entry.label} with {row["label"]} {words}. {started}' if good else
        f'{row["label"]} {words}. {started}' +
        ('' if how else f' Edit the data until {component} fires on {entity}.'))
    entry_yaml['expect'] = 'valid' if good else 'invalid'
    constraint = None
    if not good:
        constraint = purpose
        item = CommentedMap()
        item['constraint'] = constraint
        item['resource'] = entity
        entry_yaml['asserts'] = CommentedSeq([item])
    raw['examples'].append(entry_yaml)
    with open(expectations, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)

    # Run it once, so the answer says whether it already proves what it says.
    from ..package.loader import reload_keeping_shapes

    fresh = reload_keeping_shapes(package)
    case = os.path.relpath(path_out, root)
    example = next(e for e in load_expectations(fresh.path).examples if e.path == case)
    report = validate_graphs(compose(fresh, example), fresh.shapes, fresh.knowledge,
                             strict=False)
    outcome = run_tests([(example, report)], known_constraints(fresh))[0]
    return {'file': path_out, 'case': case, 'expect': entry_yaml['expect'],
            'constraint': constraint, 'resource': entity, 'source': source,
            'automatic': good or bool(how), 'passes': outcome.passed,
            'failures': list(outcome.failures)}
