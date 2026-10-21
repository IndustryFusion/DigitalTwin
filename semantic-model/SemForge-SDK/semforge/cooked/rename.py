"""Renaming a shape, a test case, a suite -- and everything that names it.

A shape's IRI is written where it is declared, where other shapes reach it
(`sh:node` and the like), in a SPARQL body now and then, in every assert that
names one of its constraints (`ns:Shape/…Component`), and in the digest of
every residue it contributes to. A rename that misses one of those leaves a
package that reads as validated and is not: a stale assert, a residue that
no longer matches, a `sh:node` to nothing. So the rename is planned first,
said in full, and written only when the shapes graph after it is the graph
before it with one IRI replaced.

A case is named by its file, relative to the expectations.yaml that declares
it; a suite by its folder. Neither name enters a digest, so renaming one is
a move and an edit of the entries that point at it.
"""

import os
import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from ..errors import PackageError
from ..rdfio.turtle_index import terms
from ..validate.normalise import curie, local

NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*')


def _valid_name(name, what):
    name = str(name or '').strip()
    if not NAME.fullmatch(name):
        raise PackageError(f'{name!r} is not a {what} name: a letter or "_" first, then '
                           'letters, digits, "_", "-" and "." (not at the end)')
    return name


# --- shapes ------------------------------------------------------------------------

def _files(package):
    return list(package.files('shapes')) + list(package.files('knowledge'))


def _uses(text, iri):
    return [t for t in terms(text) if t.iri == iri]


def _renamed_text(text, iri, new_iri, new_name, quoted=None):
    """`text` with every term that resolves to `iri` written as `new_iri`.

    A prefixed name keeps its prefix, an <IRI> stays one; nothing else moves.
    What was rewritten inside a string -- a SPARQL body -- is added to
    `quoted` as (as written, as rewritten), for the check after.
    """
    out, at = [], 0
    for term in _uses(text, iri):
        if term.raw.startswith('<'):
            written = f'<{new_iri}>'
        else:
            written = term.raw[:term.raw.index(':') + 1] + new_name
        if term.quoted and quoted is not None:
            quoted.add((term.raw, written))
        out.append(text[at:term.start])
        out.append(written)
        at = term.end
    out.append(text[at:])
    return ''.join(out)


def _in_literal(term, quoted):
    """A literal as the rename should leave it: its quoted uses rewritten."""
    if not isinstance(term, Literal) or not quoted:
        return term
    value = str(term)
    for raw, written in quoted:
        # The whole term, not the start of a longer name.
        value = re.sub(re.escape(raw) + r'(?![A-Za-z0-9_-])', lambda _: written, value)
    return Literal(value, lang=term.language, datatype=term.datatype)


def _suite_folder(package, name):
    from ..expect.store import examples_root

    return os.path.join(examples_root(package.path), f'test_{name}')


def rename_plan(package, shape, new_name):
    """What renaming `shape` to `new_name` would change -- or why it cannot."""
    from ..expect.store import load_expectations

    iri = URIRef(shape)
    if (iri, RDF.type, SH.NodeShape) not in package.shapes:
        raise PackageError(f'{shape} is not a node shape of this package')
    new_name = _valid_name(new_name, 'shape')
    old_name = local(iri)
    # The random part stays across a rename -- the name changes, the marker
    # that it is an identifier does not. A shape without one gets one,
    # derived from its IRI so the plan and the rename agree on it.
    import uuid

    from .shapes import base_name, identity_suffix, same_name, with_identity

    taken = same_name(package, new_name, but=iri)
    if taken is not None:
        raise PackageError(f'{base_name(new_name)} is already a shape of this package '
                           f'({curie(package.shapes, taken)})')

    new_name = with_identity(new_name, identity_suffix(old_name) or
                             f'-{uuid.uuid5(uuid.NAMESPACE_URL, str(iri)).hex[:8]}')
    if new_name == old_name:
        raise PackageError(f'{old_name} is already its name')
    namespace = str(iri)[:-len(old_name)]
    new_iri = namespace + new_name
    for graph, what in ((package.shapes, 'shape'), (package.knowledge, 'term')):
        if (URIRef(new_iri), None, None) in graph or (None, None, URIRef(new_iri)) in graph:
            raise PackageError(f'{new_name} is already a {what} of this package')
    for graph in (package.shapes, package.knowledge):
        for cls in (RDFS.Class, OWL.Class):
            if (iri, RDF.type, cls) in graph:
                raise PackageError(f'{old_name} is also a class: renaming it would rename an '
                                   'entity type, which is not a shape rename')

    files = []
    for path in _files(package):
        with open(path, encoding='utf-8') as handle:
            found = _uses(handle.read(), str(iri))
        if found:
            files.append({'file': path, 'references': len(found),
                          'inQueries': sum(1 for t in found if t.quoted)})

    name = curie(package.shapes, iri)
    asserts, residues = [], []
    for example in load_expectations(package.path).examples:
        count = sum(1 for item in example.asserts
                    if str(item.get('constraint', '')).startswith(name + '/'))
        if count:
            asserts.append({'case': example.path, 'count': count})
        if example.residue:
            residues.append(example.path)
    folder = _suite_folder(package, old_name)
    target = _suite_folder(package, new_name)
    suite = None
    if os.path.isdir(folder):
        suite = {'from': os.path.basename(folder), 'to': os.path.basename(target),
                 'free': not os.path.exists(target)}
    return {'shape': str(iri), 'name': name, 'oldName': old_name, 'newName': new_name,
            'newIri': new_iri, 'newCurie': name[:-len(old_name)] + new_name
            if name.endswith(old_name) else new_iri,
            'files': files, 'asserts': asserts, 'residues': residues, 'suite': suite}


def _outcomes(package, expectations, paths):
    """The test outcomes of the cases at `paths`, as `semforge test` has them."""
    from ..expect.runner import run_tests
    from ..expect.store import compose
    from ..sanity import known_constraints
    from ..validate.orchestrator import validate_graphs

    paired = [(example, validate_graphs(compose(package, example), package.shapes,
                                        package.knowledge, strict=False))
              for example in expectations.examples if example.path in paths]
    return run_tests(paired, known_constraints(package))


def _held(package, paths):
    """Of the cases at `paths`, the ones whose pinned residue holds now."""
    from ..expect.store import load_expectations

    outcomes = _outcomes(package, load_expectations(package.path), set(paths))
    return {o.example for o in outcomes if not o.residue_changed}


def rename_shape(package, shape, new_name, suite=False):
    """Rename `shape` everywhere it is named; the plan, as done.

    The pinned residues of cases that held before are pinned again: the
    digest names the shape, and a rename changes no verdict. A case that was
    failing before is left failing -- it says something the rename did not.
    """
    from rdflib.compare import isomorphic

    from ..expect.store import load_expectations, save_expectations
    from ..package import load
    from .merge import _rename_asserts

    done = rename_plan(package, shape, new_name)
    # The plan's name: the one asked for, with its identity suffix.
    new_name = done['newName']
    iri, new_iri = done['shape'], done['newIri']
    held = _held(package, done['residues'])

    writes, quoted = {}, set()
    for item in done['files']:
        with open(item['file'], encoding='utf-8') as handle:
            writes[item['file']] = _renamed_text(handle.read(), iri, new_iri, new_name, quoted)

    # The shapes graph after must be the graph before with one IRI replaced
    # (and, inside a query, the same name rewritten): no statement lost, none
    # added, no other term touched.
    def graph(texts):
        out = Graph()
        for path in package.files('shapes'):
            with open(path, encoding='utf-8') as handle:
                out.parse(data=texts.get(path, handle.read()), format='turtle')
        return out

    expected = Graph()
    swap = {URIRef(iri): URIRef(new_iri)}
    for triple in graph({}):
        expected.add(tuple(_in_literal(swap.get(term, term), quoted) for term in triple))
    if not isomorphic(expected, graph(writes)):
        raise PackageError(f'renaming {done["oldName"]} would change more than its name; '
                           'nothing written')

    for path, text in writes.items():
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    renamed, _ = _rename_asserts(package, done['name'], done['newCurie'])

    moved = ''
    if suite and done['suite'] and done['suite']['free']:
        os.rename(_suite_folder(package, done['oldName']),
                  _suite_folder(package, new_name))
        moved = done['suite']['to']

    def now(path):
        if moved and path.startswith(done['suite']['from'] + '/'):
            return moved + path[len(done['suite']['from']):]
        return path

    repinned = []
    if held:
        after = load(package.path)
        expectations = load_expectations(after.path)
        paths = {now(path) for path in held}
        outcomes = {o.example: o for o in _outcomes(after, expectations, paths)}
        for example in expectations.examples:
            outcome = outcomes.get(example.path)
            if outcome is not None and example.residue != outcome.residue:
                example.residue = outcome.residue
                repinned.append(example.path)
        if repinned:
            save_expectations(expectations)
    return dict(done, asserts=renamed, repinned=sorted(repinned), suiteMoved=moved,
                files=[item['file'] for item in done['files']])


# --- cases and suites --------------------------------------------------------------

def _entries(package):
    """(expectations.yaml, its parsed form) for every file declaring cases."""
    from ..expect.store import _yaml, expectation_files

    for path in expectation_files(package.path):
        with open(path, encoding='utf-8') as handle:
            yield path, _yaml().load(handle) or {}


def _dump(path, raw):
    from ..expect.store import _yaml

    with open(path, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)


def rename_case(package, case, new_name):
    """Rename the case at `case` (relative to examples/) to `new_name`.jsonld.

    Its entry's `path` follows, and so does any `include` naming the file.
    """
    from ..expect.store import examples_root

    root = examples_root(package.path)
    case = str(case or '')
    if os.path.isabs(case):                        # a tree row knows its file
        case = os.path.relpath(case, root)
    case = case.replace('\\', '/').strip('/')
    source = os.path.normpath(os.path.join(root, case))
    if not source.startswith(os.path.normpath(root) + os.sep) or not os.path.isfile(source):
        raise PackageError(f'{case} is not a case file under {root}')
    stem = str(new_name or '').strip()
    if stem.endswith('.jsonld'):
        stem = stem[:-len('.jsonld')]
    stem = _valid_name(stem, 'case')
    target = os.path.join(os.path.dirname(source), f'{stem}.jsonld')
    if target == source:
        raise PackageError(f'{os.path.basename(source)} is already its name')
    if os.path.exists(target):
        raise PackageError(f'{os.path.relpath(target, root)} already exists')

    declared, included = 0, 0
    old_relative = os.path.relpath(source, root).replace(os.sep, '/')
    new_relative = os.path.relpath(target, root).replace(os.sep, '/')
    changes = []
    for path, raw in _entries(package):
        directory = os.path.dirname(path)
        changed = False
        for entry in raw.get('examples') or []:
            if os.path.normpath(os.path.join(directory, entry.get('path', ''))) == source:
                entry['path'] = os.path.relpath(target, directory).replace(os.sep, '/')
                declared += 1
                changed = True
            includes = entry.get('include') or []
            for index, item in enumerate(includes):
                if str(item).replace('\\', '/') == old_relative:
                    includes[index] = new_relative
                    included += 1
                    changed = True
        if changed:
            changes.append((path, raw))
    if not declared:
        raise PackageError(f'{old_relative} is not declared in any expectations.yaml')
    os.rename(source, target)
    for path, raw in changes:
        _dump(path, raw)
    return {'file': target, 'case': new_relative, 'from': old_relative,
            'includes': included}


def rename_suite(package, suite, new_name):
    """Rename the suite folder `suite` (relative to examples/) to `new_name`.

    Its cases' paths are relative to their own expectations.yaml, so nothing
    inside changes; an `include` elsewhere that reaches into it follows.
    """
    from ..expect.store import examples_root

    root = examples_root(package.path)
    suite = str(suite or '').replace('\\', '/').strip('/')
    source = os.path.normpath(os.path.join(root, suite))
    if not suite or not source.startswith(os.path.normpath(root) + os.sep) or \
            not os.path.isdir(source):
        raise PackageError(f'{suite} is not a suite folder under {root}')
    if os.path.basename(source) in ('good', 'bad'):
        raise PackageError('good/ and bad/ say what a case expects; rename the suite above them')
    new_name = _valid_name(new_name, 'suite')
    target = os.path.join(os.path.dirname(source), new_name)
    if target == source:
        raise PackageError(f'{new_name} is already its name')
    if os.path.exists(target):
        raise PackageError(f'{os.path.relpath(target, root)} already exists')

    old_prefix = os.path.relpath(source, root).replace(os.sep, '/') + '/'
    new_prefix = os.path.relpath(target, root).replace(os.sep, '/') + '/'
    changes, included = [], 0
    for path, raw in _entries(package):
        changed = False
        for entry in raw.get('examples') or []:
            includes = entry.get('include') or []
            for index, item in enumerate(includes):
                text = str(item).replace('\\', '/')
                if text.startswith(old_prefix):
                    includes[index] = new_prefix + text[len(old_prefix):]
                    included += 1
                    changed = True
        if changed:
            changes.append((path, raw))
    os.rename(source, target)
    for path, raw in changes:
        moved = path.replace(source + os.sep, target + os.sep, 1)
        _dump(moved, raw)
    return {'folder': target, 'source': source, 'suite': new_prefix[:-1],
            'from': old_prefix[:-1], 'includes': included}


# --- a rename typed into the .ttl ------------------------------------------------------

THIS = URIRef('urn:semforge:this-shape')


def shape_prints(package):
    """{shape IRI: fingerprint of what it says}, its own name left out.

    Two shapes with the same print say the same thing under different
    names -- so one vanishing as the other appears, between two reads of
    the package, is a rename typed into the file.
    """
    import hashlib

    from rdflib import BNode
    from rdflib.compare import to_canonical_graph

    graph = package.shapes
    out = {}
    for shape in set(graph.subjects(RDF.type, SH.NodeShape)):
        if not isinstance(shape, URIRef):
            continue
        own = Graph()
        seen, todo = {shape}, [shape]
        while todo:
            node = todo.pop()
            for predicate, obj in graph.predicate_objects(node):
                own.add((THIS if node == shape else node, predicate,
                         THIS if obj == shape else obj))
                if isinstance(obj, BNode) and obj not in seen:
                    seen.add(obj)
                    todo.append(obj)
        text = '\n'.join(sorted(to_canonical_graph(own).serialize(format='nt').splitlines()))
        out[str(shape)] = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return out


def renamed_pairs(before, after):
    """[(old IRI, new IRI)] for each shape that vanished as one saying exactly
    the same appeared -- and only where that pairing is unambiguous."""
    gone = {iri: p for iri, p in before.items() if iri not in after}
    came = {iri: p for iri, p in after.items() if iri not in before}
    pairs = []
    for old, print_ in gone.items():
        matches = [new for new, p in came.items() if p == print_]
        twins = [o for o, p in gone.items() if p == print_]
        if len(matches) == 1 and len(twins) == 1:
            pairs.append((old, matches[0]))
    return sorted(pairs)


def _names(package, old, new):
    old_name, new_name = local(URIRef(old)), local(URIRef(new))
    return (curie(package.shapes, URIRef(old)), curie(package.shapes, URIRef(new)),
            old_name, new_name)


def follow_plan(package, old, new):
    """What still names `old` after it was renamed to `new` in the file, or
    None when nothing does."""
    from ..expect.store import load_expectations

    old_curie, new_curie, old_name, new_name = _names(package, old, new)
    asserts = sum(1 for example in load_expectations(package.path).examples
                  for item in example.asserts
                  if str(item.get('constraint', '')).startswith(old_curie + '/'))
    folder, target = _suite_folder(package, old_name), _suite_folder(package, new_name)
    suite = {'from': os.path.basename(folder), 'to': os.path.basename(target),
             'free': not os.path.exists(target)} if os.path.isdir(folder) else None
    if not asserts and suite is None:
        return None
    return {'shape': str(old), 'newIri': str(new), 'name': old_curie, 'newCurie': new_curie,
            'oldName': old_name, 'newName': new_name, 'asserts': asserts, 'suite': suite}


def follow_rename(package, old, new, suite=False):
    """Carry along what a rename typed into the file left behind: the asserts
    naming the old shape, the residues pinned while it had its old name, and
    -- if asked -- its test_<Shape> suite.

    A residue is pinned again only when it is exactly what was pinned with the
    old name swapped back in: proof the rename is all that changed it.
    """
    from dataclasses import replace

    from ..expect.digest import residue_digest
    from ..expect.runner import constraint_ref
    from ..expect.store import compose, load_expectations, save_expectations
    from ..package import load
    from ..validate.orchestrator import validate_graphs
    from .merge import _rename_asserts

    plan = follow_plan(package, old, new) or {'name': curie(package.shapes, URIRef(old)),
                                              'suite': None}
    old_curie, new_curie, old_name, new_name = _names(package, old, new)
    renamed, _ = _rename_asserts(package, old_curie, new_curie)
    moved = ''
    if suite and plan['suite'] and plan['suite']['free']:
        os.rename(_suite_folder(package, old_name), _suite_folder(package, new_name))
        moved = plan['suite']['to']

    fresh = load(package.path)
    expectations = load_expectations(fresh.path)
    repinned = []
    for example in expectations.examples:
        if not example.residue:
            continue
        report = validate_graphs(compose(fresh, example), fresh.shapes, fresh.knowledge,
                                 strict=False)
        asserted = example.asserted_keys()
        residue = [r for r in report.results
                   if (r.resource, constraint_ref(r)) not in asserted]
        now = residue_digest(residue)
        if now == example.residue:
            continue
        before = [replace(r, shape=str(old)) if r.shape == str(new) else r for r in residue]
        if residue_digest(before) == example.residue:
            example.residue = now
            repinned.append(example.path)
    if repinned:
        save_expectations(expectations)
    return {'asserts': renamed, 'repinned': sorted(repinned), 'suiteMoved': moved,
            'name': old_curie, 'newCurie': new_curie}
