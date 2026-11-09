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

"""Is this directory a KMS package, as the contract defines one?

openspec change gh-939-kms-package, capability `contracts/kms-package`.

The loader (`loader.py`) is lenient on purpose: it reads every name SemForge
ever wrote, `main.jsonld` and `shapes/` among them, and lets a file win over a
directory. That keeps existing packages working in the editor. This module is
the other half: the strict answer every OTHER consumer -- shacl2flink, the
dataservice, the OPC UA tools -- can implement the same way, because it allows
one name per role and calls anything ambiguous an error.

It needs nothing but the package: no network, no SemForge state, no editor.
Turtle is parsed to prove it parses; JSON-LD is checked as JSON, because
expanding it would mean resolving its context, and the contract promises that
checking a package never fetches anything.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field

FORMAT_VERSION = 1
DESCRIPTOR = 'kms.yaml'
LEGACY_DESCRIPTOR = 'semforge.yaml'      # read by the SDK, not by the format
SUMS = 'SHA256SUMS'
DEFAULT_COVERAGE = 80

NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
                    r'(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$')

# role -> (file, directory, suffix, where it may live)
ROLES = {
    'knowledge': ('knowledge.ttl', 'knowledge', '.ttl', ('',)),
    'shacl': ('shacl.ttl', 'shacl', '.ttl', ('',)),
    'model-instance': ('model-instance.jsonld', 'model-instance', '.jsonld',
                       ('', 'model')),
}
# Names the SemForge loader reads and the contract does not allow, with the
# name that conforms. Reported, never silently accepted.
ALIASES = {
    'shapes': 'shacl/',
    'main.jsonld': 'model-instance.jsonld',
    'model.jsonld': 'model-instance.jsonld',
    'main': 'model-instance/',
    'model/main.jsonld': 'model/model-instance.jsonld',
    'model/model.jsonld': 'model/model-instance.jsonld',
    'model/instance.jsonld': 'model/model-instance.jsonld',
    'model/main': 'model/model-instance/',
    'model/instance': 'model/model-instance/',
}
EXAMPLES = ('examples', 'model/examples')
DOCUMENTATION = ('README.md', 'LICENSE')


@dataclass(frozen=True)
class Problem:
    path: str        # package-relative, '' for the package as a whole
    message: str

    def __str__(self):
        return f'{self.path}: {self.message}' if self.path else self.message


@dataclass
class Report:
    root: str
    name: str = ''
    version: str = ''
    problems: list = field(default_factory=list)
    roles: dict = field(default_factory=dict)     # role -> [relative paths]
    members: list = field(default_factory=list)   # relative paths, sorted
    left_out: list = field(default_factory=list)  # relative paths, sorted
    descriptor: str = ''                          # the file that was read
    coverage_threshold: float = DEFAULT_COVERAGE  # tests.coverage, percent
    _digest: object = None                        # computed once

    @property
    def ok(self):
        return not self.problems

    def fail(self, path, message):
        self.problems.append(Problem(path, message))

    @property
    def digest(self):
        """The digest the package's archive has. '' while it is invalid."""
        if not self.ok:
            return ''
        return self.content_digest

    @property
    def content_digest(self):
        """The digest of the members as they are, valid or not: what a
        release record is compared with. '' when a member cannot be read."""
        if self._digest is None:
            try:
                self._digest = digest_of(sums_text(self.root, self.members))
            except OSError:
                self._digest = ''
        return self._digest

    def as_dict(self):
        return {
            'root': self.root, 'ok': self.ok, 'name': self.name,
            'version': self.version, 'digest': self.digest,
            'roles': self.roles, 'members': self.members,
            'leftOut': self.left_out,
            'problems': [{'path': p.path, 'message': p.message}
                         for p in self.problems],
        }


# -- digest ----------------------------------------------------------------

def sha256_file(path):
    hashed = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            hashed.update(chunk)
    return hashed.hexdigest()


def sums_text(root, members):
    """SHA256SUMS for these members: coreutils format, sorted by path bytes."""
    lines = [f'{sha256_file(os.path.join(root, *m.split("/")))}  {m}\n'
             for m in sorted(members, key=lambda m: m.encode('utf-8'))]
    return ''.join(lines).encode('utf-8')


def digest_of(sums_bytes):
    return 'sha256:' + hashlib.sha256(sums_bytes).hexdigest()


# -- helpers ---------------------------------------------------------------

def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, '/')


def _documents(directory, suffix):
    return [os.path.join(directory, n) for n in sorted(os.listdir(directory))
            if not n.startswith('.') and n.endswith(suffix)
            and os.path.isfile(os.path.join(directory, n))]


def _inside(root, declared):
    """Is a declared relative path inside the root? (and normalised)"""
    if os.path.isabs(declared) or declared.startswith(('/', '\\')) or \
            re.match(r'^[A-Za-z]:', declared):
        return None
    normal = os.path.normpath(declared).replace(os.sep, '/')
    if normal == '..' or normal.startswith('../'):
        return None
    real_root = os.path.realpath(root)
    real = os.path.realpath(os.path.join(root, normal))
    if real != real_root and not real.startswith(real_root + os.sep):
        return None                      # a symlink pointing out
    return normal


def _link_on_the_way(root, rel):
    """The first component of `rel` below `root` that is a symbolic link, or
    '' -- including the member itself, and any path that leaves the root."""
    here = root
    parts = rel.split('/')
    for depth, part in enumerate(parts):
        here = os.path.join(here, part)
        if os.path.islink(here):
            return '/'.join(parts[:depth + 1])
    real_root = os.path.realpath(root)
    if not os.path.realpath(here).startswith(real_root + os.sep):
        return rel
    return ''


def _inside_root(root, path):
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    return real == real_root or real.startswith(real_root + os.sep)


def _check_example_paths(report, root, suites):
    """Every case and include an expectations file names lies inside the
    package, so the tests of an archive are the tests of its members."""
    if not suites:
        return
    base = os.path.join(root, *suites[0].split('/'))
    for here, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        if 'expectations.yaml' not in files:
            continue
        source = os.path.join(here, 'expectations.yaml')
        try:
            from ruamel.yaml import YAML
            with open(source, encoding='utf-8') as handle:
                raw = YAML(typ='safe').load(handle) or {}
        except Exception as exc:                   # noqa: BLE001
            report.fail(_rel(root, source), f'does not parse: {exc}')
            continue
        entries = raw.get('examples') if isinstance(raw, dict) else None
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            named = [('path', entry.get('path'), here)]
            named += [('include', item, base) for item in entry.get('include') or []]
            for key, value, relative_to in named:
                if not isinstance(value, str) or not value:
                    continue
                if os.path.isabs(value) or value.startswith('\\') or '\\' in value \
                        or re.match(r'^[A-Za-z]:', value):
                    report.fail(_rel(root, source), f'{key} {value!r} must be a '
                                f'relative path inside the package')
                    continue
                candidates = [os.path.join(relative_to, value)]
                if key == 'include':
                    candidates.append(os.path.join(root, value))
                if not any(_inside_root(root, c) for c in candidates):
                    report.fail(_rel(root, source), f'{key} {value!r} leaves the '
                                f'package; the tests of a package use only its '
                                f'members')


def _parses(report, root, path, suffix):
    rel = _rel(root, path)
    try:
        if suffix == '.ttl':
            from rdflib import Graph
            Graph().parse(path, format='turtle')
        else:
            with open(path, encoding='utf-8') as handle:
                document = json.load(handle)
            if not isinstance(document, (dict, list)):
                report.fail(rel, 'is not a JSON-LD document (object or array)')
    except Exception as exc:                       # noqa: BLE001
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        report.fail(rel, f'does not parse: {first}')


def _descriptor(report, root):
    """Read the descriptor and check what the format requires of it."""
    present = [n for n in (DESCRIPTOR, LEGACY_DESCRIPTOR)
               if os.path.isfile(os.path.join(root, n))]
    if not present:
        report.fail(DESCRIPTOR, 'missing: a KMS package is a directory holding '
                    'kms.yaml')
        return {}
    if len(present) > 1:
        report.fail(', '.join(present), 'two descriptors; keep kms.yaml')
    if present[0] == LEGACY_DESCRIPTOR:
        report.fail(LEGACY_DESCRIPTOR, 'is not a name the KMS package format '
                    'allows; use kms.yaml')
    report.descriptor = present[0]
    where = os.path.join(root, present[0])
    try:
        from ruamel.yaml import YAML
        with open(where, encoding='utf-8') as handle:
            data = YAML(typ='safe').load(handle) or {}
    except Exception as exc:                       # noqa: BLE001
        report.fail(present[0], f'does not parse: {exc}')
        return {}
    if not isinstance(data, dict):
        report.fail(present[0], 'must be a mapping')
        return {}
    at = present[0]

    if 'kmsPackage' in data:
        report.fail(at, 'kmsPackage is not a key the KMS package format '
                    'knows; use format')
    fmt = data.get('format', data.get('kmsPackage'))
    if fmt is None:
        report.fail(at, f'declares no format (the format version, '
                    f'{FORMAT_VERSION})')
    elif not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        report.fail(at, f'format must be a positive integer, not {fmt!r}')
    elif fmt > FORMAT_VERSION:
        report.fail(at, f'format {fmt} is not supported: this tool '
                    f'implements format {FORMAT_VERSION}')

    name = data.get('name')
    if name is None:
        report.fail(at, 'declares no name')
    elif not NAME.match(str(name)):
        report.fail(at, f'name {name!r} must be letters, digits, '
                    f'".", "_" and "-", starting with a letter or digit')
    else:
        report.name = str(name)

    version = data.get('version')
    if version is None:
        report.fail(at, 'declares no version (MAJOR.MINOR.PATCH)')
    elif not SEMVER.match(str(version)):
        report.fail(at, f'version {version!r} is not a semantic '
                    f'version MAJOR.MINOR.PATCH')
    else:
        report.version = str(version)

    tests = data.get('tests')
    threshold = tests.get('coverage') if isinstance(tests, dict) else None
    if threshold is not None:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) \
                or not 0 <= threshold <= 100:
            report.fail(at, f'tests.coverage must be a percentage from 0 to '
                        f'100, not {threshold!r}')
        else:
            report.coverage_threshold = float(threshold)
    return data


def _declared_paths(data):
    """(setting, value) for every path-valued setting the descriptor holds."""
    found = []
    context = data.get('context')
    if isinstance(context, dict) and context.get('local'):
        found.append(('context.local', str(context['local'])))
    ngsild = data.get('ngsild')
    source = ngsild.get('source') if isinstance(ngsild, dict) else ngsild
    if isinstance(source, str) and source and \
            not source.startswith(('http://', 'https://')):
        found.append(('ngsild.source', source))
    return found


# -- the check -------------------------------------------------------------

def check(root, parse=True):
    """The contract's verdict on the directory `root`, as a Report.

    With `parse=False` the role documents are not parsed: the layout, the
    members and the digest only, which is what the editor needs after every
    write to know whether a published version changed.
    """
    root = os.path.abspath(root)
    report = Report(root=root)
    if not os.path.isdir(root):
        report.fail('', f'not a directory: {root}')
        return report

    data = _descriptor(report, root)
    members = set()
    if report.descriptor:
        members.add(report.descriptor)

    # Standalone: every declared path resolves inside the root.
    for setting, value in _declared_paths(data):
        normal = _inside(root, value)
        if normal is None:
            report.fail(report.descriptor, f'{setting} {value!r} leaves the '
                        f'package root; a package is standalone')
        elif not os.path.isfile(os.path.join(root, normal)):
            report.fail(normal, f'declared as {setting} but missing')
        else:
            members.add(normal)
    if 'context.local' not in dict(_declared_paths(data)) and \
            os.path.isfile(os.path.join(root, 'context.jsonld')):
        members.add('context.jsonld')         # the SemForge default

    # Aliases the loader reads but the contract does not allow.
    for alias, conforming in ALIASES.items():
        if os.path.exists(os.path.join(root, *alias.split('/'))):
            report.fail(alias, f'is not a name the KMS package format '
                        f'allows; use {conforming}')
    model_dir = os.path.join(root, 'model')
    if os.path.isdir(model_dir):
        for stray in _documents(model_dir, '.jsonld'):
            if os.path.basename(stray) != 'model-instance.jsonld' and \
                    _rel(root, stray) not in ALIASES:
                report.fail(_rel(root, stray), 'a bare document in model/ is '
                            'not a role; use model/model-instance/')

    # The three roles.
    for role, (filename, dirname, suffix, places) in ROLES.items():
        present = []
        for place in places:
            base = os.path.join(root, place) if place else root
            for candidate in (filename, dirname):
                path = os.path.join(base, candidate)
                if os.path.exists(path):
                    present.append(path)
        if not present:
            where = ' or '.join(f'{p + "/" if p else ""}{n}' for p in places
                                for n in (filename, dirname + '/'))
            report.fail('', f'missing role {role}: looked for {where}')
            continue
        if len(present) > 1:
            report.fail(', '.join(_rel(root, p) for p in present),
                        f'role {role} is present more than once; keep one')
            continue
        path = present[0]
        if os.path.isdir(path):
            documents = _documents(path, suffix)
            if not documents:
                report.fail(_rel(root, path), f'is the {role} directory but '
                            f'holds no {suffix} document')
                continue
        else:
            documents = [path]
        for document in documents:
            if parse:
                _parses(report, root, document, suffix)
        report.roles[role] = [_rel(root, d) for d in documents]
        members.update(report.roles[role])

    # The examples suite.
    suites = [e for e in EXAMPLES if os.path.isdir(os.path.join(root, *e.split('/')))]
    if len(suites) > 1:
        report.fail(', '.join(suites), 'two examples suites; keep one')
    for suite in suites[:1]:
        for here, dirs, files in os.walk(os.path.join(root, *suite.split('/'))):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            for d in dirs:
                # A linked directory would not be walked: its cases would
                # vanish from the package without a word.
                if os.path.islink(os.path.join(here, d)):
                    report.fail(_rel(root, os.path.join(here, d)),
                                'is a symbolic link; the examples suite must '
                                'hold its cases itself')
            members.update(_rel(root, os.path.join(here, f))
                           for f in files if not f.startswith('.'))

    for name in DOCUMENTATION:
        if os.path.isfile(os.path.join(root, name)):
            members.add(name)

    # Everything else is left out -- reported, so nothing is lost silently.
    # A directory none of whose files is a member is reported once.
    left_out = []
    for here, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        kept = []
        for d in dirs:
            rel = _rel(root, os.path.join(here, d))
            if any(m == rel or m.startswith(rel + '/') for m in members):
                kept.append(d)
            else:
                left_out.append(rel + '/')
        dirs[:] = kept
        for f in sorted(files):
            if f.startswith('.'):
                continue
            path = os.path.join(here, f)
            rel = _rel(root, path)
            if rel in members:
                continue                  # links are judged below, for all members
            left_out.append(rel)

    report.members = sorted(members, key=lambda m: m.encode('utf-8'))
    report.left_out = sorted(left_out)

    # Every member is a regular file inside the root, reached without a link:
    # a linked directory would ship -- and let change unnoticed -- whatever it
    # points to (finding of the review of #940).
    for member in report.members:
        through = _link_on_the_way(root, member)
        if through:
            report.fail(member, f'is reached through the symbolic link '
                        f'{through}; a member must be a regular file inside '
                        f'the package')
    _check_example_paths(report, root, suites[:1])

    # A published version is immutable (releases.py keeps the record).
    from .releases import immutability_problems
    report.problems.extend(immutability_problems(report))
    return report
