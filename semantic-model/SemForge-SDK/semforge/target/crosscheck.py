"""The optional SQLite cross-check (architecture.md section 7.4).

pyshacl is the validator and its verdict is the answer. This runs the package
through shacl2flink's SQLite build as well and compares -- because the two
compile from one set of templates, so an offline SQLite run is cheap evidence
about what the deployed SQL does.

It is a courtesy check, and its findings belong to shacl2flink:

  * a disagreement is reported as `divergence`, never as a data violation;
  * it never blocks a package whose pyshacl verdict is clean;
  * CI may skip it entirely.

Making pyshacl agree with the compiled SQL is not SemForge's job. What this
gives is a place where a real compiler divergence becomes visible instead of
waiting to be discovered in production.

Needs shacl2flink's own dependencies (oxrdflib, Jinja2) and the sqlite3 CLI.
When they are absent the check reports UNAVAILABLE -- never a silent pass, for
the same reason a missing consistency checker degrades to "not checked".
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

from ..errors import Diagnostic
from .export import EmissionMode, export

BUILD_STEPS = (
    ('create_rdf_table.py', ('knowledge.ttl',)),
    ('create_core_tables.py', ()),
    ('create_ngsild_tables.py', ()),
    ('create_ngsild_models.py', ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld')),
    ('create_sql_checks_from_shacl.py', ('-c', 'context.jsonld', 'shacl.ttl', 'knowledge.ttl')),
)
LOAD_ORDER = ('rdf.sqlite', 'core.sqlite', 'ngsild.sqlite',
              'ngsild-models.sqlite', 'shacl-validation.sqlite')

# min/max are one CountConstraintComponent in the compiler, two in SHACL.
ALIASES = {'MinCountConstraintComponent': 'CountConstraintComponent',
           'MaxCountConstraintComponent': 'CountConstraintComponent'}
EVENT = re.compile(r'^(?P<component>\w+)\((?P<inside>.*)\)$')


def _local(text):
    return text.rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def parse_event(event):
    """('Component', 'attributeOrShape') from an alerts_bulk_view event string.

    The compiler names a count alert after the whole path --
    `CountConstraintComponent(<iri>hasState[0] ==> <iri>hasXXXWorkpiece)` -- and
    the segment that identifies the constraint is the LAST one, which is the
    same rule normalise.owner_and_edge follows in the other direction.
    """
    match = EVENT.match(event.strip())
    if not match:
        return event, ''
    component = match.group('component')
    inside = match.group('inside')
    if '==>' in inside:
        inside = inside.split('==>')[-1]
    name = _local(re.sub(r'\[\d+\]', '', inside).strip())
    return component, name


def available(shacl2flink_dir, python_exe=None):
    """(ok, reason). Never guesses that an unavailable check passed."""
    if not shacl2flink_dir or not os.path.isdir(shacl2flink_dir):
        return False, f'shacl2flink directory not found: {shacl2flink_dir!r}'
    if shutil.which('sqlite3') is None:
        return False, 'the sqlite3 command line tool is not installed'
    exe = python_exe or sys.executable
    probe = subprocess.run(
        [exe, '-c', 'import oxrdflib, jinja2'],
        capture_output=True, text=True)
    if probe.returncode != 0:
        return False, ('shacl2flink needs oxrdflib and Jinja2, which this '
                       'interpreter does not have; see requirements-crosscheck.txt')
    return True, ''


def _build(package, workdir, shacl2flink_dir, python_exe):
    export(package, workdir, EmissionMode.COMPILE)
    if not os.path.exists(os.path.join(workdir, 'context.jsonld')):
        raise FileNotFoundError(
            'the compiler needs a local context.jsonld; the package does not '
            'provide one, and a build must not depend on fetching a remote context')
    os.makedirs(os.path.join(workdir, 'output'), exist_ok=True)
    environment = dict(os.environ, PYTHONPATH=shacl2flink_dir)
    for script, arguments in BUILD_STEPS:
        result = subprocess.run(
            [python_exe, os.path.join(shacl2flink_dir, script), *arguments],
            cwd=workdir, env=environment, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'{script} failed:\n{result.stderr.strip()[-800:]}')


def pcre_extension():
    """Path to the sqlite3 PCRE extension, or None.

    The generated SQL uses REGEXP, which sqlite does not provide natively. The
    repo's own harness gets it from ~/.sqliterc, written by `make setup`;
    loading it explicitly makes the cross-check independent of that file.
    """
    for candidate in glob.glob('/usr/lib/sqlite3/pcre*.so') + \
            glob.glob('/usr/lib/*/sqlite3/pcre*.so'):
        return candidate
    return None


def _oracle_rows(workdir):
    """Load the generated SQL and read alerts_bulk_view.

    Driven through the sqlite3 CLI rather than Python's sqlite3 module, both
    because the extension load needs a build with extension support and because
    it is exactly what shacl2flink's own tests.sh does -- the point of the
    cross-check is what the compiler's harness would see.
    """
    database = os.path.join(workdir, 'db.sqlite')
    if os.path.exists(database):
        os.remove(database)

    script = []
    extension = pcre_extension()
    if extension:
        script.append(f'.load {extension}')
    for name in LOAD_ORDER:
        path = os.path.join(workdir, 'output', name)
        if os.path.exists(path):
            with open(path, encoding='utf-8') as handle:
                script.append(handle.read())
    # ~/.sqliterc may set `.headers on` and a column mode; both would be parsed
    # as data. State the output format rather than inheriting it.
    script.append('.headers off')
    script.append('.mode list')
    script.append('.separator |')
    script.append('select resource, event, severity from alerts_bulk_view;')

    result = subprocess.run(['sqlite3', database], input='\n'.join(script),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'sqlite3 failed: {result.stderr.strip()[-500:]}')
    if 'Error' in result.stderr:
        raise RuntimeError(f'sqlite3 reported: {result.stderr.strip()[-500:]}')

    rows = []
    for line in result.stdout.splitlines():
        parts = line.split('|')
        if len(parts) >= 3:
            rows.append((parts[0], '|'.join(parts[1:-1]), parts[-1]))
    return rows


def expected_gap(key, profile=None):
    """Whether a result only pyshacl reports is one the compiler is KNOWN not
    to produce: an attribute's unit (hasX.unitCode -- shacl2flink compiles a
    nested property only with a payload of its own), a constraint type
    outside the target profile, or sh:node -- which the compiler inlines, so
    it reports the referenced shape's constraints instead. Those are not
    compiler bugs."""
    from .profile import builtin_profile

    profile = profile or builtin_profile()
    _, attribute, component = key
    # The key carries the compiler's name (min/max count are one Count).
    compiled = profile.components | {ALIASES.get(c, c) for c in profile.components}
    return str(attribute or '').endswith('.unitCode') or \
        component == 'NodeConstraintComponent' or component not in compiled


def compare(oracle_rows, violations):
    """Diagnostics for the difference between the compiled SQL's alerts and
    pyshacl's violations.

    APPROXIMATE, by construction: a result is keyed (resource, attribute,
    component), so two constraints of one component on one attribute -- an
    attribute's sh:minCount and its value's -- share a key. Counts are kept
    (a multiset, not a set), so two such results against one are still a
    difference; which of the two constraints disagreed is not knowable
    until both sides carry a stable constraint id (README, Status).
    """
    from collections import Counter

    oracle = Counter()
    for resource, event, severity in oracle_rows:
        if str(severity).lower() == 'ok':
            continue
        component, name = parse_event(str(event))
        oracle[(str(resource), name, ALIASES.get(component, component))] += 1
    ours = Counter((r.resource, r.attribute, ALIASES.get(r.component, r.component))
                   for r in violations)

    def times(n):
        return f' ({n} times)' if n > 1 else ''

    found = []
    for key, n in sorted((oracle - ours).items()):
        found.append(Diagnostic(
            code='SF-XCHK-MISSED', category='divergence', severity='warning',
            subject=key[0],
            message=(f'the compiled SQL reports {key[2]}({key[1]}) on {key[0]}{times(n)} '
                     f'and pyshacl does not')))
    for key, n in sorted((ours - oracle).items()):
        if expected_gap(key):
            found.append(Diagnostic(
                code='SF-XCHK-EXPECTED', category='divergence', severity='info',
                subject=key[0],
                message=(f'pyshacl reports {key[2]}({key[1]}) on {key[0]}{times(n)}; the '
                         f'compiler is known not to compile it (a unit, or outside the '
                         f'shacl2flink profile) -- expected, not a compiler bug')))
            continue
        found.append(Diagnostic(
            code='SF-XCHK-EXTRA', category='divergence', severity='warning',
            subject=key[0],
            message=(f'pyshacl reports {key[2]}({key[1]}) on {key[0]}{times(n)} and '
                     f'the compiled SQL does not')))
    return found


def cross_check(package, report, shacl2flink_dir, python_exe=None, workdir=None):
    """Compare the compiled SQLite build against the pyshacl report.

    Returns a list of Diagnostics, all category 'divergence' except a single
    'unavailable' note when the check could not run. An approximate
    diagnostic, not a proof of equivalence: see compare().
    """
    python_exe = python_exe or sys.executable
    ok, reason = available(shacl2flink_dir, python_exe)
    if not ok:
        return [Diagnostic(code='SF-XCHK-000', category='divergence',
                           severity='info',
                           message=f'SQLite cross-check not run: {reason}')]

    temporary = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix='semforge-xcheck-')
    try:
        try:
            _build(package, workdir, shacl2flink_dir, python_exe)
            rows = _oracle_rows(workdir)
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            return [Diagnostic(code='SF-XCHK-001', category='divergence',
                               severity='warning',
                               message=f'SQLite cross-check could not run: {exc}')]

        return compare(rows, report.violations)
    finally:
        if temporary:
            shutil.rmtree(workdir, ignore_errors=True)
