"""The project itself, as a tree: what this package is and how it is set up.

The three views answer what the package SAYS -- its constraints, its data, its
vocabulary. None of them answered what the package IS. Two directories called
`test` are not the same project, and nothing on screen separated them: no
settings, no status, no way to change either.

So a fourth view, above the other three, holding the answers in one place:

  * which package, spelled out -- the name it declares, the path it is at, and
    why that directory counted as one;
  * its settings, each one editable in place, keeping the comments that say
    what it decides;
  * what it is made of -- which file or directory holds each role, how many
    documents, how many shapes, entities and cases.

Every row that names a place carries `file:line`, so clicking it opens the
line rather than the file.
"""

import os
from dataclasses import dataclass, field

from rdflib.namespace import RDF, SH

from ..expect.store import examples_root, load_expectations
from ..package import config, discover


@dataclass
class ProjectNode:
    # kind: group | setting | fact | entry
    kind: str
    label: str
    detail: str = ''
    value: str = ''
    key: str = ''              # the setting this row writes, when it writes one
    doc: str = ''              # what it decides
    editable: bool = False
    defined_at: str = ''       # file:line
    severity: str = ''
    children: list = field(default_factory=list)


def _at(path, line):
    return f'{path}:{line}' if path and line else ''


def _relative(package, path):
    try:
        return os.path.relpath(path, package.path)
    except ValueError:                             # different drive on Windows
        return path


def build_project(package):
    """The project card: identity, settings, contents."""
    return [_identity(package), _settings(package), _contents(package)]


def _identity(package):
    root = os.path.abspath(package.path)
    found, why, _ = discover.describe(root)
    manifest = config.path_for(root)
    declared = config.read(root)

    name = declared.get('name') or os.path.basename(root)
    rows = [
        ProjectNode(kind='setting', label='name', value=str(name),
                    key='name', editable=True,
                    doc=next(doc for key, _, doc in config.SPEC
                             if key == 'name'),
                    detail='' if declared.get('name')
                           else 'not declared — the directory name',
                    defined_at=_at(manifest, config.locate(root, 'name'))),
        ProjectNode(kind='fact', label='path', value=root,
                    detail='where it is on disk'),
        ProjectNode(kind='fact', label='recognised by', value=why or '—',
                    detail='what made this directory a package'),
        ProjectNode(
            kind='fact', label='manifest',
            value=config.CONFIG if os.path.isfile(manifest) else '(none)',
            detail='' if os.path.isfile(manifest)
                   else 'this package has no semforge.yaml — editing a '
                        'setting creates one',
            defined_at=_at(manifest, 1) if os.path.isfile(manifest) else ''),
    ]
    node = ProjectNode(kind='group', label='Project', detail=str(name))
    node.children = rows
    return node


def _settings(package):
    root = os.path.abspath(package.path)
    manifest = config.path_for(root)
    rows = []
    for setting in config.settings(root):
        if setting.key == 'name':
            continue                      # shown under Project, where it reads
        detail = setting.doc
        severity = ''
        if not setting.value:
            # Only where absence actually costs something. A missing published
            # context is not a style question: export cannot run without it.
            if setting.key == 'context.published':
                severity = 'warning'
                detail = 'not declared — `semforge export` has nowhere to ' \
                         'point the model. ' + setting.doc
            elif setting.default:
                detail = f'not declared — {setting.default} applies. {setting.doc}'
            else:
                detail = 'not declared. ' + setting.doc
        rows.append(ProjectNode(
            kind='setting', label=setting.label,
            value=setting.value or '—', key=setting.key,
            doc=setting.doc, editable=setting.editable, detail=detail,
            severity=severity,
            defined_at=_at(manifest, setting.line)))

    # Prefixes are a package-wide table, so what the artifacts say about it
    # belongs on the row that shows it -- not in a command nobody runs.
    trouble = _prefix_findings(package)

    for collection in config.collections(root):
        detail = collection.doc
        severity = ''
        if collection.key == 'namespaces' and trouble:
            severity = 'error' if any(f.severity == 'error' for f in trouble) \
                else 'warning'
            detail = f'{len(trouble)} disagreement(s) — ' + trouble[0].message
        group = ProjectNode(
            kind='namespaces' if collection.key == 'namespaces' else 'fact',
            label=collection.label,
            value=f'{len(collection.entries)}', doc=collection.doc,
            detail=detail, severity=severity,
            defined_at=_at(manifest, config.locate(root, collection.key)))
        group.children = [
            ProjectNode(kind='entry', label=name, value=value,
                        defined_at=_at(manifest, line))
            for name, value, line in collection.entries]
        rows.append(group)

    node = ProjectNode(kind='group', label='Settings',
                       detail=f'{config.CONFIG} — click the pencil to change one')
    node.children = rows
    return node


def _prefix_findings(package):
    """What the artifacts say about the package's namespace table."""
    from ..package.prefixes import check

    try:
        return check(package)
    except Exception:                              # noqa: BLE001
        return []                                  # `semforge prefixes` tells it better


def _contents(package):
    """What the package is made of, counted."""
    shapes = len(set(package.shapes.subjects(RDF.type, SH.NodeShape)))
    properties = len(list(package.shapes.triples((None, SH.property, None))))
    classes = len(set(package.knowledge.subjects(RDF.type, None)))
    entities = len(set(package.model.subjects(RDF.type, None)))

    rows = []
    for role, plural in (('knowledge', 'document'), ('shapes', 'document'),
                         ('model', 'document')):
        files = package.files(role)
        where = _relative(package, files[0]) if len(files) == 1 else \
            os.path.dirname(_relative(package, files[0])) + os.sep
        rows.append(ProjectNode(
            kind='fact', label=role, value=where,
            detail=f'{len(files)} {plural}{"" if len(files) == 1 else "s"}',
            defined_at=f'{files[0]}:1'))

    rows.append(ProjectNode(kind='fact', label='shapes declared',
                            value=str(shapes),
                            detail=f'{properties} property constraint(s)'))
    rows.append(ProjectNode(kind='fact', label='knowledge terms',
                            value=str(classes)))
    rows.append(ProjectNode(kind='fact', label='entities in the model',
                            value=str(entities)))

    # The suite's own count, not a directory listing: examples/ also holds
    # the shared subobjects, which are not cases.
    try:
        declared = load_expectations(package.path).examples
    except Exception:                              # noqa: BLE001
        declared = []                              # the Model view reports why
    suites = sorted({example.suite for example in declared if example.suite})
    where = examples_root(package.path)
    rows.append(ProjectNode(
        kind='fact', label='test cases', value=str(len(declared)),
        detail=f'{len(suites)} suite(s): {", ".join(suites)}' if suites
               else 'none — nothing proves a constraint can fire',
        severity='' if declared else 'warning',
        defined_at=f'{where}:1' if where and os.path.isdir(where) else ''))

    node = ProjectNode(kind='group', label='Contents',
                       detail=f'{shapes} shape(s) · {entities} entity(s) · '
                              f'{len(declared)} case(s)')
    node.children = rows
    return node
