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

"""Published versions of a KMS package, and the tests a version must pass.

openspec change gh-939-kms-package, capability `contracts/kms-package`.

The release record `.kms/releases.yaml` lists every published version with
its package digest, its date and the results of its tests. It is hidden, so
it is not a member: recording a digest inside a member would change the
digest. The rule it carries is the one registries enforce -- the same name
and version always mean the same content -- and `conformance.check` applies
it: a published version whose members changed fails until it is raised.

Coverage is counted the way the contract defines it: the share of the
package's constraints that some example ASSERTS to fire, on an example where
it does fire. A constraint that only ever holds cannot be told apart from one
nobody checked, so good examples alone cover nothing.
"""

import datetime
import os
import re
from dataclasses import dataclass, field

from .conformance import SEMVER, Problem, check

RECORD = os.path.join('.kms', 'releases.yaml')
PARTS = ('major', 'minor', 'patch')

_HEADER = """\
# Published versions of this KMS package, written by `semforge publish`.
#
# The same name and version always mean the same content: a version listed
# here whose package digest no longer matches fails `semforge verify` until
# the version is raised. This file is not part of the package digest.
"""


# -- the record ------------------------------------------------------------

def record_path(root):
    return os.path.join(root, RECORD)


def read_record(path):
    """The releases listed in a record file, oldest first ([] if none)."""
    if not os.path.isfile(path):
        return []
    from ruamel.yaml import YAML
    with open(path, encoding='utf-8') as handle:
        data = YAML(typ='safe').load(handle) or {}
    releases = data.get('releases') if isinstance(data, dict) else None
    return [dict(r) for r in releases or [] if isinstance(r, dict)]


def released(root, version, path=None):
    """The record entry for `version`, or None."""
    for entry in read_record(path or record_path(root)):
        if str(entry.get('version')) == str(version):
            return entry
    return None


def _write_record(root, releases):
    import io

    from ruamel.yaml import YAML
    where = record_path(root)
    os.makedirs(os.path.dirname(where), exist_ok=True)
    out = io.StringIO()
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.dump({'releases': releases}, out)
    with open(where, 'w', encoding='utf-8') as handle:
        handle.write(_HEADER + '\n' + out.getvalue())
    return where


def immutability_problems(report):
    """The contract's rule on the report's package: [] or one Problem."""
    if not report.version:
        return []
    entry = released(report.root, report.version)
    if entry is None:
        return []
    actual = report.content_digest
    if actual and actual != entry.get('digest'):
        return [Problem(report.descriptor or 'kms.yaml',
                        f'{report.name} {report.version} is published and its '
                        f'content has changed; raise the version '
                        f'(`semforge version patch|minor|major`)')]
    return []


def status(root):
    """'published' or 'draft', for the package's current version."""
    report = check(root)
    return 'published' if report.version and released(root, report.version) else 'draft'


# -- the tests -------------------------------------------------------------

@dataclass
class TestRun:
    examples: int = 0
    met: int = 0
    failing: list = field(default_factory=list)      # example paths, reasons
    constraints: list = field(default_factory=list)  # every constraint, sorted
    covered: list = field(default_factory=list)      # those that fire as asserted
    threshold: float = 80.0

    @property
    def coverage(self):
        if not self.constraints:
            return 100.0
        return round(100.0 * len(self.covered) / len(self.constraints), 1)

    @property
    def uncovered(self):
        covered = set(self.covered)
        return [c for c in self.constraints if c not in covered]

    @property
    def passed(self):
        return not self.failing

    @property
    def publishable(self):
        return self.passed and self.coverage >= self.threshold

    def as_dict(self):
        return {'examples': self.examples, 'met': self.met,
                'failing': self.failing, 'coverage': self.coverage,
                'threshold': self.threshold,
                'constraints': len(self.constraints),
                'covered': len(self.covered)}


def examples_and_reports(package, expectations):
    """Every declared example paired with its validation report."""
    from ..expect.store import compose
    from ..validate.orchestrator import validate_graphs

    paired = []
    for example in expectations.examples:
        graph = compose(package, example)
        paired.append((example, validate_graphs(
            graph, package.shapes, package.knowledge, strict=False)))
    return paired


def run_tests(root):
    """Run the package's declared examples and measure its coverage.

    The examples must pass the way `semforge test` judges them: every case
    meets its expectations, no id names two entities in one case, and no case
    uses an attribute nothing declares. The scratchpad is not a test.
    """
    from ..expect import load_expectations, run_tests as run_cases
    from ..expect.identity import dangling_references, duplicate_ids, missing_context
    from ..expect.runner import Status, constraint_ref
    from ..expect.vocabulary import undeclared_attributes
    from ..sanity import known_constraints
    from .loader import load

    package = load(root)
    expectations = load_expectations(root)
    paired = examples_and_reports(package, expectations)
    run = TestRun(examples=len(paired), threshold=check(root).coverage_threshold)

    for outcome in run_cases(paired, known_constraints(package)):
        if outcome.passed:
            run.met += 1
        else:
            run.failing.append(f'{outcome.example}: ' + '; '.join(
                str(f) for f in outcome.failures))
    for problem in (missing_context(package) + dangling_references(package, expectations)
                    + duplicate_ids(package, expectations)):
        if problem.severity == 'error':
            run.failing.append(f'{problem.entity}: {problem.message}')
    for entry in undeclared_attributes(package):
        if entry.severity == 'error':
            run.failing.append(f'{entry.term}: {entry.message}')

    constraints = known_constraints(package)
    covered = set()
    for example, report in paired:
        fired = {constraint_ref(r) for r in report.results if r.status is Status.VIOLATED}
        asserted = {str(a.get('constraint', '')) for a in example.asserts}
        covered |= (asserted & fired & constraints)
    run.constraints = sorted(constraints)
    run.covered = sorted(covered)
    return run


def compare_with_record(run, verified, record):
    """Problems, and what was compared, for a test run of a verified package.

    A failing example always fails. The run is compared with a release record
    only when one is available; for a version the record lists, the digest,
    the examples and the coverage must be what was published.
    """
    problems = [Problem(f.split(': ', 1)[0], 'does not meet its expectations: '
                        + f.split(': ', 1)[-1]) for f in run.failing]
    if not record:
        return problems, 'no release record was compared'
    entry = released(None, verified.version, path=record)
    if entry is None:
        return problems, f'{verified.version} is not in {record} (a draft)'
    if run.coverage < run.threshold:
        # Only a published version is held to its threshold here; a draft's
        # coverage is reported, not enforced.
        problems.append(Problem('', f'coverage {run.coverage:g} % is below the '
                                f'threshold of {run.threshold:g} % for the '
                                f'published version {verified.version}'))
    expected = {'digest': entry.get('digest'), 'examples': entry.get('examples'),
                'met': entry.get('met'), 'coverage': entry.get('coverage')}
    actual = {'digest': verified.digest, 'examples': run.examples,
              'met': run.met, 'coverage': run.coverage}
    for key, want in expected.items():
        have = actual[key]
        same = (float(have) == float(want)) if key == 'coverage' and want is not None \
            else str(have) == str(want)
        if not same:
            problems.append(Problem('', f'{key} is {have}, but {record} records '
                                    f'{want} for {verified.version}'))
    verdict = 'matches' if not problems else 'differs from'
    return problems, f'{verdict} {record} for {verified.version}'


# -- publishing ----------------------------------------------------------------

class PublishRefused(Exception):
    def __init__(self, problems, run=None, report=None):
        self.problems = list(problems)
        self.run = run
        self.report = report
        super().__init__('\n'.join(str(p) for p in self.problems))


@dataclass
class Published:
    path: str
    name: str
    version: str
    digest: str
    run: object = None
    unchanged: bool = False       # this version was already recorded


def publish(root, output=None, today=None, compress=True):
    """Test, pack and record the package's current version.

    Nothing is written or recorded unless every check passes. Publishing a
    version that is recorded with the same digest repeats the archive and
    leaves the record alone.
    """
    from .archive import pack

    root = os.path.abspath(root)
    report = check(root)
    if not report.ok:
        raise PublishRefused(report.problems, report=report)

    entry = released(root, report.version)
    if entry is not None:                  # same digest, or check() had failed
        packed = pack(root, output=output, compress=compress)
        return Published(path=packed.path, name=report.name, version=report.version,
                         digest=packed.digest, unchanged=True)

    run = run_tests(root)
    problems = [Problem(f.split(': ', 1)[0], 'does not meet its expectations: '
                        + f.split(': ', 1)[-1]) for f in run.failing]
    if run.coverage < run.threshold:
        problems.append(Problem('', f'coverage {run.coverage:g} % is below the '
                                f'threshold of {run.threshold:g} %: '
                                f'{len(run.uncovered)} of {len(run.constraints)} '
                                f'constraints are not covered'))
    if problems:
        raise PublishRefused(problems, run=run, report=report)

    packed = pack(root, output=output, compress=compress)
    releases = read_record(record_path(root))
    releases.append({
        'version': report.version,
        'digest': packed.digest,
        'date': (today or datetime.date.today()).isoformat(),
        'examples': run.examples,
        'met': run.met,
        'coverage': run.coverage,
        'threshold': run.threshold,
    })
    _write_record(root, releases)
    return Published(path=packed.path, name=report.name, version=report.version,
                     digest=packed.digest, run=run)


# -- versions --------------------------------------------------------------

def next_versions(version):
    """{'patch': ..., 'minor': ..., 'major': ...} after `version`."""
    match = SEMVER.match(str(version))
    if not match:
        raise ValueError(f'{version!r} is not a semantic version MAJOR.MINOR.PATCH')
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    return {'patch': f'{major}.{minor}.{patch + 1}',
            'minor': f'{major}.{minor + 1}.0',
            'major': f'{major + 1}.0.0'}


def raise_version(root, part):
    """Raise one part of `version` in the descriptor; returns (old, new)."""
    from . import config

    if part not in PARTS:
        raise ValueError(f'part must be one of {", ".join(PARTS)}')
    current = config.read(root).get('version')
    if current is None:
        raise ValueError('the descriptor declares no version')
    new = next_versions(current)[part]
    _write_version(root, new)
    return str(current), new


def _write_version(root, new):
    """Replace the value on the `version:` line, nothing else."""
    from . import config

    where = config.path_for(root)
    line = config.locate(root, 'version')
    with open(where, encoding='utf-8') as handle:
        lines = handle.read().splitlines(True)
    old = lines[line - 1]
    lines[line - 1] = re.sub(r'^(version:\s*)(["\']?)[^\s#"\']+\2', rf'\g<1>{new}', old)
    with open(where, 'w', encoding='utf-8') as handle:
        handle.writelines(lines)
