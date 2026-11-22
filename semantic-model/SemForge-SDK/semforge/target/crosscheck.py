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
from ..validate.results import UNTYPED
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

XSD = 'http://www.w3.org/2001/XMLSchema#'
DATATYPE = 'DatatypeConstraintComponent'
OR = 'OrConstraintComponent'
# How the compiled SQL reads the text of a value without a declared type
# (#958, design D5: strings are judged by their text): a decimal point or an
# exponent makes a double, digits an integer. A copy of the patterns of
# shacl2flink's sh:datatype check (lib/shacl_properties_to_sql.py,
# `undeclared_double` and the xsd:integer branch); test_profile_drift.py
# reads them there and fails when the two differ.
# ASCII: the SQL's \d is PCRE's, which matches 0-9 only; Python's would also
# take other scripts' digits ("٨٠").
TEXT_DATATYPES = (
    (XSD + 'double',
     re.compile(r'^[+-]?(?:\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)$',
                re.ASCII)),
    (XSD + 'integer', re.compile(r'^[+-]?\d+$', re.ASCII)),
)

# The reasons a difference is expected, one per kind. The wording follows
# shacl2flink/tests/pyshacl-compare/expected-divergences.txt, where the same
# divergences are listed for the compiler's own fixtures.
NOT_COMPILED = ('the compiler is known not to compile it (a unit, or outside the '
                'shacl2flink profile)')
BY_TEXT = ('a value is read by its text, not by its declared type: the compiled '
           'SQL reads the string "{text}" as {datatype}, which the constraint '
           'admits; to SHACL it is an xsd:string (#958, strings are judged by '
           'their text)')
OR_NAMING = ('one violation, named twice: an sh:or of datatypes compiles into '
             'one datatype check, and the compiled SQL names that check where '
             'SHACL names the sh:or')
EXPECTED = ' -- expected, not a compiler bug'


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
        # Found by itself only beside a package inside this repository.
        return False, (f'shacl2flink directory not found: {shacl2flink_dir!r}; '
                       f'point the check at a shacl2flink checkout with '
                       f'--shacl2flink <path>')
    if shutil.which('sqlite3') is None:
        return False, 'the sqlite3 command line tool is not installed'
    exe = python_exe or sys.executable
    probe = subprocess.run(
        [exe, '-c', 'import oxrdflib, jinja2'],
        capture_output=True, text=True)
    if probe.returncode != 0:
        return False, ('shacl2flink needs oxrdflib and Jinja2, which this '
                       'interpreter does not have; see requirements-crosscheck.txt')
    if not regexp_available():
        return False, ('sqlite3 has no REGEXP: its PCRE extension is not loadable '
                       '(see .github/scripts/install-sqlite-pcre.sh)')
    return True, ''


def regexp_available():
    """Whether sqlite3 evaluates REGEXP, as the generated SQL needs.

    Without it every check using a pattern fails to load, and the build would
    report a sqlite3 error where the truth is that the check cannot run here.
    """
    script = []
    extension = pcre_extension()
    if extension:
        script.append(f'.load {extension}')
    script.append(".headers off")
    script.append("select 'a' REGEXP 'a';")
    try:
        result = subprocess.run(['sqlite3', ':memory:'], input='\n'.join(script),
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and 'rror' not in result.stderr and \
        result.stdout.strip().endswith('1')


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


def read_by_text(result):
    """The datatype the compiled SQL reads a rejected string as, or None.

    Only a value without a declared type is read by its text, and SHACL
    rejects such a string on every numeric datatype -- which is the whole of
    the divergence (#958, design D5). A declared type, xsd:string included,
    decides on both sides, so a difference on one is a real one.
    """
    if result.value_datatype != UNTYPED:
        return None
    for datatype, pattern in TEXT_DATATYPES:
        if pattern.fullmatch(result.value):
            return datatype
    return None


def judged_by_text(result):
    """Whether pyshacl rejects this value only because it is a string the
    compiled SQL reads, by its text, as a datatype the constraint admits:
    "80.0" on xsd:double, "80" on xsd:integer or an sh:or of both."""
    if result.component not in (DATATYPE, OR):
        return False
    datatype = read_by_text(result)
    return datatype is not None and datatype in result.datatypes


def compare(oracle_rows, violations):
    """Diagnostics for the difference between the compiled SQL's alerts and
    pyshacl's violations.

    APPROXIMATE, by construction: a result is keyed (resource, attribute,
    component), so two constraints of one component on one attribute -- an
    attribute's sh:minCount and its value's -- share a key. Counts are kept
    (a multiset, not a set), so two such results against one are still a
    difference; which of the two constraints disagreed is not knowable
    until both sides carry a stable constraint id (README, Status).

    Differences the compiler makes on purpose are reported as
    SF-XCHK-EXPECTED, each with its reason: what it does not compile
    (expected_gap), a string it judges by its text (judged_by_text), and an
    sh:or of datatypes it names after the datatype check it compiles into --
    one difference, where it would otherwise count as one missed and one extra.
    """
    from collections import Counter

    oracle = Counter()
    for resource, event, severity in oracle_rows:
        if str(severity).lower() == 'ok':
            continue
        component, name = parse_event(str(event))
        oracle[(str(resource), name, ALIASES.get(component, component))] += 1
    results = {}
    for result in violations:
        key = (result.resource, result.attribute, ALIASES.get(result.component, result.component))
        results.setdefault(key, []).append(result)
    ours = Counter({key: len(found) for key, found in results.items()})

    def times(n):
        return f' ({n} times)' if n > 1 else ''

    def expected(subject, message):
        return Diagnostic(code='SF-XCHK-EXPECTED', category='divergence', severity='info',
                          subject=subject, message=message + EXPECTED)

    missed, extra = oracle - ours, ours - oracle
    paired = Counter()
    found = []
    # One sh:or, two names: the SQL's datatype check against pyshacl's sh:or.
    # Only an sh:or of datatypes is compiled into a datatype check, and only a
    # value the SQL rejects too can be the same violation: a string judged by
    # its text passes there, so its sh:or is no partner for a datatype alert
    # that another value of the attribute raised.
    for key in sorted(missed):
        resource, attribute, component = key
        partner = (resource, attribute, OR)
        if component != DATATYPE or not extra[partner]:
            continue
        eligible = sum(1 for r in results[partner] if r.datatypes and not judged_by_text(r))
        n = min(missed[key], extra[partner], max(0, eligible - oracle[partner]))
        if not n:
            continue
        missed[key] -= n
        extra[partner] -= n
        paired[partner] += n
        found.append(expected(resource, (
            f'the compiled SQL reports {DATATYPE}({attribute}) on {resource}{times(n)} '
            f'where pyshacl reports {OR}({attribute}): {OR_NAMING}')))

    for key, n in sorted((+missed).items()):
        found.append(Diagnostic(
            code='SF-XCHK-MISSED', category='divergence', severity='warning',
            subject=key[0],
            message=(f'the compiled SQL reports {key[2]}({key[1]}) on {key[0]}{times(n)} '
                     f'and pyshacl does not')))
    for key, n in sorted((+extra).items()):
        what = f'pyshacl reports {key[2]}({key[1]}) on {key[0]}'
        if expected_gap(key):
            found.append(expected(key[0], f'{what}{times(n)}; {NOT_COMPILED}'))
            continue
        # The strings among them are the surplus only when everything else on
        # the key is accounted for by the SQL's alerts and the pairs above.
        # Otherwise which results the SQL matched is not knowable from counts,
        # and the key stays a difference rather than a guess.
        strings = [r for r in results[key] if judged_by_text(r)]
        others = len(results[key]) - len(strings)
        if strings and others == oracle[key] + paired[key] and len(strings) == n:
            for result in strings:
                found.append(expected(key[0], f'{what}; ' + BY_TEXT.format(
                    text=result.value, datatype='xsd:' + read_by_text(result)[len(XSD):])))
            continue
        found.append(Diagnostic(
            code='SF-XCHK-EXTRA', category='divergence', severity='warning',
            subject=key[0],
            message=f'{what}{times(n)} and the compiled SQL does not'))
    return found


def cross_check(package, report, shacl2flink_dir, python_exe=None, workdir=None):
    """Compare the compiled SQLite build against the pyshacl report.

    Returns a list of Diagnostics, all category 'divergence' except a single
    'unavailable' note when the check could not run. An approximate
    diagnostic, not a proof of equivalence: see compare().
    """
    python_exe = python_exe or sys.executable
    # The build steps run in a temporary directory: a relative path would
    # resolve there, not where it was given.
    shacl2flink_dir = os.path.abspath(shacl2flink_dir) if shacl2flink_dir else shacl2flink_dir
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
