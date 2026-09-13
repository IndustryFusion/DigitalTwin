"""Who is who inside one case: an id, and the file it was read from.

An NGSI-LD id identifies an entity, and in a suite of examples the id alone is
not the whole address -- the file is. `urn:filter:1` in
`examples/subobjects/filter-on.jsonld` and `urn:filter:1` in
`examples/subobjects/filter-off.jsonld` are the same thing in two states, and
that is how a variant is written. Nothing is reported for it: the path
distinguishes them, so everything that names an entity shows both.

What IS reported is an id that cannot be resolved to one entity anyway: two
entities the path cannot separate (inside one document, or inside one composed
case), an entity with no @context, which has no id at all as far as the graph is
concerned, and a reference to an id that nothing in the case defines.

  * **Twice in one file.** Always wrong. Nothing distinguishes the two, and
    whichever the reader means, the graph has one entity with both sets of
    attributes.

  * **Twice inside one composed case.** Also wrong, and the dangerous one. The
    case and its includes are parsed into ONE graph, so the definitions MERGE:
    an include saying `hasState ON` and a case saying `hasState OFF` produce an
    entity with both, not an entity that is off. Measured, not assumed -- and it
    is why `compose` cannot be used to override an included entity.

  * **No `@context`.** `id` and `type` are ordinary keys until a context maps
    them, so the entity expands to a blank node, no shape targets it, and the
    case passes having validated nothing -- the same failure shape as a
    constraint that cannot fire.

  * **A reference to nobody.** Within a case the composition is the world, so a
    relationship whose object no file defines leaves every constraint about that
    target with nothing to check. It is what a half-finished rename looks like:
    an id changes in a subobject, the filters pointing at it go nowhere, and the
    verdict moves somewhere unrelated.
"""

import json
import os
from dataclasses import dataclass, field

from .store import discover, load_expectations


@dataclass
class Finding:
    """Something about a document that makes it describe the wrong thing."""
    entity: str
    severity: str
    kind: str
    places: list = field(default_factory=list)
    message: str = ''


@dataclass
class Duplicate:
    entity: str
    severity: str                              # error | warning
    kind: str                                  # in-file | in-case
    places: list = field(default_factory=list)  # [(file, line)]
    message: str = ''
    case: str = ''                             # for in-case, which case


def _entity_lines(path):
    """[(id, line)] for a document, in order, including repeats."""
    from ..cooked.jsonloc import locate

    try:
        with open(path, encoding='utf-8') as handle:
            raw = handle.read()
        document = json.loads(raw)
    except Exception:                              # noqa: BLE001
        return []
    try:
        index = locate(raw)
    except Exception:                              # noqa: BLE001
        index = {}
    entities = document if isinstance(document, list) else [document]
    out = []
    for position, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        identifier = str(entity.get('id') or entity.get('@id') or '')
        if identifier:
            out.append((identifier, index.get((position,)) or 1))
    return out


def example_files(package):
    """Every JSON-LD document of the package: its model and its examples."""
    files = [os.path.abspath(document) for document in package.files('model')
             if os.path.exists(document)]
    root = os.path.join(package.path, 'examples')
    if os.path.isdir(root):
        for relative in discover(package.path):
            files.append(os.path.abspath(os.path.join(root, relative)))
    return files


def _case_groups(package, expectations):
    """{case path: {absolute files composed into it}}."""
    groups = {}
    for example in expectations.examples:
        members = set()
        for relative in list(example.include) + [example.path]:
            for candidate in (os.path.join(package.path, 'examples', relative),
                              os.path.join(package.path, relative), relative):
                if os.path.exists(candidate):
                    members.add(os.path.abspath(candidate))
                    break
        groups[example.path] = members
    return groups


def duplicate_ids(package, expectations=None):
    """Every id that names more than one entity where the path cannot tell them
    apart."""
    expectations = expectations if expectations is not None \
        else load_expectations(package.path)

    by_file = {path: _entity_lines(path) for path in example_files(package)}
    found = []

    # 1. Twice in the same document.
    for path, entries in by_file.items():
        seen = {}
        for identifier, line in entries:
            seen.setdefault(identifier, []).append(line)
        for identifier, lines in seen.items():
            if len(lines) > 1:
                found.append(Duplicate(
                    entity=identifier, severity='error', kind='in-file',
                    places=[(path, line) for line in lines],
                    message=(
                        f'{identifier} is defined {len(lines)} times in '
                        f'{os.path.basename(path)} (lines '
                        + ', '.join(str(line) for line in lines) + '). '
                        'They are one entity carrying every attribute of both; '
                        'give them different ids.')))

    # 2. Twice inside one composed case -- a merge, not an override.
    for case, members in _case_groups(package, expectations).items():
        where = {}
        for path in sorted(members):
            for identifier, line in by_file.get(path, []):
                where.setdefault(identifier, []).append((path, line))
        for identifier, places in where.items():
            files = {path for path, _ in places}
            if len(files) > 1:
                found.append(Duplicate(
                    entity=identifier, severity='error', kind='in-case',
                    places=places, case=case,
                    message=(
                        f'{identifier} is defined by '
                        + ' and '.join(sorted(os.path.basename(p)
                                              for p in files))
                        + f', both composed into {case}. The files are parsed '
                        'into one graph, so the definitions MERGE rather than '
                        'override: the entity ends up with the attributes of '
                        'both. To vary an entity between cases, include a '
                        'different subobject instead.')))

    return sorted(found, key=lambda d: (d.entity, d.kind))


def missing_context(package):
    """Entities that will not expand, because nothing gives them a context.

    In JSON-LD `id` and `type` are ordinary keys until a context maps them. An
    entity without one becomes a blank node with a literal-ish predicate, every
    shape's `sh:targetClass` misses it, and the case passes having validated
    nothing -- the exact failure this project exists to prevent. A list has no
    shared context, so each entity in one needs its own.
    """
    found = []
    for path in example_files(package):
        try:
            with open(path, encoding='utf-8') as handle:
                document = json.load(handle)
        except Exception:                          # noqa: BLE001
            continue
        shared = isinstance(document, dict) and '@context' in document
        entities = document if isinstance(document, list) else [document]
        for position, entity in enumerate(entities):
            if not isinstance(entity, dict) or shared:
                continue
            if '@context' in entity:
                continue
            identifier = str(entity.get('id') or entity.get('@id')
                             or f'entity {position}')
            line = dict(_entity_lines(path)).get(identifier, 1)
            found.append(Finding(
                entity=identifier, severity='error', kind='no-context',
                places=[(path, line)],
                message=(
                    f'{identifier} in {os.path.basename(path)} has no '
                    '@context, so `id` and `type` are ordinary keys: it expands '
                    'to a blank node, no sh:targetClass matches it, and the '
                    'case validates nothing while passing. Add the package\'s '
                    'published context URL, as the other examples do.')))
    return found


def _references(path):
    """[(target id, line)] for every relationship object in a document."""
    from ..cooked.jsonloc import locate

    try:
        with open(path, encoding='utf-8') as handle:
            raw = handle.read()
        document = json.loads(raw)
    except Exception:                              # noqa: BLE001
        return []
    try:
        index = locate(raw)
    except Exception:                              # noqa: BLE001
        index = {}

    out = []

    def walk(value, trail):
        if isinstance(value, dict):
            target = value.get('object')
            if isinstance(target, str):
                out.append((target, index.get(tuple(trail + ['object']))
                            or index.get(tuple(trail)) or 1))
            elif isinstance(target, dict) and isinstance(target.get('@id'), str):
                out.append((target['@id'],
                            index.get(tuple(trail + ['object'])) or 1))
            for key, item in value.items():
                walk(item, trail + [key])
        elif isinstance(value, list):
            for position, item in enumerate(value):
                walk(item, trail + [position])

    entities = document if isinstance(document, list) else [document]
    for position, entity in enumerate(entities):
        if isinstance(entity, dict):
            walk(entity, [position])
    return out


def dangling_references(package, expectations=None):
    """Relationships pointing at an entity no file in the case defines.

    A Relationship's object is an entity id, and in a case the composition is
    the whole world: if nothing in it defines the target, every constraint about
    that target -- its class, its attributes -- has nothing to check. The case
    keeps passing, which is the failure this tool exists to catch.

    It is also what a half-finished rename looks like: change an id in a
    subobject and the filters that point at it go nowhere, with the verdict
    moving somewhere unrelated.
    """
    expectations = expectations if expectations is not None \
        else load_expectations(package.path)

    groups = _case_groups(package, expectations)
    model = package.sources.get('model')
    if model and os.path.exists(model):
        groups.setdefault(os.path.basename(model),
                          {os.path.abspath(model)})

    found = []
    for case, members in groups.items():
        defined = set()
        for path in members:
            defined |= {identifier for identifier, _ in _entity_lines(path)}
        for path in sorted(members):
            for target, line in _references(path):
                if target in defined or not target.startswith('urn:'):
                    continue
                where = os.path.relpath(path, package.path)
                found.append(Finding(
                    entity=target, severity='error', kind='dangling',
                    places=[(path, line)],
                    message=(
                        f'{target} is referenced at {where}:{line}, and nothing '
                        f'composed into the case {case} defines it '
                        f'({len(members)} file(s)). Nothing about the target '
                        'can be checked, so the case passes having tested less '
                        'than it says. Include the file that defines it, or fix '
                        'the reference -- a half-finished rename leaves exactly '
                        'this behind.')))
    return found
