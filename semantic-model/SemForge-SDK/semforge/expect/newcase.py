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

"""Start a test case that makes one shape fire.

A rule no case makes fire looks exactly like a rule that holds. The shape page
says so ("never fired") and offers New case…; this writes it.

What it writes is a STARTING POINT, not a finished case, and says so. By
default the file is EMPTY: the entities a case needs are pasted in from the
main model (Copy entity / Copy subtree, then Paste), which picks exactly the
scene the author has in mind -- a scene chosen for them had to be cut down
first. The case is declared `expect: invalid` without asserts: it fails as unfinished
until its data breaks the rule and "Assert it" on its case page names the
firing it is about. That failure is the point: the case cannot pass by
accident.

With `scene='copy'` a scene is copied instead, from a case that already
reaches the shape -- its includes written into the one new file -- or, when
none does, from the model's document for an entity the shape reaches, and
declared with an assert that the shape fires on that entity.
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
    found = _model_source(package, node)
    return found[1] if found else None


def _model_source(package, node):
    """(the folder of its file, the model's own document for one entity id), or None."""
    for path in package.files('model'):
        if not path.endswith(('.jsonld', '.json')):
            continue
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        for document in data if isinstance(data, list) else [data]:
            if isinstance(document, dict) and \
                    node in (document.get('id'), document.get('@id')):
                return os.path.dirname(path), document
    return None


def _types_under(package, entity_type):
    from .attributecase import _family

    return _family(package, entity_type)


def _of(graph, nodes, family):
    """The nodes of one of these types; all of them when none is asked for."""
    from rdflib import RDF, URIRef

    if family is None:
        return set(nodes)
    typed = {str(s) for s, o in graph.subject_objects(RDF.type)
             if str(o) in family and isinstance(s, URIRef)}
    return {n for n in nodes if str(n) in typed}


def _fresh_scene(package, shape_name, entity_type):
    """A new entity of the type, when nothing of it reaches the shape yet."""
    from ..cooked.choices import entity_types
    from .attributecase import _fresh

    entry = next((t for t in entity_types(package)[0] if t.iri == entity_type), None)
    if entry is None:
        raise PackageError(f'nothing reaches {shape_name}, in a case or in the '
                           f'model: there is no scene to start a case from')
    return _fresh(package, entry)


def _context_home(package):
    """The folder the context of a new entity is relative to: that of the
    model file `_fresh` takes its "@context" from, else the package's own
    (kms.yaml names it)."""
    from .attributecase import _documents

    for path in package.files('model'):
        if not path.endswith(('.jsonld', '.json')):
            continue
        try:
            found = _documents(path)
        except (OSError, ValueError):
            continue
        # As `_fresh` reads it: the first document naming one, unless null.
        context = next((d['@context'] for d in found
                        if isinstance(d, dict) and '@context' in d), None)
        if context is not None:
            return os.path.dirname(path)
    return package.path


def _silent_first(package, shape, nodes):
    """The nodes, those the query does not fire on in the model first, and of
    those, the ones that break nothing else of the shape first: a property
    constraint of the same shape is reported under it too, and would make
    the case fail although the query holds. A model that cannot be
    validated -- pyshacl may refuse a package's shapes in many ways --
    keeps the plain order; the run of the case still says what fails."""
    from ..validate.orchestrator import validate_graphs

    if len(nodes) < 2:
        return nodes
    try:
        report = validate_graphs(package.model, package.shapes, package.knowledge,
                                 strict=False, only={str(shape)})
    except Exception:                               # noqa: BLE001
        return nodes
    mine = [v for v in report.violations if str(v.shape) == str(shape)]
    fired = {str(v.resource) for v in mine if v.component == COMPONENT}
    broken = {str(v.resource) for v in mine}
    return sorted(nodes, key=lambda n: (n in fired, n in broken, n))


def new_case(package, shape, name, purpose='invalid', entity_type='', scene='empty'):
    """Write examples/test_<Shape>/bad/<name>.jsonld and declare it -- or, for
    the purpose 'valid', good/<name>.jsonld: the query runs on it and is silent.

    `scene`: 'empty' (the default) writes no document and declares the case
    without an assert; 'copy' starts it from a scene, as below.

    `entity_type` (its IRI): the type the test is about, when it is asked for
    on a type's page. A scene then has an entity of it; one the package has
    none of is written fresh, its required attributes given valid values.

    Returns {'file', 'case', 'expectations', 'source', 'resource', 'constraint',
    'expect', 'scene'}, and for a test asked for on a type's page, which is run
    once, also {'passes', 'failures', 'violations'}.
    Refused: a shape with no SPARQL constraint (an attribute's constraints
    are asserted from the case page), a name already taken, another `scene`,
    and -- starting from a scene -- a shape nothing reaches.
    """
    from .addcase import _moved_context
    from .attributecase import _targets
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

    if scene not in ('empty', 'copy'):
        raise PackageError(f'{scene} is no way to start a case: empty or copy')
    if purpose not in ('valid', 'invalid'):
        raise PackageError(f'{purpose} is no test to write: one is valid or invalid')
    good = purpose == 'valid'
    # Asked on a type's page, it is a query's test: about that type, run once.
    family = _types_under(package, entity_type) if entity_type else None
    root = examples_root(package.path)
    local = shape_name.split(':')[-1]
    directory = os.path.join(root, f'test_{local}', 'good' if good else 'bad')
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
    if scene == 'empty':
        document, source = [], 'an empty file'
    examples = [] if scene == 'empty' else sorted(
        load_expectations(package.path).examples, key=lambda e: (e.expect != 'valid', e.path))
    for example in examples:
        if good and example.expect != 'valid':
            continue                   # what it violates would come along
        try:
            graph = compose(package, example)
        except PackageError:
            continue
        nodes = _of(graph, _reach(package, shape, graph), family)
        if not nodes:
            continue
        document = []
        for relative in list(example.include) + [example.path]:
            path = os.path.join(root, relative)
            if not os.path.exists(path):
                path = os.path.join(package.path, relative)
            with open(path, encoding='utf-8') as handle:
                data = json.load(handle)
            document += [(os.path.dirname(path), d) for d in (data if isinstance(data, list) else [data])]
        source, resource = example.path, sorted(nodes)[0]
        break
    fresh = False
    if document is None:
        nodes = sorted(_of(package.model, _reach(package, shape, package.model), family))
        if good and family is not None:
            nodes = _silent_first(package, shape, nodes)
        found = [(n, _model_source(package, n)) for n in nodes]
        found = [(n, d) for n, d in found if d is not None]
        if found:
            resource, first = found[0]
            document, source = [first], 'the model'
            # Asked for one type, what its entity points at comes along: the
            # query may read it there too.
            for pointed in (_targets(first[1]) if family is not None else []):
                other = _model_source(package, pointed)
                if other is not None and other not in document:
                    document.append(other)
        else:
            made, resource, source = _fresh_scene(package, shape_name, entity_type)
            document, fresh = [(_context_home(package), d) for d in made], True
    # A relative "@context" still names the same file from the case's folder.
    document = [_moved_context(d, folder, directory) for folder, d in document]

    # The folders this makes, examples/ itself included, innermost first.
    created, folder = [], directory
    while not os.path.isdir(folder) and os.path.dirname(folder) != folder:
        created.append(folder)
        folder = os.path.dirname(folder)
    expectations = os.path.join(directory, EXPECTATIONS)
    declared_before = None
    if os.path.exists(expectations):
        with open(expectations, encoding='utf-8') as handle:
            declared_before = handle.read()
    partial = f'{target}.partial'
    try:
        os.makedirs(directory, exist_ok=True)
        # Written beside and renamed: a case file is either whole or absent.
        try:
            with open(partial, 'w', encoding='utf-8') as handle:
                json.dump(document, handle, indent=2, ensure_ascii=False)
                handle.write('\n')
            os.replace(partial, target)
        finally:
            if os.path.exists(partial):
                os.remove(partial)
        _declare(expectations, slug, local, source, resource, constraint, purpose, scene)
        case = os.path.relpath(target, root)
        made = {'file': target, 'case': case, 'expectations': expectations,
                'source': source, 'resource': resource, 'constraint': constraint,
                'expect': purpose, 'scene': scene}
        if family is None:
            return made                # New case… of a shape page: not run here
        if fresh or source == 'the model':
            _reached(package, shape, shape_name, case, resource, fresh)
        from .addcase import _outcome

        return dict(made, **_outcome(package, case))
    except BaseException:
        # Nothing half-made stays behind: the case, and its declaration.
        if os.path.exists(target):
            os.remove(target)
        if declared_before is None:
            if os.path.exists(expectations):
                os.remove(expectations)
        else:
            with open(expectations, 'w', encoding='utf-8') as handle:
                handle.write(declared_before)
        for folder in created:
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)
        raise


def _reached(package, shape, shape_name, case, resource, fresh):
    """Refuse an entity the query is not evaluated on in the case: neither an
    assert nor silence on it would prove anything. A new one, or one copied
    from the model without what makes the query reach it there."""
    from ..cooked.shapepage import _reach
    from ..package.loader import reload_keeping_shapes

    reloaded = reload_keeping_shapes(package)
    example = next((e for e in load_expectations(reloaded.path).examples if e.path == case), None)
    if example is None:
        raise PackageError(f'{case} is not declared where it was written')
    if resource in _reach(reloaded, shape, compose(reloaded, example)):
        return
    if not fresh:
        raise PackageError(f'{shape_name} is not evaluated on {resource} without the rest of the '
                           f'model: write a case it runs on by hand')
    raise PackageError(f'{shape_name} is not evaluated on a new entity of this type '
                       f'either: write a case it runs on by hand')


def _declare(expectations, slug, local, source, resource, constraint, purpose, scene):
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    good = purpose == 'valid'
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
    entry = CommentedMap()
    entry['path'] = f'{slug}.jsonld'
    if scene == 'empty':
        entry['description'] = (
            f'{local} runs on what is pasted here and does not fire. Starts empty: paste '
            f'the entities it needs from Main.' if good else
            f'Makes {local} fire. Starts empty: paste the entities it needs from Main, '
            f'then edit them until it fires. Until then this case fails.')
    else:
        entry['description'] = (
            f'{local} runs on {resource} and does not fire. Started from {source}.' if good
            else f'Makes {local} fire. Started from {source}, where it holds: edit the '
            f'data until it fires on {resource}. Until then this case fails.')
    entry['expect'] = purpose
    if not good and resource:
        # Empty, there is no entity to name yet: declared without asserts, it
        # fails as unfinished until "Assert it" on its case page names the
        # firing it is about -- as New test case… declares a bad case.
        item = CommentedMap()
        item['constraint'] = constraint
        item['resource'] = resource
        entry['asserts'] = CommentedSeq([item])
    raw['examples'].append(entry)
    with open(expectations, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)
