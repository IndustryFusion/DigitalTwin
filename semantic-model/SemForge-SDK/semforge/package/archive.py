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

"""The distribution form of a KMS package: a zip that checks itself.

openspec change gh-939-kms-package, capability `contracts/kms-package`.

The archive holds the package's members and one more entry, `SHA256SUMS`, in
the format `sha256sum -c` reads -- so anyone can check a package with nothing
but unzip and coreutils. The package digest is the hash of `SHA256SUMS`, not
of the zip: deflate output differs between zlib builds, the member contents do
not, and a digest that changed with the packer's platform could not name a
package.

Verification is all or nothing. Every entry is checked BEFORE anything is
written (paths, links, encryption, size), hashes are checked while extracting
into a fresh directory, and the extracted tree must then pass the package
check. A caller gets a directory only when all of that held.
"""

import hashlib
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field

from .conformance import SUMS, Problem, check, digest_of, sums_text

EPOCH = (1980, 1, 1, 0, 0, 0)
DEFAULT_LIMIT = 512 * 1024 * 1024
_LINE = re.compile(r'^([0-9a-f]{64})  (.+)$')


def is_archive(path):
    return os.path.isfile(path) and path.lower().endswith('.zip')


# -- pack ------------------------------------------------------------------

@dataclass
class Packed:
    path: str
    digest: str
    name: str
    version: str
    members: list
    left_out: list


def default_name(report):
    return f'{report.name}-{report.version}.kms.zip'


def pack(root, output=None, compress=True):
    """Write the archive of the package at `root`. Returns Packed.

    Raises PackageInvalid carrying the report when the package fails the
    contract; nothing is written then.
    """
    report = check(root)
    if not report.ok:
        raise PackageInvalid(report.problems, report)
    output = os.path.abspath(output or default_name(report))
    sums = sums_text(report.root, report.members)
    method = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED

    def entry(name):
        info = zipfile.ZipInfo(name, date_time=EPOCH)
        info.compress_type = method
        info.create_system = 3                       # unix: mode bits below
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        return info

    directory = os.path.dirname(output) or '.'
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix='.zip.part')
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, 'w') as archive:
            archive.writestr(entry(SUMS), sums)
            for member in report.members:
                with open(os.path.join(report.root, *member.split('/')), 'rb') as f:
                    archive.writestr(entry(member), f.read())
        os.replace(temporary, output)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return Packed(path=output, digest=digest_of(sums), name=report.name,
                  version=report.version, members=report.members,
                  left_out=report.left_out)


# -- verify ----------------------------------------------------------------

class PackageInvalid(Exception):
    def __init__(self, problems, report=None):
        self.problems = list(problems)
        self.report = report
        super().__init__('\n'.join(str(p) for p in self.problems))


@dataclass
class Verified:
    source: str
    ok: bool
    name: str = ''
    version: str = ''
    digest: str = ''
    problems: list = field(default_factory=list)
    tree: str = ''                 # the extracted package, when ok

    def as_dict(self):
        return {'source': self.source, 'ok': self.ok, 'name': self.name,
                'version': self.version, 'digest': self.digest,
                'problems': [{'path': p.path, 'message': p.message}
                             for p in self.problems]}


def _unsafe(name):
    if not name or name.startswith('/') or '\\' in name or \
            re.match(r'^[A-Za-z]:', name):
        return 'path must be relative, with / as separator'
    if any(part in ('..', '') for part in name.rstrip('/').split('/')):
        return 'path must not contain empty or .. segments'
    return ''


def _parse_sums(data, problems):
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        problems.append(Problem(SUMS, 'is not UTF-8'))
        return None
    if text and not text.endswith('\n'):
        problems.append(Problem(SUMS, 'last line is not terminated'))
        return None
    listed = {}
    order = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _LINE.match(line)
        if not match:
            problems.append(Problem(SUMS, f'line {number} is not '
                                    '"<sha256>  <path>"'))
            return None
        digest, path = match.groups()
        if path in listed:
            problems.append(Problem(SUMS, f'lists {path} twice'))
            return None
        listed[path] = digest
        order.append(path.encode('utf-8'))
    if order != sorted(order):
        problems.append(Problem(SUMS, 'is not sorted by path'))
        return None
    return listed


def _integrity(archive, limit, problems):
    """Check everything that can be checked without writing. Returns
    (entries by name, listed hashes, sums bytes) or None."""
    entries = {}
    total = 0
    for info in archive.infolist():
        name = info.filename
        why = _unsafe(name)
        if why:
            problems.append(Problem(name, why))
            continue
        mode = info.external_attr >> 16
        if info.flag_bits & 0x1:
            problems.append(Problem(name, 'is encrypted'))
            continue
        if stat.S_ISLNK(mode):
            problems.append(Problem(name, 'is a link; entries must be '
                                    'regular files'))
            continue
        if info.is_dir():
            if info.file_size:
                problems.append(Problem(name, 'is a directory carrying data'))
            continue
        if name in entries:
            problems.append(Problem(name, 'appears twice in the archive'))
            continue
        entries[name] = info
        total += info.file_size
    if total > limit:
        problems.append(Problem('', f'{total} bytes uncompressed exceed the '
                                f'limit of {limit}'))
    if problems:
        return None

    if SUMS not in entries:
        problems.append(Problem(SUMS, 'missing: the archive cannot be checked'))
        return None
    sums = archive.read(entries[SUMS])
    listed = _parse_sums(sums, problems)
    if listed is None:
        return None
    for name in sorted(set(entries) - set(listed) - {SUMS}):
        problems.append(Problem(name, f'is not listed in {SUMS}'))
    for name in sorted(set(listed) - set(entries)):
        problems.append(Problem(name, f'is listed in {SUMS} but missing'))
    if SUMS in listed:
        problems.append(Problem(SUMS, 'must not list itself'))
    if problems:
        return None
    return entries, listed, sums


def _extract(archive, entries, listed, target, problems):
    """Write each listed entry under `target`, hashing as it goes; never
    trusting the declared size (a zip bomb lies about it)."""
    real = os.path.realpath(target)
    for name in sorted(listed):
        info = entries[name]
        destination = os.path.realpath(os.path.join(target, *name.split('/')))
        if not destination.startswith(real + os.sep):
            problems.append(Problem(name, 'would be written outside the '
                                    'extraction directory'))
            return
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        hashed = hashlib.sha256()
        written = 0
        with archive.open(info) as source, open(destination, 'wb') as sink:
            for chunk in iter(lambda: source.read(1 << 20), b''):
                written += len(chunk)
                if written > info.file_size:
                    problems.append(Problem(name, 'holds more data than it '
                                            'declares'))
                    return
                hashed.update(chunk)
                sink.write(chunk)
        if hashed.hexdigest() != listed[name]:
            problems.append(Problem(name, f'does not match its SHA-256 in '
                                    f'{SUMS}'))


def verify(path, into=None, limit=DEFAULT_LIMIT):
    """Verify an archive. With `into`, the package is extracted there (which
    must not exist yet) and kept when it verifies; otherwise a temporary
    directory is used and removed. Never leaves a partial tree behind."""
    result = Verified(source=os.path.abspath(path), ok=False)
    problems = result.problems
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        problems.append(Problem('', f'not a zip archive: {exc}'))
        return result

    with archive:
        checked = _integrity(archive, limit, problems)
        if checked is None:
            return result
        entries, listed, sums = checked
        result.digest = digest_of(sums)

        if into:
            if os.path.exists(into):
                raise FileExistsError(into)
            target = into
        else:
            target = tempfile.mkdtemp(prefix='kms-package-')
        os.makedirs(target, exist_ok=True)
        _extract(archive, entries, listed, target, problems)

    if not problems:
        report = check(target)
        problems.extend(report.problems)
        result.name, result.version = report.name, report.version
        if report.ok and sorted(report.members) != sorted(listed):
            for name in sorted(set(listed) - set(report.members)):
                problems.append(Problem(name, 'is in the archive but is not '
                                        'a member of the package'))
            for name in sorted(set(report.members) - set(listed)):
                problems.append(Problem(name, 'is a member of the package but '
                                        'not in the archive'))

    result.ok = not problems
    if result.ok and into:
        result.tree = os.path.abspath(target)
    else:
        shutil.rmtree(target, ignore_errors=True)
    if not result.ok:
        result.digest = ''        # a digest is only reported for a package
    return result


def verify_directory(root):
    """The same verdict for a directory: the package check, and the digest
    its archive would have."""
    report = check(root)
    return Verified(source=report.root, ok=report.ok, name=report.name,
                    version=report.version, digest=report.digest,
                    problems=list(report.problems))
