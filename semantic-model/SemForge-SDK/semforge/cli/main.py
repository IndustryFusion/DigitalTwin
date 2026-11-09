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

"""semforge command line.

Exit codes are the CI contract:
  0 conformant   1 violations   2 package invalid   3 internal
"""

import os
import sys

import click

from .. import __version__
from ..errors import CapabilityError, PackageError
from ..expect import (coverage, load_expectations, run_tests,
                      save_expectations)
from ..expect.store import Example, examples_root
from ..package import load
from ..package.archive import (PackageInvalid, is_archive, pack as pack_archive,
                               verify as verify_archive, verify_directory)
from ..package.discover import describe
from ..provenance import build_provenance
from ..sanity import known_constraints
from ..target import EmissionMode, builtin_profile, check_package, export as export_package
from ..target.crosscheck import cross_check
from ..importers import (import_json_schema, import_ontology, observe_examples,
                         save_proposal)
from ..diff import semantic_diff
from ..diff.model import format_changes
from ..diff.impact import format_regression, regression_report
from ..validate import validate_package
from ..validate.orchestrator import validate_graphs


class PackageArgument(click.Path):
    """A path that resolves to the package it lies in.

    `cargo`, `npm` and `git` all let you stand anywhere inside a project.
    SemForge did not: it read the given directory and only that one, so running
    a command one level inside a package reported all three roles missing, and
    running it one level above reported the same. Both are the normal place to
    be standing, and the error told you nothing about where to stand instead.
    """

    name = 'package'

    def __init__(self, *args, writes=False, **kwargs):
        super().__init__(*args, **kwargs)
        # A command that changes the package cannot take an archive: its
        # tree is a verified, throw-away extraction, and an edit to it would
        # be lost without a word.
        self.writes = writes

    def convert(self, value, param, ctx):
        given = super().convert(value, param, ctx)
        if is_archive(given):
            if self.writes:
                self.fail(f'{given} is a packed package, and a packed package '
                          f'is read-only. Unpack it, or run this on the '
                          f'directory it was packed from.', param, ctx)
            tree = open_archive(given, lambda message: self.fail(message, param, ctx))
            click.echo(f'package: {given}  (verified archive, read-only)', err=True)
            return tree
        found, why, _ = describe(given)
        if found is None:
            self.fail('package error: ' + why, param, ctx)
        # Say which package was resolved, on stderr so that piping a report
        # stays a report. This one line is the answer to "which directory does
        # this apply to?", and you are usually not standing in it.
        click.echo(f'package: {found}  ({why})', err=True)
        return found


PACKAGE = PackageArgument(exists=True)
PACKAGE_RW = PackageArgument(exists=True, writes=True)

# The extracted trees of archives given on this command line: read-only.
ARCHIVE_TREES = set()


def open_archive(path, fail):
    """Verify an archive and return its extracted tree, removed at exit.

    Nothing of an archive is used before all of it verified: `fail` is called
    with every problem otherwise, and the tree never exists."""
    import atexit
    import shutil
    import tempfile

    holder = tempfile.mkdtemp(prefix='semforge-archive-')
    atexit.register(shutil.rmtree, holder, True)
    result = verify_archive(path, into=os.path.join(holder, 'package'))
    if not result.ok:
        fail('archive does not verify:\n' +
             '\n'.join(f'  {problem}' for problem in result.problems))
    ARCHIVE_TREES.add(result.tree)
    return result.tree


@click.group()
@click.version_option(__version__)
def cli():
    """SemForge: offline authoring and validation of semantic packages."""


@cli.command()
@click.argument('path', type=PACKAGE, default='.')
@click.option('--no-strict', is_flag=True,
              help='report view-declaration problems instead of failing on them')
@click.option('--cross-check', type=click.Choice(['sqlite']), default=None,
              help='additionally run the compiled SQLite build and compare')
@click.option('--shacl2flink', type=click.Path(), default=None,
              help='path to the shacl2flink checkout (for --cross-check)')
def validate(path, no_strict, cross_check, shacl2flink):
    """Validate a package's examples against its shapes."""
    try:
        package = load(path)
        report = validate_package(package, strict=not no_strict)
    except PackageError as exc:
        click.echo(f'package error: {exc}', err=True)
        sys.exit(2)
    except CapabilityError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    for stats in report.view_stats:
        detail = [f'view={stats.view.value}']
        if stats.collapsed:
            detail.append(f'collapsed={stats.collapsed} attribute instances')
        if stats.empty_lists:
            detail.append(f'empty-lists={stats.empty_lists}')
        click.echo('  '.join(detail))

    for result in sorted(report.violations, key=lambda r: r.key()):
        click.echo(f'{result.severity:>9}  {result.resource}  '
                   f'{result.component}({result.attribute})  [{result.shape_name}]')

    if cross_check:
        # A courtesy check. Its findings are bug reports for the compiler, and
        # they never block a package whose pyshacl verdict is clean.
        target = shacl2flink or _default_shacl2flink(path)
        divergences = cross_check_sqlite(package, report, target)
        click.echo(f'\ncross-check against {target or "(not found)"}')
        for diagnostic in divergences:
            click.echo(f'  {diagnostic}')
        if not divergences:
            click.echo('  cross-check: the compiled SQL agrees with pyshacl')

    count = len(report.violations)
    click.echo(f'\n{len(report.evaluated)} constraints evaluated, '
               f'{count} violation{"" if count == 1 else "s"}')
    if not report.complete:
        # V1: a report that cannot account for every applicable constraint must
        # say so. Silence is never success.
        for diagnostic in report.diagnostics:
            click.echo(f'  {diagnostic}', err=True)
        click.echo('note: this report is INCOMPLETE -- conformance cannot be '
                   'trusted for the shapes above.', err=True)
    sys.exit(1 if count else 0)


def _default_shacl2flink(package_path):
    """Look for a sibling shacl2flink checkout, walking up from the package."""
    here = os.path.abspath(package_path)
    while here != os.path.dirname(here):
        candidate = os.path.join(here, 'shacl2flink')
        if os.path.isdir(candidate):
            return candidate
        here = os.path.dirname(here)
    return ''


def cross_check_sqlite(package, report, shacl2flink_dir):
    return cross_check(package, report, shacl2flink_dir, python_exe=sys.executable)


@cli.command('export')
@click.argument('path', type=PACKAGE, default='.')
@click.option('-o', '--out', 'out_dir', required=True, type=click.Path(),
              help='directory to write the KMS triple into')
@click.option('--target', type=click.Choice(['kms']), default='kms')
@click.option('--mode', type=click.Choice([m.value for m in EmissionMode]),
              default=EmissionMode.COMPILE.value,
              help='compile keeps the observation stream; broker collapses to the latest')
@click.option('--profile', 'profile_name', default='shacl2flink',
              help='target profile to check against before exporting')
@click.option('--no-check', is_flag=True, help='skip the capability check')
def export_command(path, out_dir, target, mode, profile_name, no_check):
    """Export a package as the KMS triple, after checking it compiles.

    The capability check runs FIRST, so a shape the target cannot express is a
    diagnostic with a file and a line rather than a stack trace from the
    compiler -- and nothing is written until the package passes.
    """
    try:
        package = load(path)
    except PackageError as exc:
        click.echo(f'package error: {exc}', err=True)
        sys.exit(2)

    if not no_check:
        problems = check_package(package, builtin_profile(profile_name))
        if problems:
            click.echo('ERROR: the following shapes cannot be compiled by the '
                       f'{profile_name} profile and would be silently '
                       'unvalidated:', err=True)
            for diagnostic in problems:
                click.echo(f'  - {diagnostic}', err=True)
            sys.exit(2)

    # Readiness is checked BEFORE writing. A term the published context does
    # not declare exports as a value that will not expand, and the moment to
    # say so is now -- not when a broker rejects it.
    from ..package.context import check_export_readiness

    readiness = check_export_readiness(
        package, cache_dir=os.path.join(path, '.semforge', 'cache', 'contexts'))
    blocking = [d for d in readiness if d.severity == 'error']
    for diagnostic in readiness:
        click.echo(f'  {diagnostic}', err=diagnostic.severity == 'error')
    if blocking:
        click.echo('\nERROR: the published context must be updated before this '
                   'package can be exported. Nothing was written.', err=True)
        sys.exit(2)

    from ..target.export import AmbiguousInstances

    try:
        written = export_package(package, out_dir, EmissionMode(mode))
    except AmbiguousInstances as exc:
        click.echo(f'ERROR: {exc} Nothing was written.', err=True)
        sys.exit(2)
    for role in ('knowledge', 'shapes', 'model', 'context'):
        if role in written:
            click.echo(f'{role:>10}  {written[role]}')
    if written.get('context_url'):
        click.echo(f'{"@context":>10}  {written["context_url"]} '
                   f'({written.get("retargeted", 0)} entity/entities retargeted)')
    for place in written.get('node_kinds_where', []):
        click.echo(f'{"nodeKind":>10}  sh:BlankNode added: {place}')
    if written.get('collapsed'):
        click.echo(f'{"collapsed":>10}  {written["collapsed"]} attribute '
                   f'instance(s) to the latest observedAt')


def _examples_and_reports(package, expectations):
    """Every declared example paired with its report.

    A package with no expectation file is still testable: its own model is the
    single example, so `semforge test` works before anything is declared.
    """
    if not expectations.examples:
        # No declared cases: the model documents ARE the examples, one each.
        report = validate_package(package)
        return [(Example(path=os.path.relpath(document, package.path)), report)
                for document in package.files('model')]

    from ..expect.store import compose

    paired = []
    for example in expectations.examples:
        graph = compose(package, example)
        paired.append((example, validate_graphs(
            graph, package.shapes, package.knowledge, strict=False)))
    return paired


@cli.command('new')
@click.argument('name')
@click.option('--in', 'parent', type=click.Path(), default='.',
              help='where to create the project directory')
@click.option('--namespace',
              help='base IRI for this package, e.g. https://example.org/plant/')
@click.option('--layout', type=click.Choice(['grouped', 'flat']),
              default='grouped', show_default=True)
@click.pass_context
def new_command(ctx, name, parent, namespace, layout):
    """Create a project DIRECTORY and scaffold a package in it.

    The classical gesture: `semforge new plant-line` makes ./plant-line. To
    scaffold a directory you already have, use `semforge init`.
    """
    import re

    slug = re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-').lower()
    if not slug:
        click.echo('a name needs letters or digits in it', err=True)
        sys.exit(2)
    directory = os.path.join(parent, slug)
    if os.path.isdir(directory) and os.listdir(directory):
        click.echo(f'{directory} already exists and is not empty', err=True)
        sys.exit(2)
    ctx.invoke(init_command, path=directory, name=name, namespace=namespace,
               published=None, layout=layout)


@cli.command('init')
@click.argument('path', type=click.Path(), default='.')
@click.option('--name', help='the package name; defaults to the directory name')
@click.option('--namespace',
              help='base IRI for this package, e.g. https://example.org/plant/')
@click.option('--published',
              help='where the context will be published; defaults to '
                   '<namespace>context.jsonld')
@click.option('--layout', type=click.Choice(['grouped', 'flat']),
              default='grouped', show_default=True,
              help='grouped puts the instance and examples under model/')
def init_command(path, name, namespace, published, layout):
    """Create a package that already works.

    Not three empty files: a package that loads, validates clean, and has an
    example on each side of one constraint -- which is the shape every later
    addition copies.
    """
    from ..package.scaffold import create_package

    os.makedirs(path, exist_ok=True)
    try:
        written = create_package(path, name=name, namespace=namespace,
                                 published=published, layout=layout)
    except PackageError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    for created in written:
        click.echo(f'  {os.path.relpath(created, path)}')

    # Prove it rather than claim it: a scaffold that does not pass its own
    # checks is worse than none, because the first run blames the author.
    try:
        package = load(path)
        report = validate_package(package, strict=False)
    except (PackageError, CapabilityError) as exc:
        click.echo(f'\nwritten, but it does not load: {exc}', err=True)
        sys.exit(2)

    click.echo(f'\n{len(written)} file(s) in {os.path.abspath(path)}')
    click.echo(f'{len(report.results)} constraint(s) evaluated, '
               f'{len(report.violations)} violation(s)')
    click.echo('\nNext:')
    click.echo(f'  semforge test {path}             the declared cases')
    click.echo(f'  semforge test {path} --coverage  what no example makes fire')
    click.echo('  open the folder in VS Code for the Constraints, Model and '
               'Knowledge views')


@cli.command('check')
@click.argument('path', type=PACKAGE, default='.')
@click.option('--strict', is_flag=True,
              help='fail on warnings too, not only on errors')
def check_command(path, strict):
    """References that point at nothing, and declarations nothing uses.

    The cross-artifact sanity check the editor shows in its Problems panel,
    for a terminal or CI: a sh:path or a query naming an attribute the
    knowledge no longer declares, a data key no knowledge file declares, an
    expectation on a constraint no shape has, a class nothing declares, a
    declared attribute nothing uses. Exits 1 when anything is an error (with
    --strict, a warning), so a broken link cannot be merged unnoticed.
    """
    from ..expect.vocabulary import undeclared_attributes
    from ..sanity import sanity

    try:
        package = load(path)
    except (PackageError, CapabilityError) as exc:
        click.echo(f'error: {exc}', err=True)
        sys.exit(2)

    rows = [(f.file, f.line, f.severity, f.code, f.message)
            for f in sanity(package)]
    for entry in undeclared_attributes(package):
        for where, line in entry.places:
            rows.append((os.path.abspath(where), line, entry.severity,
                         'undeclared-key', entry.message))

    order = {'error': 0, 'warning': 1}
    rows.sort(key=lambda r: (r[0], r[1], order.get(r[2], 2)))
    for file, line, severity, code, message in rows:
        click.echo(f'{os.path.relpath(file, package.path)}:{line}  '
                   f'{severity:<11} {code:<18} {message}')

    errors = sum(1 for r in rows if r[2] == 'error')
    warnings = sum(1 for r in rows if r[2] == 'warning')
    others = len(rows) - errors - warnings
    click.echo(f'\n{errors} error(s), {warnings} warning(s), {others} note(s)'
               + ('' if rows else ' -- every reference resolves'))
    if errors or (strict and warnings):
        sys.exit(1)


def _problems(problems):
    for problem in problems:
        click.echo(f'  {problem}', err=True)


@cli.command('pack')
@click.argument('path', type=PACKAGE, default='.')
@click.option('--output', '-o', type=click.Path(dir_okay=False), default=None,
              help='archive to write (default: <name>-<version>.kms.zip here)')
@click.option('--store', is_flag=True,
              help='do not compress; the digest is the same either way')
def pack_command(path, output, store):
    """Pack a package into its distribution form: a .kms.zip with SHA256SUMS.

    The package must satisfy the KMS package contract; files under it that are
    not members are listed and left out, so nothing is shipped by accident.
    """
    try:
        packed = pack_archive(path, output=output, compress=not store)
    except PackageInvalid as exc:
        click.echo('package does not conform; nothing written:', err=True)
        _problems(exc.problems)
        sys.exit(2)
    for left in packed.left_out:
        click.echo(f'left out  {left}', err=True)
    click.echo(f'packed   {packed.path}')
    click.echo(f'name     {packed.name} {packed.version}')
    click.echo(f'members  {len(packed.members)}')
    click.echo(f'digest   {packed.digest}')


@cli.command('verify')
@click.argument('target', type=click.Path(exists=True))
@click.option('--tests', 'with_tests', is_flag=True,
              help='also run the examples and measure coverage')
@click.option('--record', type=click.Path(exists=True, dir_okay=False), default=None,
              help='release record to compare an archive\'s tests with')
@click.option('--format', 'fmt', type=click.Choice(['text', 'json']),
              default='text')
def verify_command(target, with_tests, record, fmt):
    """Verify a package directory or archive against the KMS package contract.

    For an archive: every entry against SHA256SUMS, safe paths and sizes, then
    the extracted tree as a package. For a directory: the package check, the
    published-version rule, and the digest its archive would have. With
    --tests, the examples run too, and the result is compared with a release
    record when one is available. Exit 0 when it holds, 2 otherwise.

    Running the tests is not a sandbox: SPARQL constraints may contact
    services (SERVICE) and JSON-LD contexts may be fetched. Verify an
    untrusted archive without --tests, or run its tests where that is safe.
    """
    import shutil
    import tempfile

    from ..package.releases import compare_with_record, record_path, run_tests

    holder = None
    if is_archive(target):
        if with_tests:
            holder = tempfile.mkdtemp(prefix='semforge-verify-')
            result = verify_archive(target, into=os.path.join(holder, 'package'))
        else:
            result = verify_archive(target)
        tree = result.tree
    elif os.path.isdir(target):
        result = verify_directory(target)
        tree = result.source
        if record is None and os.path.isfile(record_path(tree)):
            record = record_path(tree)
    else:
        click.echo(f'{target} is neither a package directory nor a .zip', err=True)
        sys.exit(2)

    run, compared = None, ''
    try:
        if with_tests and result.ok:
            try:
                run = run_tests(tree)
            except (PackageError, CapabilityError) as exc:
                from ..package.conformance import Problem
                result.problems.append(Problem('', f'tests do not run: {exc}'))
            else:
                problems, compared = compare_with_record(run, result, record)
                result.problems.extend(problems)
            result.ok = not result.problems
    finally:
        if holder:
            shutil.rmtree(holder, ignore_errors=True)

    if fmt == 'json':
        import json
        out = result.as_dict()
        if run is not None:
            out['tests'] = run.as_dict()
            out['record'] = compared
        click.echo(json.dumps(out, indent=2))
    else:
        if result.ok:
            click.echo(f'verified {result.source}')
            click.echo(f'name     {result.name} {result.version}')
            click.echo(f'digest   {result.digest}')
        else:
            click.echo(f'does not verify: {result.source}', err=True)
            _problems(result.problems)
        if run is not None:
            click.echo(f'examples {run.met} of {run.examples} meet their expectations')
            click.echo(f'coverage {run.coverage:g} % of {len(run.constraints)} '
                       f'constraints (threshold {run.threshold:g} %)')
            click.echo(f'record   {compared}')
    sys.exit(0 if result.ok else 2)


@cli.command('publish')
@click.argument('path', type=PACKAGE_RW, default='.')
@click.option('--output', '-o', type=click.Path(dir_okay=False), default=None,
              help='archive to write (default: <name>-<version>.kms.zip here)')
def publish_command(path, output):
    """Publish the current version: test it, pack it and record it.

    Every example must meet its expectations and the coverage must reach the
    package's threshold (tests.coverage, default 80 %). Nothing is written or
    recorded otherwise. The version is then immutable.
    """
    from ..package.releases import PublishRefused, publish

    try:
        published = publish(path, output=output)
    except PublishRefused as exc:
        click.echo('not published; nothing written:', err=True)
        _problems(exc.problems)
        if exc.run is not None and exc.run.uncovered:
            click.echo('not covered:', err=True)
            for constraint in exc.run.uncovered:
                click.echo(f'  {constraint}', err=True)
        sys.exit(2)
    click.echo(f'packed   {published.path}')
    click.echo(f'name     {published.name} {published.version}')
    click.echo(f'digest   {published.digest}')
    if published.unchanged:
        click.echo('already published; the record is unchanged')
    else:
        run = published.run
        click.echo(f'examples {run.met} of {run.examples}')
        click.echo(f'coverage {run.coverage:g} % (threshold {run.threshold:g} %)')
        click.echo('recorded in .kms/releases.yaml')


@cli.command('version')
@click.argument('part', type=click.Choice(['patch', 'minor', 'major']))
@click.argument('path', type=PACKAGE_RW, default='.')
def version_command(part, path):
    """Raise the package's version: patch, minor or major."""
    from ..package.releases import raise_version

    try:
        old, new = raise_version(path, part)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)
    click.echo(f'version  {old} -> {new}')


@cli.command('packages')
@click.argument('directory', type=click.Path(exists=True, file_okay=False), default='.')
@click.option('--format', 'fmt', type=click.Choice(['text', 'json', 'paths']),
              default='text')
def packages_command(directory, fmt):
    """The packages in a directory of packages, such as semantic-model/kms.

    Each once; the one `default` links to is marked. `--format paths` prints
    one directory per line, for scripts.
    """
    from ..package.discover import packages_below

    found = packages_below(directory)
    if fmt == 'json':
        import json
        click.echo(json.dumps([{'name': n, 'path': p, 'default': d}
                               for n, p, d in found], indent=2))
    elif fmt == 'paths':
        for _, where_, _ in found:
            click.echo(where_)
    else:
        for name, where_, is_default in found:
            click.echo(f'{name:<24} {where_}{"  (default)" if is_default else ""}')
    if not found:
        click.echo(f'no packages in {directory}', err=True)


@cli.command('where')
@click.argument('path', type=click.Path(exists=True), default='.')
def where_command(path):
    """Which package applies here, and what it is made of.

    `git rev-parse --show-toplevel` for semantic packages. Every other command
    resolves the same way, so this is how you check what they will read before
    one of them writes something.
    """
    if is_archive(path):
        path = PACKAGE.convert(path, None, click.get_current_context())
    found, why, roles = describe(path)
    click.echo(f'here     {os.path.abspath(path)}')
    if found is None:
        click.echo(f'package  (none)\n\n{why}')
        sys.exit(2)
    from ..package import config

    declared = config.read(found)
    click.echo(f'package  {found}')
    click.echo(f'  name     {declared.get("name") or os.path.basename(found)}'
               f'{"" if declared.get("name") else "  (the directory name)"}')
    click.echo(f'  found by {why}')
    from ..package.releases import released
    version = declared.get('version')
    if version is not None:
        try:
            state = 'published' if released(found, version) else 'draft'
        except Exception:                          # noqa: BLE001 -- malformed record
            state = 'release record unreadable'
        click.echo(f'  version  {version}  ({state})')
    tests = declared.get('tests') if isinstance(declared.get('tests'), dict) else {}
    if tests.get('coverage') is not None:
        click.echo(f'  coverage threshold {tests["coverage"]} %')
    else:
        click.echo('  coverage threshold 80 %  (the default)')

    try:
        package = load(found)
    except (PackageError, CapabilityError) as exc:
        click.echo(f'\nit does not load: {exc}', err=True)
        sys.exit(2)

    for role, where_ in roles.items():
        files = package.files(role)
        listing = ', '.join(os.path.relpath(f, found) for f in files[:4])
        if len(files) > 4:
            listing += f', ... ({len(files)} files)'
        click.echo(f'  {role:<10} {where_ or "?":<22} {listing}')

    examples = examples_root(found)
    if examples and os.path.isdir(examples):
        cases = sorted(entry for entry in os.listdir(examples)
                       if os.path.isdir(os.path.join(examples, entry)))
        click.echo(f'  {"tests":<10} {os.path.relpath(examples, found) + os.sep:<22} '
                   f'{", ".join(cases) if cases else "(no cases)"}')


@cli.command()
@click.argument('path', type=PACKAGE, default='.')
@click.option('--coverage', 'want_coverage', is_flag=True,
              help='report which constraints are exercised, and on which side')
@click.option('--fail-on', type=click.Choice(['no-firing-example',
                                              'no-conforming-example']),
              help='treat that coverage status as a failure')
def test(path, want_coverage, fail_on):
    """Run a package's examples against its declared expectations."""
    try:
        package = load(path)
        expectations = load_expectations(path)
        paired = _examples_and_reports(package, expectations)
    except (PackageError, CapabilityError) as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    from ..expect.identity import (dangling_references, duplicate_ids,
                                   missing_context)

    duplicates = (missing_context(package)
                  + dangling_references(package, expectations)
                  + duplicate_ids(package, expectations))
    if duplicates:
        click.echo('Identity')
        for duplicate in duplicates:
            marker = '  !!  ' if duplicate.severity == 'error' else '  ..  '
            click.echo(f'{marker}{duplicate.entity}  [{duplicate.kind}]')
            click.echo(f'        {duplicate.message}')
        click.echo('')

    # An attribute the knowledge never declared. In a CASE that is an error:
    # no sh:path selects it, so the case proves nothing while passing. In the
    # scratchpad it is reported and left alone -- the scratchpad cannot fail.
    from ..expect.vocabulary import (undeclared_attributes,
                                     unknown_ngsild_terms)

    unknown = undeclared_attributes(package)
    if unknown:
        click.echo('Vocabulary')
        for entry in unknown:
            marker = '  !!  ' if entry.severity == 'error' else '  ..  '
            where = ', '.join(sorted({os.path.relpath(place, path)
                                      for place, _ in entry.places})[:3])
            click.echo(f'{marker}{entry.term}  [{where}]')
            click.echo(f'        {entry.message}')
        click.echo('')

    # And the encoding's own terms, judged by the same rule.
    strangers = unknown_ngsild_terms(package)
    if strangers:
        click.echo('NGSI-LD vocabulary')
        for entry in strangers:
            click.echo(f'  ..  ngsild:{entry.term}  [{", ".join(entry.where)}]')
            click.echo(f'        {entry.message}')
        click.echo('')

    failed = 0
    for outcome in run_tests(paired, known_constraints(package)):
        if outcome.passed:
            click.echo(f'ok    {outcome.example}')
            continue
        failed += 1
        click.echo(f'FAIL  {outcome.example}')
        for failure in outcome.failures:
            click.echo(f'        {failure}')

    if want_coverage:
        click.echo('\nCoverage')
        for entry in coverage(paired):
            marker = {'two-sided': '  ok  ', 'no-firing-example': '  !!  ',
                      'no-conforming-example': '  ..  '}[entry.status]
            click.echo(f'{marker}{entry.constraint}  [{entry.status}]')
        if fail_on:
            offenders = [e for e in coverage(paired) if e.status == fail_on]
            if offenders:
                click.echo(f'\n{len(offenders)} constraint(s) are {fail_on}', err=True)
                failed += len(offenders)

    # An id naming two entities inside one case, or an entity with no context,
    # is a broken test rather than a style question: the one merges two entities
    # into one, the other validates nothing while passing.
    broken = [d for d in duplicates if d.severity == 'error']
    if broken:
        click.echo(f'{len(broken)} id(s) name more than one entity in the same '
                   f'case', err=True)

    invisible = [entry for entry in unknown if entry.severity == 'error']
    if invisible:
        click.echo(f'{len(invisible)} attribute(s) used by a case are declared '
                   f'nowhere, so nothing constrains them', err=True)

    if want_coverage:
        _coverage_summary(path, package, expectations, paired, coverage(paired),
                          passed=not (failed or broken or invisible))

    sys.exit(1 if failed or broken or invisible else 0)


def _coverage_summary(path, package, expectations, paired, entries, passed):
    """The coverage `publish` gates on, and how the list above adds up to it.

    The list counts what some example evaluates and any firing; the contract
    counts every constraint, and a firing only where an example asserts it.
    Both are shown, reconciled, so nobody reads one as the other.
    """
    from ..package.conformance import check
    from ..package.releases import asserted_coverage

    constraints = known_constraints(package)
    declared = paired if expectations.examples else []   # the scratchpad is no test
    covered, unasserted = asserted_coverage(declared, constraints)
    evaluated = {entry.constraint for entry in entries} & constraints
    percent = 100.0 if not constraints else round(100.0 * len(covered) / len(constraints), 1)
    threshold = check(path, parse=False).coverage_threshold
    publishable = passed and percent >= threshold

    def fire(n):
        return f'{n} fire{"s" if n == 1 else ""}'

    unevaluated = len(constraints - evaluated)
    click.echo(f'\ncoverage {percent:g} % of {len(constraints)} constraints: '
               f'{fire(len(covered))} as asserted, {fire(len(unasserted))} without '
               f'an example asserting it, {unevaluated} '
               f'{"is" if unevaluated == 1 else "are"} evaluated by no example')
    click.echo(f'threshold {threshold:g} % -- '
               f'{"publishable" if publishable else "not publishable"}')


@cli.command('import')
@click.argument('source', type=click.Path(exists=True))
@click.option('--as', 'kind', type=click.Choice(['jsonschema', 'ontology']),
              required=True)
@click.option('--into', 'path', type=PACKAGE_RW, default='.')
@click.option('--namespace', required=True,
              help='namespace for the proposed classes and shapes')
def import_command(source, kind, path, namespace):
    """Import a schema or ontology as PROPOSED semantics.

    Nothing is added to the package. Importer output lands in .semforge/, which
    validation does not read, because an imported artifact is evidence -- it
    does not become a validation requirement until somebody says so.
    """
    proposal = (import_json_schema(source, namespace) if kind == 'jsonschema'
                else import_ontology(source, namespace))
    target = save_proposal(proposal, path)
    click.echo(f'{len(proposal)} proposal(s) written to {target}')
    click.echo('tier: proposed -- not loaded by validation, and not in shacl.ttl')
    for note in proposal.notes:
        click.echo(f'  note: {note}')
    click.echo('\nReview them, then add the ones you want to shacl.ttl.')


@cli.command('observe')
@click.argument('path', type=PACKAGE, default='.')
def observe_command(path):
    """Report the structure the examples contain, and propose nothing.

    Repeated observation is not a requirement. Four examples that all carry a
    serial number are four examples; whether it is required is a decision, and
    this is the evidence for making it.
    """
    try:
        package = load(path)
    except PackageError as exc:
        click.echo(f'package error: {exc}', err=True)
        sys.exit(2)

    observations, proposal = observe_examples([package.model], source=path)
    for (entity_type, attribute), record in sorted(observations.items()):
        types = ', '.join(sorted(record.datatypes)) or '-'
        click.echo(f'{entity_type:<16} {attribute:<22} '
                   f'on {len(record.entities)} entity/entities   {types}')
    click.echo(f'\n{len(observations)} observation(s), tier: observed. '
               f'Nothing here is a constraint.')


@cli.command('serve-context')
@click.argument('path', type=PACKAGE, default='.')
@click.option('--port', default=0, help='0 picks a free port')
def serve_context_command(path, port):
    """Serve the package's local context over HTTP.

    Loading inside the SDK does not need this -- it substitutes the local
    content in memory. It is for tools that insist on an http url.
    """
    from ..package.context import serve_local_context

    try:
        server = serve_local_context(path, port)
    except PackageError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)
    click.echo(f'serving {server.path}\n  at {server.url}\nCtrl-C to stop')
    try:
        while True:
            __import__('time').sleep(3600)
    except KeyboardInterrupt:
        server.stop()
        click.echo('stopped')


@cli.command('retarget')
@click.argument('path', type=PACKAGE_RW, default='.')
@click.option('--to', type=click.Choice(['local', 'published']), required=True)
def retarget_command(path, to):
    """Point a model instance's @context at the local file or the published url.

    Importing a model written elsewhere is the `local` case: until it names
    something this package can resolve, it is not part of the package.
    """
    from ..package.context import context_config, local_context_path, retarget_model

    try:
        package = load(path)
    except PackageError as exc:
        click.echo(f'package error: {exc}', err=True)
        sys.exit(2)

    config = context_config(path)
    if to == 'published':
        if not config.declared:
            click.echo('kms.yaml declares no published context', err=True)
            sys.exit(2)
        value = config.published
    else:
        local = local_context_path(path, config)
        if local is None:
            click.echo('the package has no local context', err=True)
            sys.exit(2)
        value = os.path.relpath(local, path)

    changed = sum(retarget_model(document, value)
                  for document in package.files('model'))
    click.echo(f'{changed} entity/entities now name {value}')


@cli.command('prefixes')
@click.argument('path', type=PACKAGE, default='.')
@click.option('--fix', is_flag=True, help='rewrite the artifacts to the agreed names')
@click.option('--define', 'definitions', multiple=True, metavar='PREFIX=IRI',
              help='define a name for the whole package, in kms.yaml')
def prefixes_command(path, fix, definitions):
    """Check that every namespace has one agreed name, and optionally align.

    The context is the source of truth: it is the artifact all three already
    share. kms.yaml `namespaces:` adds what the context does not declare
    and overrides it where the package has a reason to.
    """
    if (fix or definitions) and path in ARCHIVE_TREES:
        click.echo('a packed package is read-only; run this on its directory',
                   err=True)
        sys.exit(2)
    from ..package.prefixes import add_namespace, align, check

    for definition in definitions:
        name, _, namespace = definition.partition('=')
        try:
            made = add_namespace(path, name, namespace)
        except PackageError as exc:
            click.echo(f'{exc}', err=True)
            sys.exit(2)
        click.echo(f'defined {made["prefix"]}: {made["namespace"]}  '
                   f'({os.path.relpath(made["file"], path)}:{made["line"]})')

    try:
        package = load(path)
    except PackageError as exc:
        click.echo(f'package error: {exc}', err=True)
        sys.exit(2)

    if fix:
        applied = align(package)
        if not applied:
            click.echo('already aligned; nothing to rewrite')
        for role, renames in sorted(applied.items()):
            for old, new in sorted(renames.items()):
                click.echo(f'{role:>10}  {old or "(default)"}: -> {new}:')
        package = load(path)

    findings = check(package)
    for finding in findings:
        click.echo(f'{finding.code:<12} {finding.severity:<8} {finding.message}')
    errors = [f for f in findings if f.severity == 'error']
    if not findings:
        click.echo('every namespace has one agreed name across the package')
    sys.exit(1 if errors else 0)


@cli.command('resolve')
@click.argument('path', type=PACKAGE, default='.')
@click.option('--out', type=click.Path(), default=None,
              help='write the assembled knowledge file here')
@click.option('--require-pinned', is_flag=True,
              help='fail if any dependency declares no sha256')
def resolve_command(path, out, require_pinned):
    """Resolve declared dependencies and assemble knowledge reproducibly."""
    from ..package.registry import (assemble_knowledge,
                                    dependencies_from_config, resolve)
    from ruamel.yaml import YAML

    from ..package.config import path_for
    config_path = path_for(path)
    if not os.path.exists(config_path):
        click.echo(f'no kms.yaml in {path}; nothing to resolve', err=True)
        sys.exit(2)
    with open(config_path) as handle:
        config = YAML().load(handle) or {}

    try:
        resolution = resolve(dependencies_from_config(config), path,
                             allow_unpinned=not require_pinned)
    except PackageError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    for dependency in resolution.dependencies:
        pinned = 'pinned' if dependency.sha256 else 'UNPINNED'
        click.echo(f'{dependency.name:<24} {dependency.version or "-":<10} '
                   f'{pinned:<9} {resolution.hashes[dependency.name]}')
    if resolution.unpinned:
        click.echo(f'\n{len(resolution.unpinned)} dependency/dependencies have no '
                   f'sha256. The package cannot be reproduced from its own '
                   f'contents until they do.', err=True)
    if out:
        assemble_knowledge(resolution, out)
        click.echo(f'\nassembled -> {out}')


@cli.command('diff')
@click.argument('before', type=PACKAGE)
@click.argument('after', type=PACKAGE)
@click.option('--impact/--no-impact', default=True,
              help='also run the examples under both versions')
def diff_command(before, after, impact):
    """Compare two package versions at the semantic level.

    Reports classified model changes -- a constraint weakened, a datatype
    changed, a rule body edited -- and then what those did to the examples. A
    changed SPARQL body is reported as impact-unknown rather than guessed at;
    the example run is what settles it.
    """
    try:
        old = load(before)
        new = load(after)
    except PackageError as exc:
        click.echo(f'package error: {exc}', err=True)
        sys.exit(2)

    changes = semantic_diff(old.shapes, new.shapes)
    if not changes:
        click.echo('no semantic changes')
    else:
        click.echo(f'{len(changes)} semantic change(s)')
        for line in format_changes(changes, new.shapes):
            click.echo(f'  {line}')

    if not impact:
        sys.exit(0)

    report = regression_report(
        (old.model, old.shapes, old.knowledge),
        (new.model, new.shapes, new.knowledge),
        [(os.path.basename(document), new.model)
         for document in new.files('model')],
        changes=changes)
    lines = format_regression(report)
    if lines:
        click.echo('\nAffected examples')
        for line in lines:
            click.echo(line)
        # A weakening that changes behaviour is the case worth stopping for.
        weakened = [c for c in changes if c.direction.value == 'weakened']
        sys.exit(1 if weakened else 0)
    click.echo('\nno example changed behaviour')
    sys.exit(0)


@cli.command()
@click.argument('path', type=PACKAGE, default='.')
@click.argument('subject', required=False)
def explain(path, subject):
    """Say why a shape exists: where it came from, and what exercises it.

    Provenance answers the first half; coverage answers the second. Together
    they are what "why does this constraint exist" actually needs -- a
    declaration site, and the examples standing behind it.
    """
    try:
        package = load(path)
        provenance = build_provenance(package)
        expectations = load_expectations(path)
        paired = _examples_and_reports(package, expectations)
    except (PackageError, CapabilityError) as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    entries = {e.constraint: e for e in coverage(paired)}
    matched = False
    for origin in sorted(provenance.origins.values(), key=lambda o: o.subject):
        name = origin.subject.rsplit('/', 1)[-1].rsplit('#', 1)[-1]
        if subject and subject not in origin.subject:
            continue
        related = {ref: entry for ref, entry in entries.items()
                   if ref.split('/')[0].endswith(name)}
        if subject is None and not related:
            continue
        matched = True
        click.echo(f'{origin.subject}')
        click.echo(f'  origin    {origin.kind}  (tier: {origin.tier})')
        click.echo(f'  declared  {origin.locator or "unknown"}')
        for ref, entry in sorted(related.items()):
            click.echo(f'  {ref.split("/", 1)[-1]}')
            click.echo(f'      fires on     {entry.firing_examples or "-- nothing"}')
            click.echo(f'      conforms on  {entry.conforming_examples or "-- nothing"}')
            if not entry.has_firing:
                click.echo('      NOTE no example proves this can fire; it may be '
                           'unsatisfiable rather than satisfied')
        click.echo('')
    if not matched:
        click.echo(f'nothing known about {subject!r}', err=True)
        sys.exit(1)


@cli.command()
@click.argument('path', type=PACKAGE_RW, default='.')
def accept(path):
    """Record the current residue of every example as expected."""
    try:
        package = load(path)
        expectations = load_expectations(path)
        paired = _examples_and_reports(package, expectations)
    except (PackageError, CapabilityError) as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    changed = 0
    outcomes = {o.example: o for o in run_tests(paired, known_constraints(package))}
    for example, _ in paired:
        outcome = outcomes[example.path]
        if example.residue != outcome.residue:
            example.residue = outcome.residue
            changed += 1
    if not expectations.examples:
        expectations.examples = [example for example, _ in paired]
    save_expectations(expectations)
    click.echo(f'accepted residue for {changed} example(s) -> {expectations.path}')
