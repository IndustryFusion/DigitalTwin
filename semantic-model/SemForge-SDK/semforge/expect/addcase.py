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

"""New test case…: add a test file to a suite, from wherever it should start.

The other ways to a case are aimed at one thing -- New test… at an attribute,
New case… at a SPARQL rule. This is the general one: a suite (an existing one
or a new one for a shape), good or bad, and a start -- a copy of a case, the
whole main model, an entity from the model, a fresh entity of a type with its
required attributes given valid values, an empty file, or a .jsonld already
under examples/ that no expectations file declares yet (a file nobody runs is worse than none:
the folder suggests coverage the suite does not have).

The case is declared in the expectations.yaml beside it, `expect: valid` or
`invalid`, and run once. A bad case is declared without asserts: what fires
is shown on its case page, and "Assert it" turns each firing into a claim.

The whole main model is written INTO the case, document by document, like a
copied case gets its includes written in. Including the model files instead
would not do: everything is parsed into one graph, so a case could neither
remove an included entity nor override one of its values. The case is a
snapshot; later edits of the model do not reach it, nor its edits the model.
"""

import json
import os
import re

from ..errors import PackageError
from .store import (EXPECTATIONS, _yaml, compose, discover, examples_root,
                    load_expectations)


def _documents(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else [data]


def case_options(package):
    """What New test case… can offer: suites, shapes (for a new suite),
    cases to copy, the main model's files, model entities, entity types,
    undeclared files."""
    from rdflib import RDF, URIRef

    from ..validate.normalise import curie, local
    from ..validate.shapes import every_node_shape
    from ..cooked.choices import entity_types

    expectations = load_expectations(package.path)
    suites = sorted({e.suite for e in expectations.examples if e.suite})
    root = examples_root(package.path)
    declared = {os.path.normpath(e.path) for e in expectations.examples}
    included = {os.path.normpath(i) for e in expectations.examples for i in e.include}
    undeclared = [p for p in discover(package.path)
                  if os.path.normpath(p) not in declared | included
                  and not p.replace('\\', '/').startswith('subobjects/')]
    from ..rdfio.relative import as_written

    entities = sorted({as_written(s) for s in package.model.subjects(RDF.type, None)
                       if isinstance(s, URIRef)})
    return {
        'root': root,
        'suites': suites,
        'shapes': [{'iri': str(s), 'name': curie(package.shapes, s), 'label': local(s)}
                   for s in every_node_shape(package.shapes)],
        'cases': [{'path': e.path, 'expect': e.expect, 'description': e.description}
                  for e in expectations.examples],
        'modelFiles': [os.path.relpath(p, package.path).replace('\\', '/')
                       for p in _model_files(package)],
        'entities': entities,
        'types': [{'iri': t.iri, 'label': t.label, 'term': t.term}
                  for t in entity_types(package)[0]],
        'undeclared': undeclared,
    }


def _model_files(package):
    """The main model's files, in load order."""
    return [p for p in package.files('model') if p.endswith(('.jsonld', '.json'))]


_SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')


def _moved_context(document, source, target):
    """`document`, read from the folder `source`, to be written into the
    folder `target`: a relative "@context" ("context.jsonld", as `semforge
    retarget --to local` writes it) still names the same file. A URL, an
    absolute path and an inline context object are left as they are."""
    def moved(context):
        if isinstance(context, str) and not _SCHEME.match(context) \
                and not os.path.isabs(context):
            return os.path.relpath(os.path.normpath(os.path.join(source, context)),
                                   target).replace('\\', '/')
        if isinstance(context, list):
            return [moved(item) for item in context]
        return context

    if not isinstance(document, dict) or '@context' not in document:
        return document
    return dict(document, **{'@context': moved(document['@context'])})


def _shared_ids(documents):
    """Ids that more than one document defines, in order of first sight."""
    seen, shared = set(), []
    for document in documents:
        identifier = document.get('id', document.get('@id')) \
            if isinstance(document, dict) else None
        if identifier in seen and identifier not in shared:
            shared.append(identifier)
        seen.add(identifier)
    return [i for i in shared if i]


def _scene(package, start, source, directory=''):
    """The documents a new case starts with, for a case file in `directory`."""
    root = examples_root(package.path)
    if start == 'copy':
        example = next((e for e in load_expectations(package.path).examples
                        if e.path == source), None)
        if example is None:
            raise PackageError(f'{source} is not a declared test case')
        documents = []
        # Includes are written into the copy: editing its entities must not
        # change a subobject other cases share.
        for relative in list(example.include) + [example.path]:
            path = os.path.join(root, relative)
            if not os.path.exists(path):
                path = os.path.join(package.path, relative)
            documents += _documents(path)
        return documents
    if start == 'whole-model':
        # Every document of every model file, written in: the case is edited
        # on its own, and the model stays as it is.
        files = _model_files(package)
        if not files:
            raise PackageError('the package has no main model to start a case from')
        documents = []
        for path in files:
            documents += [_moved_context(d, os.path.dirname(path), directory)
                          for d in _documents(path)]
        return documents
    if start == 'model':
        from .newcase import _model_document

        document = _model_document(package, source)
        if document is None:
            raise PackageError(f'{source} is not an entity in the model')
        return [document]
    if start == 'type':
        from ..cooked.choices import entity_types
        from .attributecase import _fresh

        entry = next((t for t in entity_types(package)[0]
                      if source in (t.iri, t.term, t.label)), None)
        if entry is None:
            raise PackageError(f'{source} is not an entity type this package declares')
        documents, _, _ = _fresh(package, entry)
        return documents
    if start == 'empty':
        return []
    raise PackageError(f'{start} is not a way to start a case')


def _declare(directory, file_name, expect, description):
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    expectations = os.path.join(directory, EXPECTATIONS)
    if os.path.exists(expectations):
        with open(expectations, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or CommentedMap()
    else:
        raw = CommentedMap()
        raw.yaml_set_start_comment(
            'Cases in this directory are expected to CONFORM.' if expect == 'valid' else
            'Cases in this directory are expected to VIOLATE, and to say which '
            'constraint.')
    if not raw.get('examples'):
        raw['examples'] = CommentedSeq()
    if any(e.get('path') == file_name for e in raw['examples']):
        raise PackageError(f'{file_name} is already declared in {expectations}')
    entry = CommentedMap()
    entry['path'] = file_name
    if description:
        entry['description'] = description
    entry['expect'] = expect
    raw['examples'].append(entry)
    with open(expectations, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)
    return expectations


def add_test_case(package, suite, expect, start, source='', name='', description=''):
    """Write and declare a test case. `start` is copy | whole-model | model
    | type | empty | existing (then `source` is the undeclared file, declared
    where it is).

    Returns {'file', 'case', 'expect', 'start', 'violations', 'passes', 'failures'},
    and for the whole model 'sharedIds': ids two of its documents define.
    Anything that fails after the file is written removes the file and its
    declaration again.
    """
    from .newcase import _slug

    if expect not in ('valid', 'invalid'):
        raise PackageError('a case either conforms (valid) or violates (invalid)')
    root = examples_root(package.path)
    if start == 'existing':
        path = os.path.normpath(os.path.join(root, source))
        if not path.startswith(os.path.normpath(root) + os.sep) or not os.path.exists(path):
            raise PackageError(f'{source} is not a file under {root}')
        directory, file_name = os.path.split(path)
        written = False
    else:
        suite = str(suite or '').strip().strip('/')
        if not suite or '..' in suite.split('/'):
            raise PackageError('a case needs a suite: a folder under examples/')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*', suite):
            raise PackageError(f'{suite!r} is not a folder name: letters, digits, '
                               '"_", "-" and "." only')
        directory = os.path.join(root, suite, 'good' if expect == 'valid' else 'bad')
        file_name = f'{_slug(name)}.jsonld'
        path = os.path.join(directory, file_name)
        if os.path.exists(path):
            raise PackageError(f'{os.path.relpath(path, root)} already exists')
        documents = _scene(package, start, source, directory)
        os.makedirs(directory, exist_ok=True)
        # Written beside and renamed: a case file is either whole or absent.
        partial = f'{path}.partial'
        try:
            with open(partial, 'w', encoding='utf-8') as handle:
                json.dump(documents, handle, indent=2, ensure_ascii=False)
                handle.write('\n')
            os.replace(partial, path)
        finally:
            if os.path.exists(partial):
                os.remove(partial)
        written = True
    described = bool(description)
    if not description:
        description = {'copy': f'Started from {source}.', 'model': f'{source}, from the model.',
                       'type': 'A new entity, its required attributes given valid values.',
                       'whole-model': WHOLE_MODEL_PLACEHOLDER,
                       'empty': '', 'existing': ''}.get(start, '')
    expectations = os.path.join(directory, EXPECTATIONS)
    declared_before = None
    if os.path.exists(expectations):
        with open(expectations, encoding='utf-8') as handle:
            declared_before = handle.read()
    try:
        _declare(directory, file_name, expect, description)
        return _first_run(package, root, path, directory, file_name, expect, start,
                          described, documents if written else [])
    except BaseException:
        # Nothing half-made stays behind: the file this wrote, and its
        # declaration, go again.
        if written and os.path.exists(path):
            os.remove(path)
        if declared_before is None:
            if os.path.exists(expectations):       # this made it
                os.remove(expectations)
        else:
            with open(expectations, 'w', encoding='utf-8') as handle:
                handle.write(declared_before)
        raise


def _first_run(package, root, path, directory, file_name, expect, start, described,
               documents):
    """Run a case just declared, once, and say how it went."""
    from ..package.loader import reload_keeping_shapes
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs
    from .runner import run_tests

    fresh = reload_keeping_shapes(package)
    case = os.path.relpath(path, root)
    example = next(e for e in load_expectations(fresh.path).examples if e.path == case)
    made = {'file': path, 'case': case, 'expect': expect, 'start': start}
    if start == 'whole-model':
        # Two model files may define one id; the model graph merges them, and
        # so does the case's -- but in one file it reads as a mistake.
        made['sharedIds'] = _shared_ids(documents)
    try:
        report = validate_graphs(compose(fresh, example), fresh.shapes, fresh.knowledge,
                                 strict=False)
    except Exception as exc:                       # noqa: BLE001
        return dict(made, violations=0, passes=False, failures=[f'does not load: {exc}'])
    outcome = run_tests([(example, report)], known_constraints(fresh))[0]
    if start == 'whole-model' and not described:
        # What the case still lacks depends on whether the model conforms,
        # which only the run says.
        _describe(directory, file_name,
                  WHOLE_MODEL[(expect, 'violates' if report.violations else 'conforms')])
    return dict(made, violations=len(report.violations), passes=outcome.passed,
                failures=list(outcome.failures))


# Declared before the one run, which decides the description.
WHOLE_MODEL_PLACEHOLDER = 'Started from the whole main model.'
WHOLE_MODEL = {
    ('valid', 'conforms'): 'Started from the whole main model, which conforms: a snapshot, '
                           'so editing this case never changes the model.',
    ('valid', 'violates'): 'Started from the whole main model, which violates. It fails '
                           'until its data is edited so it conforms.',
    ('invalid', 'conforms'): 'Started from the whole main model, which conforms. It fails '
                             'until its data is edited to break what it should show, and '
                             'that is asserted.',
    ('invalid', 'violates'): 'Started from the whole main model, which violates already: '
                             'assert what fires on its case page.',
}


def _describe(directory, file_name, description):
    """Set the description of a case declared in `directory`."""
    expectations = os.path.join(directory, EXPECTATIONS)
    with open(expectations, encoding='utf-8') as handle:
        raw = _yaml().load(handle)
    entry = next(e for e in raw['examples'] if e.get('path') == file_name)
    entry['description'] = description
    with open(expectations, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)


OPPOSITE = {'valid': 'invalid', 'invalid': 'valid'}


def clone_case(package, case, expect='opposite', name=''):
    """A copy of a declared case, in the same suite, expecting `expect`:
    'opposite' (a valid case's invalid twin, or the other way round), 'same',
    or 'valid' / 'invalid' outright.

    The data is copied as "A copy of a case" copies it -- includes written in,
    so nothing shared is touched. An opposite clone starts from data that does
    the opposite of what it now claims: it fails until its data is edited, and
    says so in its description. Its asserts are not copied (a valid case has
    none; an invalid one's would be wrong for a valid twin). A same clone
    keeps the asserts and the description and passes as the original does.
    """
    root = examples_root(package.path)
    case = str(case or '')
    if os.path.isabs(case):                        # a tree row knows its file
        case = os.path.relpath(case, root)
    case = case.replace('\\', '/')
    example = next((e for e in load_expectations(package.path).examples if e.path == case), None)
    if example is None:
        raise PackageError(f'{case} is not a declared test case')
    if not example.suite:
        raise PackageError(f'{case} is in no suite (a folder holding good/ and bad/), so there '
                           'is nowhere for its clone to go')
    target = OPPOSITE[example.expect] if expect == 'opposite' else \
        example.expect if expect == 'same' else expect
    if target not in OPPOSITE:
        raise PackageError(f'a clone either conforms or violates, not {expect!r}')
    stem = os.path.basename(case)[:-len('.jsonld')] if case.endswith('.jsonld') \
        else os.path.basename(case)
    name = name or (f'{stem}-copy' if target == example.expect else
                    f'{stem}-{"violates" if target == "invalid" else "conforms"}')
    if target == example.expect:
        description = example.description or f'A copy of {case}.'
    elif target == 'invalid':
        description = (f'Cloned from {case}, which conforms. It fails until its data is '
                       'edited to break what it should show, and that is asserted.')
    else:
        description = (f'Cloned from {case}, which violates. It fails until its data is '
                       'edited so it conforms.')
    made = add_test_case(package, example.suite, target, 'copy', source=case, name=name,
                         description=description)

    copied = 0
    if target == example.expect and example.asserts:
        directory = os.path.dirname(made['file'])
        source = os.path.join(directory, EXPECTATIONS)
        with open(source, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        entry = next(e for e in raw.get('examples') or []
                     if os.path.normpath(os.path.join(directory, e.get('path', ''))) ==
                     os.path.normpath(made['file']))
        entry['asserts'] = [dict(a) for a in example.asserts]
        copied = len(example.asserts)
        with open(source, 'w', encoding='utf-8') as handle:
            _yaml().dump(raw, handle)
        made = dict(made, **_outcome(package, made['case']))
    return dict(made, source=case, sourceExpect=example.expect, asserts=copied)


def _outcome(package, case):
    """Whether a declared case passes now, as `semforge test` says."""
    from ..package.loader import reload_keeping_shapes
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs
    from .runner import run_tests

    fresh = reload_keeping_shapes(package)
    example = next(e for e in load_expectations(fresh.path).examples if e.path == case)
    report = validate_graphs(compose(fresh, example), fresh.shapes, fresh.knowledge,
                             strict=False)
    outcome = run_tests([(example, report)], known_constraints(fresh))[0]
    return {'violations': len(report.violations), 'passes': outcome.passed,
            'failures': list(outcome.failures)}
