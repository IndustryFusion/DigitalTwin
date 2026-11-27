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
    with open(path, encoding='utf-8') as handle:
        return parse_record(handle.read(), path)


def parse_record(text, where):
    """The releases listed in the text of a record, oldest first."""
    from ruamel.yaml import YAML
    data = YAML(typ='safe').load(text) or {}
    if not isinstance(data, dict) or not isinstance(data.get('releases', []), list):
        raise ValueError(f'{where}: expected a mapping with a `releases:` list')
    releases = data.get('releases')
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
    _replace(where, _HEADER + '\n' + out.getvalue())
    return where


def _replace(where, text):
    """Write `text` to `where` all at once: a temporary file, then a rename."""
    import tempfile

    handle, temporary = tempfile.mkstemp(dir=os.path.dirname(where) or '.',
                                         prefix='.' + os.path.basename(where))
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            out.write(text)
        os.replace(temporary, where)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def immutability_problems(report):
    """The contract's rule on the report's package: [] or one Problem."""
    if not report.version:
        return []
    try:
        entry = released(report.root, report.version)
    except Exception as exc:                       # noqa: BLE001 -- malformed record
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        return [Problem(RECORD.replace(os.sep, '/'), f'does not parse: {first}')]
    if entry is None:
        return []
    actual = report.content_digest
    if not actual:
        return [Problem('', f'{report.name} {report.version} is published, and a '
                        f'member cannot be read, so its content cannot be '
                        f'compared with the record')]
    if actual != entry.get('digest'):
        return [Problem(report.descriptor or 'kms.yaml',
                        f'{report.name} {report.version} is published and its '
                        f'content has changed; raise the version '
                        f'(`semforge version patch|minor|major`)')]
    return []


def status(root):
    """'published' or 'draft', for the package's current version."""
    report = check(root)
    try:
        entry = released(root, report.version) if report.version else None
    except Exception:                              # noqa: BLE001 -- malformed record
        return 'unknown'
    return 'published' if entry else 'draft'


# -- the record's history --------------------------------------------------
#
# The record is not a member, so only its history protects it: `semforge
# verify --against REF` compares it with its earlier state at a git ref.

RECORD_POSIX = RECORD.replace(os.sep, '/')
LINK = '120000'                                 # git's mode of a symbolic link


def record_changes(before, after):
    """Problems for every way `after` is not `before` with entries appended.

    An entry of `before` must still be in `after`, under the same version and
    with every field present, absent and valued as it was, type included: `2`
    and `'2'` differ. A version listed twice in `after` is reported too:
    which of the two entries counts would depend on the reader.
    """
    problems, listed = [], {}
    for entry in after:
        listed.setdefault(str(entry.get('version')), []).append(entry)
    for version, entries in listed.items():
        if len(entries) > 1:
            problems.append(Problem(RECORD_POSIX, f'{version} is listed {len(entries)} '
                                    f'times; a version is published once'))
    for old in before:
        version = str(old.get('version'))
        if version not in listed:
            problems.append(Problem(RECORD_POSIX, f'{version} was published and its '
                                    f'entry has been removed; a published '
                                    f'entry cannot be removed'))
            continue
        new = listed[version][0]
        for key in sorted(set(old) | set(new), key=str):
            if _same(old, new, key):
                continue
            problems.append(Problem(RECORD_POSIX, f'{version}: {key} was '
                                    f'{_shown(old, new, key)} and is now '
                                    f'{_shown(new, old, key)}; a published '
                                    f'entry cannot be changed'))
    return problems


def _same(old, new, key):
    if (key in old) != (key in new):
        return False
    was, now = old.get(key), new.get(key)
    return type(was) is type(now) and was == now


def _shown(entry, other, key):
    if key not in entry:
        return '(absent)'
    value = entry[key]
    if value is None:
        return 'null'
    if key in other and other[key] is not None and type(other[key]) is not type(value):
        return f'{value!r} ({type(value).__name__})'
    return str(value)


def _git(where, *arguments):
    """(exit code, stdout) of a git command in `where`; (None, '') without git."""
    import subprocess
    try:
        done = subprocess.run(('git', '-C', where) + arguments,
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, ''
    return done.returncode, done.stdout


@dataclass
class _AtRef:
    """One package directory of the directory of packages at the ref."""
    path: str                       # relative to the work tree's top
    descriptor: str = ''            # its kms.yaml (or legacy semforge.yaml)
    record_mode: str = ''           # mode of .kms/releases.yaml, '' if absent
    kms_link: bool = False          # .kms itself is a link
    name: str = None                # declared name; None if unread


def _listing(top, ref, parent):
    """The package directories under `parent` at `ref`, by directory name.

    One `git ls-tree`, NUL-separated so that no name is quoted. A link
    directly under `parent`, such as `kms/default`, is one entry, not a
    directory, and so never a package.
    """
    from . import config

    code, out = _git(top, 'ls-tree', '-r', '-z', ref, '--', parent + '/')
    if code != 0:
        return None
    found = {}
    for item in out.split('\0'):
        if not item:
            continue
        meta, _, path = item.partition('\t')
        mode = meta.split(' ', 1)[0]
        parts = path[len(parent) + 1:].split('/')
        if len(parts) < 2:
            continue
        here = found.setdefault(parts[0], _AtRef(f'{parent}/{parts[0]}'))
        rest = '/'.join(parts[1:])
        if len(parts) == 2 and parts[1] in config.DESCRIPTORS:
            # kms.yaml wins over a legacy semforge.yaml, as when reading.
            if parts[1] == config.CONFIG or not here.descriptor:
                here.descriptor = path
        elif rest == RECORD_POSIX:
            here.record_mode = mode
        elif rest == '.kms' and mode == LINK:
            here.kms_link = True
    return found


def _read_names(top, ref, found):
    """Fill in the declared names; the directories whose descriptor does not
    parse."""
    from ruamel.yaml import YAML

    unread = []
    for here in found.values():
        if not here.descriptor:
            continue
        code, text = _git(top, 'show', f'{ref}:{here.descriptor}')
        try:
            declared = YAML(typ='safe').load(text) if code == 0 else None
        except Exception:                          # noqa: BLE001 -- malformed there
            declared = None
        if isinstance(declared, dict) and declared.get('name'):
            here.name = str(declared['name'])
        else:
            unread.append(here)
    return unread


def _siblings_named(root, name):
    """Other package directories beside `root` that declare `name` now."""
    from . import config

    parent = os.path.dirname(root)
    clash = []
    for entry in sorted(os.listdir(parent)):
        other = os.path.join(parent, entry)
        if other == root or os.path.islink(other) or not os.path.isdir(other):
            continue
        if not any(os.path.isfile(os.path.join(other, d)) for d in config.DESCRIPTORS):
            continue
        try:
            declared = config.read(other).get('name')
        except Exception:                          # noqa: BLE001 -- reported by its own check
            continue
        if declared is not None and str(declared) == name:
            clash.append(entry)
    return clash


def history_problems(root, ref):
    """Problems, and what was compared, for the record against `ref`.

    The record in the package must be the earlier record at `ref` with
    entries appended. A package is identified by its name, so its earlier
    records are the one at its own path at `ref` and the one of every package
    that declares its name in the same directory of packages at `ref` --
    moved, copied, or replaced by another package at this path. A name `ref`
    does not have is new. A record, or `.kms`, that is a link is refused here
    and at `ref`, and so is a record at `ref` that does not parse: either
    would let the record change without its history showing it.
    """
    from . import config

    root = os.path.realpath(root)
    not_compared = f'not compared with {ref}'
    code, top = _git(root, 'rev-parse', '--show-toplevel')
    if code != 0:
        return [Problem(RECORD_POSIX, f'{root} is not in a git work tree, so the '
                        f'record has no history to compare with {ref}')], not_compared
    top = os.path.realpath(top.strip())
    code, _ = _git(top, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
    if code != 0:
        return [Problem(RECORD_POSIX, f'{ref} is not a commit in {top}; fetch it, '
                        f'or name another one')], not_compared

    for link in ('.kms', RECORD_POSIX):
        if os.path.islink(os.path.join(root, link)):
            return [Problem(link, 'is a symbolic link; the release record must be '
                            'a file in the package, or its history does not '
                            'show its changes')], not_compared

    package = os.path.relpath(root, top).replace(os.sep, '/')
    parent, directory = os.path.dirname(package), os.path.basename(package)
    try:
        name = str(config.read(root).get('name') or '')
    except Exception:                              # noqa: BLE001 -- reported by check()
        name = ''
    problems = []
    if name:
        clash = _siblings_named(root, name)
        if clash:
            problems.append(Problem(config.name_for(root), f'declares the name {name}, '
                                    f'and so does {", ".join(clash)} beside it; a '
                                    f'name identifies one package'))

    found = _listing(top, ref, parent) if parent else {}
    if found is None:
        return problems + [Problem(RECORD_POSIX, f'cannot list {parent} at {ref}')], \
            not_compared
    for here in _read_names(top, ref, found):
        if here.record_mode or here.kms_link:
            problems.append(Problem(RECORD_POSIX, f'the descriptor {here.descriptor} '
                                    f'on {ref} does not parse, so whether its '
                                    f'published record belongs to this package '
                                    f'cannot be told'))
    earlier = [here for key, here in sorted(found.items())
               if (key == directory or (name and here.name == name))
               and (here.record_mode or here.kms_link)]
    if not earlier:
        if problems:
            return problems, not_compared
        return [], f'no release record on {ref}; nothing to keep'

    try:
        after = read_record(record_path(root))
    except Exception:                              # noqa: BLE001 -- reported by check()
        return problems, f'{not_compared}: the record does not parse'

    kept = []
    for here in earlier:
        own = here.path == package
        suffix = '' if own else f' (published as {here.path} on {ref})'
        source = f'{ref}:{here.path}/{RECORD_POSIX}'
        if here.kms_link or here.record_mode == LINK:
            problems.append(Problem(RECORD_POSIX, f'{source} is a symbolic link; '
                                    f'its history cannot be compared{suffix}'))
            continue
        code, text = _git(top, 'show', source)
        if code != 0:
            problems.append(Problem(RECORD_POSIX, f'{source} cannot be read{suffix}'))
            continue
        try:
            before = parse_record(text, source)
        except Exception as exc:                   # noqa: BLE001 -- malformed there
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            problems.append(Problem(RECORD_POSIX, f'{source} does not parse ({first}), '
                                    f'so the record cannot be compared{suffix}'))
            continue
        changes = record_changes(before, after)
        problems += [Problem(p.path, p.message + suffix) for p in changes]
        if not changes:
            kept.append(f'the {len(before)} entries published on {ref}'
                        + ('' if own else f' at {here.path}')
                        + f', {len(after) - len(before)} appended')
    if problems:
        return problems, f'does not keep the entries published on {ref}'
    return [], f'keeps {" and ".join(kept)}'


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


def run_tests(root, allow_network=False):
    """Run the package's declared examples and measure its coverage.

    The examples must pass the way `semforge test` judges them: every case
    meets its expectations, no id names two entities in one case, and no case
    uses an attribute nothing declares. The scratchpad is not a test.

    A SPARQL SERVICE anywhere raises ServiceRefused naming what uses it,
    before anything runs (offline.py). The run is offline: only the package's
    own and the SDK's pinned JSON-LD contexts resolve, unless `allow_network`
    lets it fetch other contexts. Nothing else reaches the network.

    Whatever keeps the tests from running is a PackageError (TestsDoNotRun
    when it is none of its own); a test that fails is in the TestRun.
    """
    from ..errors import CapabilityError, PackageError
    from .offline import (TestsDoNotRun, _reason, model_context_urls, offline,
                          package_contexts)
    try:
        with offline(root, package_contexts(root), model_context_urls(root),
                     fetch_contexts=allow_network) as scope:
            try:
                run = _run_tests(root)
            except (PackageError, CapabilityError):
                raise
            except Exception:
                if scope.refusals:
                    raise scope.refusals[0]        # the cause, not its wrapping
                raise
            if scope.refusals:                     # swallowed on the way
                raise scope.refusals[0]
            return run
    except (PackageError, CapabilityError):
        raise
    except Exception as exc:                       # noqa: BLE001 -- any: reported, not raised
        raise TestsDoNotRun(_reason(exc)) from exc


def _run_tests(root):
    from ..expect import load_expectations, run_tests as run_cases
    from ..expect.identity import dangling_references, duplicate_ids, missing_context
    from ..expect.vocabulary import undeclared_attributes
    from ..sanity import known_constraints
    from .loader import load

    package = load(root)
    if package.vocabulary_error:
        # Elsewhere a vocabulary that did not load is a finding; the tests
        # would run without any NGSI-LD term declared, so they do not run.
        from ..errors import PackageError
        from ..ngsild.vocabulary import source_for
        raise PackageError(f'the NGSI-LD vocabulary {source_for(root).source} did '
                           f'not load: {package.vocabulary_error}')
    from .offline import refuse_services
    refuse_services(package)
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
    covered, _ = asserted_coverage(paired, constraints)
    run.constraints = sorted(constraints)
    run.covered = sorted(covered)
    return run


def asserted_coverage(paired, constraints):
    """(covered, unasserted) over declared examples and their reports.

    `covered`: the constraints some example asserts to fire, on an example
    where they do -- the contract's measure, the one `publish` gates on.
    `unasserted`: those that fire somewhere without any example asserting
    it, which a list of firings would count and this measure does not.
    """
    from ..expect.runner import Status, constraint_ref

    constraints = set(constraints)
    covered, fired_anywhere = set(), set()
    for example, report in paired:
        fired = {constraint_ref(r) for r in report.results if r.status is Status.VIOLATED}
        asserted = {str(a.get('constraint', '')) for a in example.asserts}
        covered |= (asserted & fired & constraints)
        fired_anywhere |= fired & constraints
    return covered, fired_anywhere - covered


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
    try:
        entry = released(None, verified.version, path=record)
    except Exception as exc:                       # noqa: BLE001 -- malformed record
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        problems.append(Problem(record, f'does not parse: {first}'))
        return problems, f'{record} could not be read'
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


def publish(root, output=None, today=None, compress=True, allow_network=False):
    """Test, pack and record the package's current version.

    Nothing is written or recorded unless every check passes. Publishing a
    version that is recorded with the same digest repeats the archive and
    leaves the record alone. The tests run offline unless `allow_network`.
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

    # Pack first and test what was packed: the files may change while the
    # tests run, and the record must describe the archive, not the directory.
    import shutil
    import tempfile

    from .archive import default_name, verify

    final = os.path.abspath(output or default_name(report))
    os.makedirs(os.path.dirname(final), exist_ok=True)
    handle, staged = tempfile.mkstemp(dir=os.path.dirname(final), suffix='.kms.zip.part')
    os.close(handle)
    holder = tempfile.mkdtemp(prefix='kms-publish-')
    try:
        packed = pack(root, output=staged, compress=compress)
        verified = verify(staged, into=os.path.join(holder, 'package'))
        if not verified.ok:
            raise PublishRefused(verified.problems, report=report)
        from ..errors import CapabilityError, PackageError
        from .offline import ServiceRefused
        try:
            run = run_tests(verified.tree, allow_network=allow_network)
        except ServiceRefused as exc:
            raise PublishRefused([Problem(s, m) for s, m in exc.problems],
                                 report=report) from exc
        except (PackageError, CapabilityError) as exc:
            # Refused to go offline, a shipped copy that fails its hash,
            # shapes the validator refuses: the tests do not run, so nothing
            # is published -- the same report `verify --tests` gives.
            raise PublishRefused([Problem('', f'tests do not run: {exc}')],
                                 report=report) from exc
        problems = [Problem(f.split(': ', 1)[0], 'does not meet its expectations: '
                            + f.split(': ', 1)[-1]) for f in run.failing]
        if run.coverage < run.threshold:
            problems.append(Problem('', f'coverage {run.coverage:g} % is below the '
                                    f'threshold of {run.threshold:g} %: '
                                    f'{len(run.uncovered)} of {len(run.constraints)} '
                                    f'constraints are not covered'))
        if problems:
            raise PublishRefused(problems, run=run, report=report)
        os.replace(staged, final)
    finally:
        shutil.rmtree(holder, ignore_errors=True)
        if os.path.exists(staged):
            os.unlink(staged)
    packed.path = final

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
    # The version, findable again: its files and record committed, tagged
    # v<version> in the package's own repository (package/history.py).
    from . import history
    history.tag(root, report.version)
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
    _replace(where, ''.join(lines))
