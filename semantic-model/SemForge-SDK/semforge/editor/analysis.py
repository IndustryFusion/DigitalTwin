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
from ..package.discover import find
from ..provenance import build_provenance
from ..rdfio import index_file
from ..target import builtin_profile, check_package
from ..validate import validate_package
from ..validate.normalise import curie, local
from ..validate.shapes import check_declarations, node_shapes

# Which package a file belongs to is one question with one answer, and it lives
# in semforge.package.discover so that the editor, the CLI and CI cannot drift
# apart about it. This module used to keep a private copy of the role names --
# a third one, after the loader's and the extension's.


@dataclass(frozen=True)
class EditorFinding:
    line: int                 # 1-based
    severity: str             # error | warning | info | hint
    kind: str                 # capability | view | unexercised | fires |
    #                           violation | identity | vocabulary | prefix | sanity
    message: str
    subject: str = ''
    # What a quick fix needs: a stable code naming the kind of problem, and
    # the data to act on it (sanity.SanityFinding.fix). Empty for findings no
    # fix exists for.
    code: str = ''
    data: dict = None


def package_root(path):
    """The package directory containing this file, or None.

    Walks up so that opening any artifact of a package activates the service --
    an editor gives you a file, not a project. Same rule as the command line:
    see semforge.package.discover.
    """
    return find(path)[0]


def analyse(root, profile_name='shacl2flink', package=None, verdicts=None):
    """Findings for a package, keyed by absolute file path.

    Returns (findings, package). A finding about a shape lands on the file that
    DECLARES that shape -- the role may be a directory, and putting every
    finding on the first file would annotate a document that has nothing to do
    with it. A violation is attributed to the shape that raised it rather than
    to the data, so the author sees it against the constraint they are editing.

    `package` is the loaded package when the caller has one. `verdicts` as for
    build_type_page (cooked/typepage.py): with PENDING the findings that need
    a validation ("fires", "unexercised") are left out -- the editor publishes
    the rest at once and these when the background validation is done.
    """
    from ..cooked.typepage import PENDING

    package = package if package is not None else load(root)
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

    # An attribute the knowledge does not declare. Same silence as an
    # undeclared type, one level down: no sh:path selects it, so the constraint
    # that should have judged the value never fires.
    from ..expect.vocabulary import undeclared_attributes

    try:
        for entry in undeclared_attributes(package):
            for where, line in entry.places:
                findings.setdefault(os.path.abspath(where), []).append(
                    EditorFinding(line=line, severity=entry.severity,
                                  kind='vocabulary', message=entry.message,
                                  subject=entry.term))
    except Exception:                              # noqa: BLE001
        pass

    # The namespace table is package-wide, and a file that binds a name the
    # package has not defined has invented one: nothing else knows it, and a
    # term copied out of that file means nothing where it lands.
    from ..package.prefixes import PREFIX_LINE, check as check_prefixes

    try:
        said = set()           # the check repeats a finding per file it read
        for finding in check_prefixes(package):
            # On the files that bind the namespace, at that line -- not on
            # every file of the role: a knowledge directory of ten files made
            # one finding ten, and buried what else the panel had to say.
            places = []
            for role in sorted(set(finding.files)):
                for path in package.files(role):
                    if not finding.namespace:
                        continue
                    with open(path, encoding='utf-8') as handle:
                        text = handle.read()
                    for match in PREFIX_LINE.finditer(text):
                        if match.group(3) == finding.namespace:
                            places.append((path, text[:match.start()].count('\n') + 1))
                            break
            if not places:
                first = next((package.files(role)[0] for role in sorted(set(finding.files))
                              if package.files(role)), None)
                places = [(first, 1)] if first else []
            # Once, on the first file: a generator binds a namespace the same
            # way in every file it writes, and ten copies of one finding
            # buried the violations in the Problems panel.
            if places and (finding.message, places[0]) not in said:
                said.add((finding.message, places[0]))
                path, line = places[0]
                more = f' (the same in {len(places) - 1} other file(s))' if len(places) > 1 else ''
                findings.setdefault(os.path.abspath(path), []).append(
                    EditorFinding(line=line, severity=finding.severity,
                                  kind='prefix', message=finding.message + more,
                                  subject=finding.namespace))
    except Exception:                              # noqa: BLE001
        pass            # `semforge prefixes` tells this better than a squiggle

    # References that point at nothing, across artifacts: a sh:path or a
    # query naming an attribute the knowledge no longer declares, an assert on
    # a constraint no shape has, a declaration nothing uses. Each lands on the
    # line that holds it, with what its quick fix needs.
    from ..sanity import sanity

    for finding in sanity(package):
        findings.setdefault(finding.file, []).append(EditorFinding(
            line=finding.line, severity=finding.severity, kind='sanity',
            message=finding.message, subject=finding.subject,
            code=finding.code, data=dict(finding.fix, code=finding.code,
                                         subject=finding.subject)))

    # The vocabulary finding for an undeclared data key gets a quick fix too:
    # the same "Declare it" an undeclared sh:path has.
    for items in findings.values():
        for position, finding in enumerate(items):
            if finding.kind == 'vocabulary' and not finding.code:
                items[position] = EditorFinding(
                    line=finding.line, severity=finding.severity,
                    kind=finding.kind, message=finding.message,
                    subject=finding.subject, code='undeclared-key',
                    data={'code': 'undeclared-key', 'declare': finding.subject,
                          'subject': finding.subject})

    if verdicts is PENDING:
        return findings, package
    report = verdicts.model if verdicts is not None else validate_package(package, strict=False)

    # Each violation of the model where it is written: the row in the data,
    # which F8 steps to (the Main page shows it with its entity).
    from ..cooked.casepage import located_violations

    for found in located_violations(package, report):
        where = f' · {found["attribute"]}' if found['attribute'] else ''
        findings.setdefault(os.path.abspath(found['file']), []).append(EditorFinding(
            line=found['line'], severity='error', kind='violation',
            message=f'{found["entity"]}{where}: {found["text"]} ({found["shape"]})',
            subject=found['entity'], code='model-violation',
            data={'code': 'model-violation', 'subject': found['entity'],
                  'entity': found['entity'], 'attribute': found['attribute']}))

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
        # A hint: VS Code lists no hints in the Problems panel, where these
        # outnumbered the violations; the Health page counts them.
        at(shape, 'hint', 'unexercised',
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


def references_at(package, token, path=None, include_declaration=True):
    """Every place the term under the cursor is used, as editor References.

    `token` is the term as written, prefix included -- the local name alone
    cannot tell base_shacl:CartridgeShape from filter_shacl:CartridgeShape --
    and `path` is the file it was written in, whose prefixes or `@context`
    decide what it means.
    """
    from .references import iris_named, references_to

    found = references_to(package, iris_named(package, token, path))
    if include_declaration:
        return found
    return [reference for reference in found if not reference.declaration]
