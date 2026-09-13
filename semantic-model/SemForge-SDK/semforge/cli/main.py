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
from ..expect.store import Example
from ..package import load
from ..provenance import build_provenance
from ..target import EmissionMode, builtin_profile, check_package, export as export_package
from ..target.crosscheck import cross_check
from ..importers import (import_json_schema, import_ontology, observe_examples,
                         save_proposal)
from ..diff import semantic_diff
from ..diff.model import format_changes
from ..diff.impact import format_regression, regression_report
from ..validate import validate_package
from ..validate.orchestrator import validate_graphs


@click.group()
@click.version_option(__version__)
def cli():
    """SemForge: offline authoring and validation of semantic packages."""


@cli.command()
@click.argument('path', type=click.Path(exists=True), default='.')
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
@click.argument('path', type=click.Path(exists=True), default='.')
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

    written = export_package(package, out_dir, EmissionMode(mode))
    for role in ('knowledge', 'shapes', 'model', 'context'):
        if role in written:
            click.echo(f'{role:>10}  {written[role]}')
    if written.get('context_url'):
        click.echo(f'{"@context":>10}  {written["context_url"]} '
                   f'({written.get("retargeted", 0)} entity/entities retargeted)')
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


@cli.command()
@click.argument('path', type=click.Path(exists=True), default='.')
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

    failed = 0
    for outcome in run_tests(paired):
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

    sys.exit(1 if failed or broken else 0)


@cli.command('import')
@click.argument('source', type=click.Path(exists=True))
@click.option('--as', 'kind', type=click.Choice(['jsonschema', 'ontology']),
              required=True)
@click.option('--into', 'path', type=click.Path(exists=True), default='.')
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
@click.argument('path', type=click.Path(exists=True), default='.')
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
@click.argument('path', type=click.Path(exists=True), default='.')
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
@click.argument('path', type=click.Path(exists=True), default='.')
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
            click.echo('semforge.yaml declares no published context', err=True)
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
@click.argument('path', type=click.Path(exists=True), default='.')
@click.option('--fix', is_flag=True, help='rewrite the artifacts to the agreed names')
def prefixes_command(path, fix):
    """Check that every namespace has one agreed name, and optionally align.

    The context is the source of truth: it is the artifact all three already
    share. semforge.yaml `namespaces:` adds what the context does not declare
    and overrides it where the package has a reason to.
    """
    from ..package.prefixes import align, check

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
@click.argument('path', type=click.Path(exists=True), default='.')
@click.option('--out', type=click.Path(), default=None,
              help='write the assembled knowledge file here')
@click.option('--require-pinned', is_flag=True,
              help='fail if any dependency declares no sha256')
def resolve_command(path, out, require_pinned):
    """Resolve declared dependencies and assemble knowledge reproducibly."""
    from ..package.registry import (assemble_knowledge,
                                    dependencies_from_config, resolve)
    from ruamel.yaml import YAML

    config_path = os.path.join(path, 'semforge.yaml')
    if not os.path.exists(config_path):
        click.echo(f'no semforge.yaml in {path}; nothing to resolve', err=True)
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
@click.argument('before', type=click.Path(exists=True))
@click.argument('after', type=click.Path(exists=True))
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
@click.argument('path', type=click.Path(exists=True), default='.')
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
@click.argument('path', type=click.Path(exists=True), default='.')
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
    outcomes = {o.example: o for o in run_tests(paired)}
    for example, _ in paired:
        outcome = outcomes[example.path]
        if example.residue != outcome.residue:
            example.residue = outcome.residue
            changed += 1
    if not expectations.examples:
        expectations.examples = [example for example, _ in paired]
    save_expectations(expectations)
    click.echo(f'accepted residue for {changed} example(s) -> {expectations.path}')
