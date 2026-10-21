"""New test case…: add a test file to a suite, from wherever it should start.

The other ways to a case are aimed at one thing -- New test… at an attribute,
New case… at a SPARQL rule. This is the general one: a suite (an existing one
or a new one for a shape), good or bad, and a start -- a copy of a case, an
entity from the model, a fresh entity of a type with its required attributes
given valid values, an empty file, or a .jsonld already under examples/ that
no expectations file declares yet (a file nobody runs is worse than none:
the folder suggests coverage the suite does not have).

The case is declared in the expectations.yaml beside it, `expect: valid` or
`invalid`, and run once. A bad case is declared without asserts: what fires
is shown on its case page, and "Assert it" turns each firing into a claim.
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
    cases to copy, model entities, entity types, undeclared files."""
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
    entities = sorted({str(s) for s in package.model.subjects(RDF.type, None)
                       if isinstance(s, URIRef)})
    return {
        'root': root,
        'suites': suites,
        'shapes': [{'iri': str(s), 'name': curie(package.shapes, s), 'label': local(s)}
                   for s in every_node_shape(package.shapes)],
        'cases': [{'path': e.path, 'expect': e.expect, 'description': e.description}
                  for e in expectations.examples],
        'entities': entities,
        'types': [{'iri': t.iri, 'label': t.label, 'term': t.term}
                  for t in entity_types(package)[0]],
        'undeclared': undeclared,
    }


def _scene(package, start, source):
    """The documents a new case starts with."""
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
    """Write and declare a test case. `start` is copy | model | type | empty
    | existing (then `source` is the undeclared file, declared where it is).

    Returns {'file', 'case', 'expect', 'violations', 'passes', 'failures'}.
    """
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs
    from .newcase import _slug
    from .runner import run_tests

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
        documents = _scene(package, start, source)
        os.makedirs(directory, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(documents, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        written = True
    if not description:
        description = {'copy': f'Started from {source}.', 'model': f'{source}, from the model.',
                       'type': 'A new entity, its required attributes given valid values.',
                       'empty': '', 'existing': ''}.get(start, '')
    try:
        _declare(directory, file_name, expect, description)
    except PackageError:
        if written:
            os.remove(path)
        raise

    from ..package import load

    fresh = load(package.path)
    case = os.path.relpath(path, root)
    example = next(e for e in load_expectations(fresh.path).examples if e.path == case)
    try:
        report = validate_graphs(compose(fresh, example), fresh.shapes, fresh.knowledge,
                                 strict=False)
    except Exception as exc:                       # noqa: BLE001
        return {'file': path, 'case': case, 'expect': expect, 'violations': 0,
                'passes': False, 'failures': [f'does not load: {exc}']}
    outcome = run_tests([(example, report)], known_constraints(fresh))[0]
    return {'file': path, 'case': case, 'expect': expect,
            'violations': len(report.violations), 'passes': outcome.passed,
            'failures': list(outcome.failures)}


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
    from ..package import load
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs
    from .runner import run_tests

    fresh = load(package.path)
    example = next(e for e in load_expectations(fresh.path).examples if e.path == case)
    report = validate_graphs(compose(fresh, example), fresh.shapes, fresh.knowledge,
                             strict=False)
    outcome = run_tests([(example, report)], known_constraints(fresh))[0]
    return {'violations': len(report.violations), 'passes': outcome.passed,
            'failures': list(outcome.failures)}
