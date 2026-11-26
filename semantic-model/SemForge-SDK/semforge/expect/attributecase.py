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

"""A test for one attribute: one that should conform, or one that should fail.

Asked from the attribute itself -- a row in the Entity Types & Constraints view, a row on the
type page -- because that is where the question arises: "hasPressure is new,
what proves its constraints work?".

A test that should fail ('invalid') does not choose its reason here: it starts
from a valid scene, asserts nothing and so fails, until its data is edited and
the constraint that then fires is asserted ("Assert it" on the case page).
That works the same for every constraint SHACL has -- sh:in, sh:or, SPARQL --
where a list of things that can go wrong never ends.

The case is a scene with an entity of the type: copied from a valid case
that has one (its includes written into the file), else from the model, else
written fresh with every required attribute given a valid value. The
attribute is then set to a valid value, as many instances as it requires. The
case is run once, and the result says whether it passes.
"""

import json
import math
import os
import re

from decimal import Decimal

from rdflib import RDF, RDFS, XSD, URIRef

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

    try:
        entry = _type_entry(package, entity_type)
    except PackageError:
        # Written otherwise than the package lists it: what the name means.
        context, written = _prefixes(package)
        entry = _type_entry(package, _meant(context, entity_type) or
                            _meant(written, entity_type) or entity_type)
    root = next((r for r in build_tree(package) if r.target_class == entry.iri), None)
    wanted = list(path or [])
    nodes = [node for shape in (root.children if root is not None else [])
             for node in shape.children if node.kind == 'attribute']
    node = _same_path(package, nodes, wanted)
    if node is not None:
        kind_of = {a.iri: a.kind for a in attribute_terms(package) if a.kind}
        row = _attribute_rows(package, node, kind_of, 0, {}, {})[0]
        value_of = _value_of(package, node)
        return entry, dict(row, formConditions=_form_conditions(value_of),
                           formDatatypes=_form_datatypes(value_of))
    if len(wanted) > 1:
        raise PackageError('a test for a sub-attribute is not offered yet; write it '
                           'by hand, inside its parent attribute')
    raise PackageError(f'{" / ".join(wanted) or "that attribute"} is not an attribute '
                       f'of {entry.label}')


def _meant(prefixes, term):
    """The IRI a name means where `prefixes` hold, or None."""
    text = str(term or '').strip('<>')
    if '://' in text or text.startswith('urn:'):
        return text
    prefix, colon, name = text.partition(':')
    return prefixes[prefix] + name if colon and prefix in prefixes else None


def _prefixes(package):
    """(what prefixes mean in the data, what they mean in the shapes files)."""
    from ..package.prefixes import canonical_map, file_prefixes

    context = canonical_map(package.path)
    written = dict(context)
    for path in package.files('shapes'):
        written.update(file_prefixes(path)[0])
    return context, written


def _same_path(package, nodes, wanted):
    """The attribute at `wanted`: as written, else the one its names mean. The
    data may say a:hasMode where the shape says b:hasMode, two prefixes of one
    namespace. Each is read where it is written, the data's names in the
    package's context and the shape's in its files: the graph keeps one prefix
    per namespace."""
    found = next((n for n in nodes if list(n.path_chain) == wanted), None)
    if found is not None or not wanted:
        return found
    context, written = _prefixes(package)
    meant = [_meant(context, step) or _meant(written, step) for step in wanted]
    if None in meant:
        return None
    return next((n for n in nodes
                 if [_meant(written, step) for step in n.path_chain] == meant), None)


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


def _form_datatypes(value):
    """Every sh:datatype the one value may have, read from all branches of
    its one-value form. Unlike `_form_conditions`, a choice is not cut to its
    first branch: `sh:or ( double integer )` admits integers, while the
    OPC UA `sh:or ( [hasValue double] [hasValueList …] )` is a choice of form
    whose one-value side is a double alone."""
    from ..cooked.expression import Leaf, Op

    forms = [f for f in value.forms if not f.is_list] or list(value.forms)
    found = set()
    pending = [forms[0].root] if forms else []
    while pending:
        node = pending.pop(0)
        if isinstance(node, Leaf):
            found.update(said for key, said in node.conditions if key == 'sh:datatype')
        elif isinstance(node, Op):
            pending.extend(node.children)
    return sorted(found)


# Datatypes whose values a writer declares (#961, contracts/typed-literals):
# JSON-LD 1.1 makes a plain whole number an xsd:integer, 80.0 included.
DECLARED = {'xsd:double': 'http://www.w3.org/2001/XMLSchema#double',
            'xsd:float': 'http://www.w3.org/2001/XMLSchema#float',
            'xsd:decimal': 'http://www.w3.org/2001/XMLSchema#decimal'}


def declared_type(row):
    """The full XSD IRI every value of the attribute is declared with, or None.

    A number is declared when the one value may be a double, a float or a
    decimal and nothing else: said as the value's own sh:datatype, or by all
    branches of its form. An sh:or that admits integers too is written plain."""
    return DECLARED.get(value_datatype(row))


def value_datatype(row):
    """The one sh:datatype the attribute's value has, or None: none, or a
    choice of several."""
    _, value = _params(row)
    datatypes = [value['sh:datatype']] if value.get('sh:datatype') else row.get('formDatatypes') or []
    return datatypes[0] if len(set(datatypes)) == 1 else None


def declared_value(number, iri):
    """A number declared as `iri`. A decimal as text: as a JSON number it would
    come back as a double's spelling, which is no decimal."""
    if iri == DECLARED['xsd:decimal']:
        return {'@value': format(Decimal(repr(number)), 'f'), '@type': iri}
    return {'@value': float(number), '@type': iri}


def typed(row, number):
    """`number` as the attribute's values are written: declared for a double
    (float, decimal); otherwise plain, a whole value as an integer -- which is
    what JSON-LD makes of it anyway, so `80` rather than `80.0`."""
    iri = declared_type(row)
    if iri is not None:
        return declared_value(number, iri)
    if isinstance(number, float) and number.is_integer():
        return int(number)
    return number


def _params(row):
    attribute = {p['parameter']: p['value'] for p in row['parameters']
                 if p['layer'] == 'attribute'}
    value = {p['parameter']: p['value'] for p in row['parameters']
             if p['layer'] == 'value'}
    return attribute, value


def _value_conditions(row):
    """What a valid value must meet: the row's own value parameters, and
    what its forms say."""
    _, value = _params(row)
    for key, said in (row.get('formConditions') or {}).items():
        value.setdefault(key, said)
    return value


def _number(text):
    try:
        return float(str(text).split('^^')[0].strip('"'))
    except ValueError:
        return None


def _required(row):
    """How many instances of the attribute its sh:minCount asks for.

    What it counts is INSTANCES: an NGSI-LD attribute is identified by
    (entity, name, datasetId), so n instances are n datasetIds -- the
    platform counts distinct live datasetIds, and observations of one
    datasetId are one instance.
    """
    attribute, _ = _params(row)
    return int(_number(attribute.get('sh:minCount', 0)) or 0)


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


def _directory(package, row, purpose):
    """Where a test of the attribute goes: its shape's suite, good/ or bad/."""
    return os.path.join(examples_root(package.path), f'test_{row["shapeName"].split(":")[-1]}',
                        'good' if purpose == 'valid' else 'bad')


def _suggested(package, row, purpose):
    """hasPressure, invalid -> 'pressure-invalid', or -2, -3… while that is taken."""
    from .newcase import _slug

    attribute = row['label']
    base = re.sub(r'^has(?=[A-Z])', '', attribute)
    base = re.sub(r'(?<!^)(?=[A-Z])', '-', base).lower()
    first = name = _slug(f'{base}-{purpose}')
    number = 2
    while os.path.exists(os.path.join(_directory(package, row, purpose), f'{name}.jsonld')):
        name, number = f'{first}-{number}', number + 1
    return name


def attribute_test_options(package, entity_type, path):
    """What a test for this attribute can show: that it conforms, or that it fails."""
    entry, row = _row(package, entity_type, path)
    said = {'valid': f'{row["label"]} present, with a valid value: the case conforms',
            'invalid': 'starts from valid data and fails until you break the data and '
                       'assert what fires'}
    return {'type': entry.label, 'attribute': row['label'], 'shape': row['shapeName'],
            'options': [{'purpose': purpose, 'detail': detail,
                         'name': _suggested(package, row, purpose)}
                        for purpose, detail in said.items()]}


# --- values ------------------------------------------------------------------------------

def _vocabulary_value(package, cls_curie):
    """A member of a vocabulary class, as the model writes it."""
    from ..cooked.choices import model_term

    cls = package.shapes.namespace_manager.expand_curie(cls_curie) \
        if ':' in cls_curie and not cls_curie.startswith('http') else URIRef(cls_curie)
    members = sorted((s for s in package.knowledge.subjects(RDF.type, URIRef(cls))
                      if isinstance(s, URIRef)), key=str)
    return model_term(package, members[0]) if members else None


def _listed(package, row, value):
    """('value'|'object', the first item of the value's sh:in), or None: what a
    list admits is written in it, a value of the right datatype need not be."""
    from ..cooked.listcheck import item_term
    from ..cooked.tree import list_items

    items = (row.get('inList') or {}).get('items') or list_items(value.get('sh:in', ''))
    if not items:
        return None
    term = item_term(package, items[0])
    if row['kind'] == 'Relationship':
        return 'object', str(term)
    return 'value', json_value(package, term)


def json_value(package, term):
    """An RDF term as the JSON-LD value that reads back as exactly that term
    (sh:in compares terms). What JSON itself can say is written plain."""
    from ..cooked.choices import model_term

    if isinstance(term, URIRef):
        return {'@id': model_term(package, term)}
    if term.language:
        return {'@value': str(term), '@language': term.language}
    if term.datatype is None:
        return str(term)
    if term.datatype == XSD.boolean and str(term) in ('true', 'false', '1', '0'):
        return str(term) in ('true', '1')
    # A decimal is no JSON number: it would come back as another term (2.50).
    # Neither is a text that is not what its datatype says ("abc"^^xsd:integer).
    written = str(term)
    try:
        if term.datatype == XSD.integer:
            return int(written)
        if term.datatype in (XSD.double, XSD.float) and math.isfinite(float(written)):
            written = float(written)           # INF and NaN are no JSON
    except ValueError:
        pass
    return {'@value': written, '@type': str(term.datatype)}


def _valid(package, row, scene):
    """('value'|'object', a value every constraint on it accepts)."""
    value = _value_conditions(row)
    listed = _listed(package, row, value)
    if listed:
        return listed
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
        return 'value', typed(row, float(number))
    if datatype == 'xsd:boolean':
        return 'value', True
    if datatype in ('xsd:dateTime', 'xsd:date'):
        return 'value', {'@type': 'xsd:dateTime', '@value': STAMP}
    return 'value', 'text'


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
    # the same way; else the published one kms.yaml names.
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
                           'type, and no context in kms.yaml to write a new one')
    name = re.sub(r'[^a-z0-9]+', '-', os.path.basename(os.path.abspath(package.path)).lower())
    document = {'id': f'urn:{name}:{local(entry.iri).lower()}:test',
                'type': model_term(package, URIRef(entry.iri))}
    root = next((r for r in build_tree(package) if r.target_class == entry.iri), None)
    for shape in (root.children if root is not None else []):
        for node in shape.children:
            if node.kind != 'attribute' or len(node.path_chain) != 1:
                continue
            _, row = _row(package, entry.iri, node.path_chain)
            low = _required(row)
            if low >= 1:
                field, value = _valid(package, row, [document])
                document[model_term(package, URIRef(row['attribute']))] = _instances(
                    package, {'type': row['kind'] or 'Property', field: value}, low)
    document['@context'] = context
    return [document], document['id'], 'a new entity'


# --- the case ----------------------------------------------------------------------------

def new_attribute_test(package, entity_type, path, purpose, name):
    """Write a test for one attribute and declare it. `purpose` is 'valid'
    or 'invalid' (valid data and no reason yet: it fails until one is asserted).

    Returns {'file', 'case', 'expect', 'resource', 'source', 'purpose',
    'passes', 'failures'}."""
    from ..cooked.choices import model_term
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs
    from .newcase import _slug
    from .runner import run_tests

    entry, row = _row(package, entity_type, path)
    if purpose not in ('valid', 'invalid'):
        raise PackageError(f'{purpose} is no test to write: one is valid or invalid')

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
    # As many instances as the attribute requires, each its own datasetId.
    required = max(_required(row), 1)
    attribute = _instances(package, attribute, required)
    position = list(target).index('@context') if '@context' in target else len(target)
    items = list(target.items())
    items.insert(position, (term, attribute))
    target.clear()
    target.update(items)

    good = purpose == 'valid'
    root = examples_root(package.path)
    directory = _directory(package, row, purpose)
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
        f'{entry.label} with {row["label"]} present and valid. {started}' if good else
        f'{entry.label} with {row["label"]} invalid. {started} It fails until its data is '
        'edited to break what it should show, and that is asserted.')
    entry_yaml['expect'] = 'valid' if good else 'invalid'
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
            'resource': entity, 'source': source, 'purpose': purpose,
            'passes': outcome.passed, 'failures': list(outcome.failures)}
