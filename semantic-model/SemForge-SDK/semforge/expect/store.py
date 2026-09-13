"""The expectation file.

ruamel.yaml in round-trip mode on purpose: expectation files are human-edited
and `semforge accept` rewrites them in place, so comments and key order have to
survive. pyyaml would destroy every comment in the file on the first accept.
"""

import json
import os
from dataclasses import dataclass, field

from ruamel.yaml import YAML

from ..errors import PackageError

# One file per good/ or bad/ directory, sitting with the cases it declares.
#
# A central list means every new case edits one shared file, so two people
# adding a test to different shapes collide over it. Declaring a case next to
# itself makes a suite something you can add, move or delete on its own.
EXPECTATIONS = 'expectations.yaml'
EXAMPLES = 'examples'


def examples_root(package_path):
    """Where the cases live.

    `model/examples/` if the package groups its data under `model/`, else
    `examples/` beside the artifacts. Both are the same thing said twice: the
    suite and the scratchpad are two kinds of data about the same model, so they
    belong at the same level -- under `model/` when a package says so, and at
    the root for the layout the kms already has.
    """
    for candidate in (os.path.join(package_path, 'model', EXAMPLES),
                      os.path.join(package_path, EXAMPLES)):
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(package_path, EXAMPLES)


def _yaml():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


@dataclass
class Example:
    path: str
    expect: str = 'valid'            # valid | invalid
    asserts: list = field(default_factory=list)
    residue: str = ''
    conformance: str = ''            # 'full' requires empty residue
    include: list = field(default_factory=list)
    description: str = ''
    source: str = ''           # the expectations.yaml that declares it
    suite: str = ''            # the test_<Shape> directory it belongs to

    @property
    def group(self):
        """good, bad, or '' when the suite draws no such distinction.

        Folder names group and select; they decide nothing. What an example is
        FOR comes from `expect` and `asserts` -- a file under bad/ that asserts
        nothing is an unfinished test, not a passing one.
        """
        parts = self.path.replace('\\', '/').split('/')
        return parts[-2] if len(parts) > 1 and parts[-2] in GROUPS else ''

    @property
    def requires_full_conformance(self):
        return self.conformance == 'full'

    def asserted_keys(self):
        """The (resource, constraint reference) pairs this example is about."""
        return {(a.get('resource', ''), a['constraint']) for a in self.asserts}


@dataclass
class Expectations:
    path: str
    examples: list = field(default_factory=list)
    raw: object = None

    def for_path(self, example_path):
        for example in self.examples:
            if example.path == example_path:
                return example
        return None


def expectation_files(package_path):
    """Every expectations.yaml under examples/, deepest path first."""
    root = examples_root(package_path)
    found = []
    for current, _, names in os.walk(root):
        if EXPECTATIONS in names:
            found.append(os.path.join(current, EXPECTATIONS))
    return sorted(found)


def load_expectations(package_path):
    """Every case declared anywhere under examples/.

    A case's `path` is relative to the file that declares it, so a suite can be
    moved or renamed without editing anything inside it. Includes stay relative
    to examples/, because a subobject is shared and does not belong to the
    suite that happens to use it.
    """
    root = examples_root(package_path)
    examples = []
    raw_by_file = {}

    for path in expectation_files(package_path):
        directory = os.path.dirname(path)
        with open(path) as handle:
            raw = _yaml().load(handle) or {}
        raw_by_file[path] = raw

        for entry in raw.get('examples', []) or []:
            if 'path' not in entry:
                raise PackageError(f'{path}: an example entry has no "path"')
            relative = os.path.relpath(
                os.path.join(directory, entry['path']), root)
            # A case outside good/ or bad/ is assumed to conform. That is the
            # weaker position and it is worth naming: a suite with no bad case
            # cannot tell a constraint that is satisfied from one that could
            # never fire, which is what `semforge test --coverage` reports.
            examples.append(Example(
                path=relative,
                expect=entry.get('expect', 'valid'),
                asserts=list(entry.get('asserts', []) or []),
                residue=entry.get('residue', ''),
                conformance=entry.get('conformance', ''),
                include=list(entry.get('include', []) or []),
                description=entry.get('description', ''),
                source=path,
                suite=_suite_of(relative)))

    return Expectations(path=root, examples=examples, raw=raw_by_file)


GROUPS = ('good', 'bad')


def _suite_of(relative):
    """The directory a case belongs to.

    Any name will do -- test_<Shape> reads well but nothing depends on it. What
    a suite IS, is a directory holding good/ and bad/; the suite is whatever
    sits above them.
    """
    parts = relative.replace('\\', '/').split('/')
    for index, part in enumerate(parts[:-1]):
        if part in GROUPS:
            return '/'.join(parts[:index]) if index else ''
    return '/'.join(parts[:-1])


def save_expectations(expectations):
    """Write each case back to the file that declares it.

    Accept has to land in the right suite: writing every residue into one file
    would undo the point of distributing them.
    """
    raw_by_file = expectations.raw if isinstance(expectations.raw, dict) else {}
    if not raw_by_file and expectations.examples:
        # Nothing declared anything yet -- the package is being described for
        # the first time, so put it where a reader will look.
        os.makedirs(expectations.path, exist_ok=True)
        source = os.path.join(expectations.path, EXPECTATIONS)
        raw_by_file = {source: {'examples': [
            {'path': e.path, 'expect': e.expect, 'residue': e.residue}
            for e in expectations.examples]}}
        for example in expectations.examples:
            example.source = source
    for source, raw in raw_by_file.items():
        directory = os.path.dirname(source)
        mine = {e.path: e for e in expectations.examples if e.source == source}
        for entry in raw.get('examples') or []:
            relative = os.path.relpath(
                os.path.join(directory, entry.get('path', '')),
                expectations.path)
            example = mine.get(relative)
            if example is not None and example.residue:
                entry['residue'] = example.residue
        with open(source, 'w') as handle:
            _yaml().dump(raw, handle)


def compose(package, example):
    """The data graph for one example: its own file plus what it includes.

    Subobjects exist so a case can say what it is about. "A cutter running
    while its filter is off" needs a filter, a cartridge and a workpiece to be
    a well-formed entity at all, and repeating them in every case makes the
    difference between two cases hard to see and easy to get wrong.

    Includes are composed BEFORE the example, but that does NOT make the
    example win: everything is parsed into one graph, so two definitions of the
    same id MERGE -- an include saying `hasState ON` and a case saying OFF
    produce an entity with both. Measured, in test_identity.py. To vary an
    entity between cases, include a different subobject, which is what
    bad/filter-off does; `semforge test` reports a shared id inside one case as
    an error.
    """
    import os

    from rdflib import Graph

    from ..package.context import context_config, resolve_model_document

    config = context_config(package.path)
    graph = Graph()
    for relative in list(example.include) + [example.path]:
        path = os.path.join(examples_root(package.path), relative) \
            if not os.path.isabs(relative) else relative
        if not os.path.exists(path):
            path = os.path.join(package.path, relative)
        if not os.path.exists(path):
            raise PackageError(
                f'{example.path}: cannot find {relative}')
        document, _ = resolve_model_document(package.path, path, config)
        graph.parse(data=json.dumps(document), format='json-ld')
    return graph


def discover(package_path, folder=None):
    """Every .jsonld under examples/, as relative paths.

    Used to notice a file nobody declared -- an example that exists and is
    never run is worse than no example, because the directory listing suggests
    coverage that the suite does not have.
    """
    import os

    root = os.path.join(package_path, folder) if folder \
        else examples_root(package_path)
    found = []
    for current, _, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(('.jsonld', '.json')):
                found.append(os.path.relpath(os.path.join(current, name), root))
    return sorted(found)
