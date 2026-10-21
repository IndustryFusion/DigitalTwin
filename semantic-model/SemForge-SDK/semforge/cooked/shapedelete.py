"""Deleting a shape -- and what goes with it, said before anything is written.

A shape is more than its statement: asserts name its constraints, a bad case
may exist only to make it fire, the digest of every residue it contributes to
names it, and another shape may reach it through `sh:node`. Deleting the
statement alone leaves stale asserts and failing cases; deleting it under a
reference leaves a `sh:node` to nothing, which a validator treats as an
error. So the deletion is planned first, a reference refuses it, and what
goes with it is the person's choice: the asserts, and the cases that then
mean nothing.
"""

import os
import shutil

from rdflib import BNode, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF, RDFS, SH

from ..errors import PackageError
from ..validate.normalise import curie, local


def _own_nodes(graph, shape):
    """The shape and every blank node its statement holds."""
    seen, todo = {shape}, [shape]
    while todo:
        node = todo.pop()
        for _, obj in graph.predicate_objects(node):
            if isinstance(obj, BNode) and obj not in seen:
                seen.add(obj)
                todo.append(obj)
    return seen


def _references(package, shape):
    """(who, how) for every statement outside the shape that names it."""
    own = _own_nodes(package.shapes, shape)
    found = []
    for graph in (package.shapes, package.knowledge):
        for subject, predicate in graph.subject_predicates(shape):
            if subject in own:
                continue
            who = curie(package.shapes, subject) if isinstance(subject, URIRef) \
                else 'a nested shape'
            found.append({'from': who, 'predicate': curie(package.shapes, predicate)})
    return found


def _cases(package, name):
    """For each case with an assert naming the shape: how many, and whether
    every assert it makes is about the shape."""
    from ..expect.store import load_expectations

    out = []
    for example in load_expectations(package.path).examples:
        mine = [a for a in example.asserts
                if str(a.get('constraint', '')).startswith(name + '/')]
        if mine:
            out.append({'case': example.path, 'asserts': len(mine),
                        'only': len(mine) == len(example.asserts),
                        'expect': example.expect})
    return out


def delete_plan(package, shape):
    """What deleting `shape` would remove -- or why it cannot be deleted."""
    from ..expect.store import load_expectations
    from .merge import _statement

    iri = URIRef(shape)
    if (iri, RDF.type, SH.NodeShape) not in package.shapes:
        raise PackageError(f'{shape} is not a node shape of this package')
    name = curie(package.shapes, iri)
    for graph in (package.shapes, package.knowledge):
        for cls in (RDFS.Class, OWL.Class):
            if (iri, RDF.type, cls) in graph:
                raise PackageError(f'{local(iri)} is also a class: deleting it would delete an '
                                   'entity type, which is not a shape deletion')
    references = _references(package, iri)
    if references:
        raise PackageError(
            f'{name} is reached from ' + ', '.join(f'{r["from"]} ({r["predicate"]})'
                                                   for r in references) +
            '; deleted, that reference would point at nothing. Change it first.')
    path, _ = _statement(package, iri)
    at = package.index('shapes').locator(str(iri)) or f'{path}:1'

    cases = _cases(package, name)
    only = [c['case'] for c in cases if c['only']]
    residues = [e.path for e in load_expectations(package.path).examples if e.residue]
    folder = _suite_folder(package, local(iri))
    suite = os.path.basename(folder) if os.path.isdir(folder) else ''
    suite_empties = bool(suite) and set(_suite_cases(package, suite)) <= set(only)
    return {'shape': str(iri), 'name': name, 'file': path, 'definedAt': at,
            'cases': cases, 'onlyCases': only, 'residues': residues,
            'suite': suite, 'suiteEmpties': suite_empties,
            'asserts': sum(c['asserts'] for c in cases)}


def _suite_folder(package, name):
    from ..expect.store import examples_root

    return os.path.join(examples_root(package.path), f'test_{name}')


def _suite_cases(package, suite):
    from ..expect.store import load_expectations

    return [e.path for e in load_expectations(package.path).examples
            if e.path.startswith(suite + '/')]


def _drop(package, name, cases):
    """Remove the asserts naming `name`, and the entries of `cases` (paths
    relative to examples/); returns (asserts removed, case files to delete)."""
    from ..expect.store import _yaml, examples_root, expectation_files

    root = examples_root(package.path)
    removed, files = 0, []
    included = set()
    for path in expectation_files(package.path):
        with open(path, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        for entry in raw.get('examples') or []:
            included.update(str(i).replace('\\', '/') for i in entry.get('include') or [])
    for path in expectation_files(package.path):
        directory = os.path.dirname(path)
        with open(path, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        changed = False
        entries = raw.get('examples') or []
        for entry in list(entries):
            relative = os.path.relpath(os.path.join(directory, entry.get('path', '')),
                                       root).replace(os.sep, '/')
            if relative in cases:
                removed += len(entry.get('asserts') or [])   # every one names the shape
                entries.remove(entry)
                if relative not in included:      # another case still builds on it
                    files.append(os.path.join(root, relative))
                changed = True
                continue
            asserts = entry.get('asserts') or []
            keep = [a for a in asserts if not str(a.get('constraint', '')).startswith(name + '/')]
            if len(keep) != len(asserts):
                removed += len(asserts) - len(keep)
                if keep:
                    entry['asserts'] = keep
                else:
                    del entry['asserts']
                changed = True
        if changed:
            with open(path, 'w', encoding='utf-8') as handle:
                _yaml().dump(raw, handle)
    return removed, files


def delete_shape(package, shape, asserts=False, cases=False):
    """Delete `shape`; with `asserts`, the asserts naming it; with `cases`
    too, the cases whose every assert is about it (and its test_<Shape>
    suite, when that leaves it empty). The plan, as done.

    Pinned residues that held before are pinned again: the shape leaves
    their digest. A case failing before is left failing.
    """
    from ..expect.store import load_expectations, save_expectations
    from ..package import load
    from .merge import _knowledge_without_text, _statement
    from .rename import _held, _outcomes

    done = delete_plan(package, shape)
    iri = URIRef(done['shape'])
    held = _held(package, done['residues'])
    path, text = _statement(package, iri)
    after_text = _knowledge_without_text(text, iri)

    # Nothing but the shape may go: the shapes graph after is the graph before
    # without the shape's own statements, exactly.
    before, after = Graph(), Graph()
    for each in package.files('shapes'):
        with open(each, encoding='utf-8') as handle:
            source = handle.read()
        before.parse(data=source, format='turtle')
        after.parse(data=after_text if each == path else source, format='turtle')
    if (iri, None, None) in after:
        raise PackageError(f'{done["name"]} is said in more than one statement; delete the '
                           'others by hand first. Nothing written.')
    own = _own_nodes(before, iri)
    expected = Graph()
    for triple in before:
        if triple[0] not in own:
            expected.add(triple)
    if not isomorphic(expected, after):
        raise PackageError(f'deleting {done["name"]} would change more than its own '
                           'statement; nothing written')

    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(after_text)

    removed, files, suite_removed = 0, [], ''
    gone = set(done['onlyCases']) if asserts and cases else set()
    if asserts:
        removed, files = _drop(package, done['name'], gone)
        for file in files:
            if os.path.exists(file):
                os.remove(file)
        if gone and done['suiteEmpties']:
            folder = _suite_folder(package, local(iri))
            if os.path.isdir(folder):
                shutil.rmtree(folder)
                suite_removed = done['suite']

    repinned = []
    keep = {p for p in held if p not in gone}
    if keep:
        fresh = load(package.path)
        expectations = load_expectations(fresh.path)
        outcomes = {o.example: o for o in _outcomes(fresh, expectations, keep)}
        for example in expectations.examples:
            outcome = outcomes.get(example.path)
            if outcome is not None and example.residue != outcome.residue:
                example.residue = outcome.residue
                repinned.append(example.path)
        if repinned:
            save_expectations(expectations)
    return dict(done, assertsRemoved=removed, casesRemoved=sorted(gone),
                filesRemoved=sorted(files), suiteRemoved=suite_removed,
                repinned=sorted(repinned))
