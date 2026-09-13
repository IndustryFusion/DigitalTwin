"""What an editor shows, computed without any LSP types in sight.

Keeping this layer protocol-free is the point of architecture.md section 8.4:
the VS Code layer must not become the semantic engine. Everything here is
testable without starting a server, and the LSP module below is a thin
translation into protocol objects.

Four kinds of finding reach the editor, and the third is the one that does not
exist in an ordinary linter:

  * capability   -- this shape cannot be compiled by the target
  * view         -- this shape aggregates but reads the current view
  * unexercised  -- no example proves this constraint can fire
  * fires        -- this constraint currently fires, and on what

`unexercised` is the dead-shape warning. A constraint that can never match
produces exactly what a satisfied one produces, so the only signal available is
that no example has ever made it fire -- and an editor is where an author will
actually notice it.
"""

import os
from dataclasses import dataclass

from ..expect import coverage
from ..expect.runner import constraint_ref
from ..expect.store import Example
from ..package import load
from ..provenance import build_provenance
from ..rdfio import index_file
from ..target import builtin_profile, check_package
from ..validate import validate_package
from ..validate.normalise import curie, local
from ..validate.shapes import check_declarations, node_shapes

ARTIFACTS = ('knowledge.ttl', 'shacl.ttl', 'model-instance.jsonld')
# Each role may also be a directory of documents, so a directory holding
# `shacl/` and `knowledge/` and `model-instance/` is a package too. Recognising
# only the files would leave such a package invisible to the editor -- the
# trees empty, with the loader perfectly able to read it.
ALTERNATIVES = {
    'knowledge.ttl': ('knowledge',),
    'shacl.ttl': ('shacl', 'shapes'),
    'model-instance.jsonld': ('model-instance', 'model'),
}


def _has_role(directory, name):
    if os.path.isfile(os.path.join(directory, name)):
        return True
    return any(os.path.isdir(os.path.join(directory, folder))
               for folder in ALTERNATIVES.get(name, ()))


@dataclass(frozen=True)
class EditorFinding:
    line: int                 # 1-based
    severity: str             # error | warning | info | hint
    kind: str                 # capability | view | unexercised | fires | identity
    message: str
    subject: str = ''


def package_root(path):
    """The package directory containing this file, or None.

    Walks up so that opening any artifact of a package activates the service --
    an editor gives you a file, not a project.
    """
    here = os.path.abspath(path)
    if os.path.isfile(here):
        here = os.path.dirname(here)
    while True:
        if all(_has_role(here, name) for name in ARTIFACTS):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def analyse(root, profile_name='shacl2flink'):
    """Findings for a package, keyed by absolute file path.

    Returns (findings, package). A finding about a shape lands on the file that
    DECLARES that shape -- the role may be a directory, and putting every
    finding on the first file would annotate a document that has nothing to do
    with it. A violation is attributed to the shape that raised it rather than
    to the data, so the author sees it against the constraint they are editing.
    """
    package = load(root)
    index = package.index('shapes')
    findings = {os.path.abspath(path): [] for path in index.paths}
    primary = os.path.abspath(package.sources['shapes'])

    def at(subject, severity, kind, message):
        path, block = index.block_for(subject)
        where = os.path.abspath(path) if path else primary
        findings.setdefault(where, []).append(EditorFinding(
            line=block.start_line if block else 1,
            severity=severity, kind=kind, message=message,
            subject=str(subject)))

    for diagnostic in check_declarations(package.shapes):
        at(diagnostic.subject, 'error', 'view', diagnostic.message)

    for diagnostic in check_package(package, builtin_profile(profile_name), index):
        at(diagnostic.subject, 'error', 'capability', diagnostic.message)

    # Who is who across the examples. These land on the .jsonld file and line
    # where the entity is defined -- the shapes file has nothing to do with it,
    # and a locator for JSON exists now.
    from ..expect.identity import (dangling_references, duplicate_ids,
                                   missing_context)

    try:
        for duplicate in (list(missing_context(package))
                          + list(dangling_references(package))
                          + duplicate_ids(package)):
            for where, line in duplicate.places:
                findings.setdefault(os.path.abspath(where), []).append(
                    EditorFinding(line=line, severity=duplicate.severity,
                                  kind='identity', message=duplicate.message,
                                  subject=duplicate.entity))
    except Exception:                              # noqa: BLE001
        pass            # a malformed example is the validator's story to tell

    report = validate_package(package, strict=False)

    fires = {}
    for result in report.violations:
        fires.setdefault(result.shape, []).append(result)
    for shape, results in fires.items():
        resources = sorted({r.resource for r in results})
        at(shape, 'warning', 'fires',
           f'{len(results)} violation(s) here: '
           + ', '.join(f'{r.component}({r.attribute}) on {r.resource}'
                       for r in results[:3])
           + (f' and {len(results) - 3} more' if len(results) > 3 else '')
           + f'  [{len(resources)} entity/entities]')

    entries = coverage([(Example(path=os.path.basename(package.sources['model'])),
                         report)])
    by_shape = {}
    for result in report.results:
        by_shape.setdefault(constraint_ref(result), result.shape)
    # Aggregated per shape on purpose. Reported one-per-constraint, a package
    # with a single example produces a finding on nearly every line, and a
    # warning nobody can read is a warning nobody acts on.
    unexercised = {}
    for entry in entries:
        if entry.has_firing:
            continue
        shape = by_shape.get(entry.constraint)
        if shape:
            unexercised.setdefault(shape, []).append(entry.constraint)
    for shape, constraints in unexercised.items():
        listed = ', '.join(c.split('/', 1)[-1] for c in sorted(constraints)[:3])
        more = f' and {len(constraints) - 3} more' if len(constraints) > 3 else ''
        at(shape, 'information', 'unexercised',
           f'{len(constraints)} constraint(s) here have no example that makes '
           f'them fire ({listed}{more}). A constraint that cannot fire looks '
           f'exactly like one that is satisfied, so only a violating example '
           f'tells them apart.')
    return findings, package


def hover_at(package, word):
    """Markdown describing the shape or property named at the cursor."""
    if not word:
        return ''
    provenance = build_provenance(package)
    for shape in node_shapes(package.shapes):
        if local(shape) != word and curie(package.shapes, shape) != word:
            continue
        origin = provenance.of(shape)
        lines = [f'### {curie(package.shapes, shape)}', '']
        if origin:
            lines += [f'- origin: `{origin.kind}` (tier: {origin.tier})',
                      f'- declared: `{origin.locator}`']
        targets = [local(t) for t in package.shapes.objects(shape, None)
                   if str(t).endswith(('Cutter', 'Filter', 'Machine',
                                       'Workpiece', 'FilterCartridge'))]
        if targets:
            lines.append(f'- targets: {", ".join(sorted(set(targets)))}')
        return '\n'.join(lines)

    for subject in set(package.knowledge.subjects(None, None)):
        if local(subject) == word:
            types = sorted({local(o) for o in package.knowledge.objects(
                subject, None)})[:6]
            return (f'### {curie(package.knowledge, subject)}\n\n'
                    f'declared in the ontology'
                    + (f'\n\n- {", ".join(types)}' if types else ''))
    return ''


def definition_at(package, word):
    """(file, line) where the named thing is declared, or None.

    The high-value navigation is cross-artifact: from `sh:path
    iffBaseEntities:hasStrength` in shacl.ttl to the owl:ObjectProperty that
    declares it in knowledge.ttl. Nothing else in the toolchain can follow that
    link, because the two files are only related through the graph.
    """
    if not word:
        return None
    for role in ('shapes', 'knowledge'):
        for path in package.files(role):
            index = index_file(path)
            for block in index.blocks:
                if local(block.subject) == word or block.raw_subject == word:
                    return os.path.abspath(path), block.start_line
    return None
