"""Start a test case that makes one shape fire.

A rule no case makes fire looks exactly like a rule that holds. The shape page
says so ("never fired") and offers New case…; this writes it.

What it writes is a STARTING POINT, not a finished case, and says so. A scene
is copied from a case that already reaches the shape -- its includes written
into the one new file -- or, when none does, from the model's document for an entity the
shape reaches. The case is declared `expect: invalid` with an assert that the
shape fires on that entity. Copied from a scene where the shape holds, it does
not fire yet, so `semforge test` fails the new case until its data is edited
to break the rule. That failure is the point: the case cannot pass by accident.
"""

import json
import os
import re

from rdflib.namespace import SH

from ..errors import PackageError
from ..validate.normalise import curie
from .store import EXPECTATIONS, _yaml, compose, examples_root, load_expectations

COMPONENT = 'SPARQLConstraintComponent'


def _slug(name):
    slug = re.sub(r'[^A-Za-z0-9_-]+', '-', str(name or '').strip()).strip('-').lower()
    if not slug:
        raise PackageError('a case needs a name')
    return slug


def _model_document(package, node):
    """The model's own document for one entity id, or None."""
    for path in package.files('model'):
        if not path.endswith(('.jsonld', '.json')):
            continue
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        for document in data if isinstance(data, list) else [data]:
            if isinstance(document, dict) and \
                    node in (document.get('id'), document.get('@id')):
                return document
    return None


def new_case(package, shape, name):
    """Write examples/test_<Shape>/bad/<name>.jsonld and declare it.

    Returns {'file', 'case', 'expectations', 'source', 'resource', 'constraint'}.
    Refused: a shape with no SPARQL constraint (an attribute's constraints
    are asserted from the case page), a name already taken, and a shape
    nothing reaches -- there is no scene to start from.
    """
    from ..cooked.shapepage import _reach, _resolve
    from ..sanity import known_constraints

    shape = _resolve(package, shape)
    shape_name = curie(package.shapes, shape)
    if (shape, SH.sparql, None) not in package.shapes:
        raise PackageError(f'{shape_name} has no SPARQL constraint; assert an '
                           f'attribute constraint from a case page instead')
    constraint = f'{shape_name}/{COMPONENT}'
    if constraint not in known_constraints(package):
        raise PackageError(f'{shape_name} has no target, so it never runs on '
                           f'its own; start the case from the shape that uses it')

    root = examples_root(package.path)
    local = shape_name.split(':')[-1]
    directory = os.path.join(root, f'test_{local}', 'bad')
    slug = _slug(name)
    target = os.path.join(directory, f'{slug}.jsonld')
    if os.path.exists(target):
        raise PackageError(f'{os.path.relpath(target, root)} already exists')

    # A scene that already reaches the shape -- a case expected to be valid
    # first, so the copy does not carry some other shape's violation along.
    # Its includes are written INTO the new file: the entity to edit often
    # lives in a shared subobject, and editing it there would change every
    # case that includes it.
    source, resource, document = '', '', None
    examples = sorted(load_expectations(package.path).examples,
                      key=lambda e: (e.expect != 'valid', e.path))
    for example in examples:
        try:
            nodes = _reach(package, shape, compose(package, example))
        except PackageError:
            continue
        if not nodes:
            continue
        document = []
        for relative in list(example.include) + [example.path]:
            path = os.path.join(root, relative)
            if not os.path.exists(path):
                path = os.path.join(package.path, relative)
            with open(path, encoding='utf-8') as handle:
                data = json.load(handle)
            document += data if isinstance(data, list) else [data]
        source, resource = example.path, sorted(nodes)[0]
        break
    if document is None:
        nodes = sorted(_reach(package, shape, package.model))
        found = [(n, _model_document(package, n)) for n in nodes]
        found = [(n, d) for n, d in found if d is not None]
        if not found:
            raise PackageError(f'nothing reaches {shape_name}, in a case or in the '
                               f'model: there is no scene to start a case from')
        resource, first = found[0]
        document, source = [first], 'the model'

    os.makedirs(directory, exist_ok=True)
    with open(target, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write('\n')

    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    expectations = os.path.join(directory, EXPECTATIONS)
    if os.path.exists(expectations):
        with open(expectations, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or CommentedMap()
    else:
        raw = CommentedMap()
        raw.yaml_set_start_comment(
            'Cases in this directory are expected to VIOLATE, and to say which '
            'constraint.')
    if not raw.get('examples'):
        raw['examples'] = CommentedSeq()
    entry = CommentedMap()
    entry['path'] = f'{slug}.jsonld'
    entry['description'] = (
        f'Makes {local} fire. Started from {source}, where it holds: edit the '
        f'data until it fires on {resource}. Until then this case fails.')
    entry['expect'] = 'invalid'
    item = CommentedMap()
    item['constraint'] = constraint
    item['resource'] = resource
    entry['asserts'] = CommentedSeq([item])
    raw['examples'].append(entry)
    with open(expectations, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)

    return {'file': target, 'case': os.path.relpath(target, root),
            'expectations': expectations, 'source': source,
            'resource': resource, 'constraint': constraint}
