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

"""What the review of #940 found, each pinned by a test.

Links that lead out of a package, example paths that leave it, archives that
break during extraction, a release record that does not parse, and the hostile
archive shapes the integrity check already rejected without a test saying so.
"""

import datetime
import glob
import os
import shutil
import tempfile
import warnings
import zipfile

import pytest
from click.testing import CliRunner

from semforge.cli.main import cli
from semforge.package.archive import PackageInvalid, pack, verify
from semforge.package.conformance import SUMS, check
from semforge.package.releases import publish, read_record, record_path
from semforge.package.scaffold import create_package

TTL = '@prefix ex: <https://example.org/> .\nex:a ex:b ex:c .\n'


@pytest.fixture
def pkg(tmp_path):
    root = str(tmp_path / 'p')
    create_package(root, name='p', layout='flat')
    return root


def _messages(report):
    return [str(p) for p in report.problems]


def _leftovers():
    return set(glob.glob(os.path.join(tempfile.gettempdir(), 'kms-package-*')))


# --- 1: links out of the package ------------------------------------------------

def test_a_linked_role_directory_is_refused(pkg, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    shutil.move(os.path.join(pkg, 'shacl.ttl'), outside / 'secret.ttl')
    os.symlink('../outside', os.path.join(pkg, 'shacl'))
    problems = _messages(check(pkg))
    assert any('shacl/secret.ttl' in m and 'symbolic link shacl' in m for m in problems), problems
    with pytest.raises(PackageInvalid):
        pack(pkg, output=str(tmp_path / 'p.kms.zip'))


def test_a_linked_examples_suite_is_refused(pkg, tmp_path):
    shutil.move(os.path.join(pkg, 'examples'), tmp_path / 'elsewhere')
    os.symlink(str(tmp_path / 'elsewhere'), os.path.join(pkg, 'examples'))
    assert any('symbolic link examples' in m for m in _messages(check(pkg)))


def test_a_linked_directory_inside_the_suite_is_refused(pkg, tmp_path):
    suite = os.path.join(pkg, 'examples', 'test_MachineShape')
    shutil.move(os.path.join(suite, 'bad'), tmp_path / 'bad')
    os.symlink(str(tmp_path / 'bad'), os.path.join(suite, 'bad'))
    assert any(m.startswith('examples/test_MachineShape/bad: is a symbolic link')
               for m in _messages(check(pkg)))


def test_a_linked_member_file_is_refused(pkg, tmp_path):
    shutil.move(os.path.join(pkg, 'knowledge.ttl'), tmp_path / 'k.ttl')
    os.symlink(str(tmp_path / 'k.ttl'), os.path.join(pkg, 'knowledge.ttl'))
    assert any(m.startswith('knowledge.ttl: is reached through the symbolic link')
               for m in _messages(check(pkg)))


# --- 2: example paths that leave the package -------------------------------------

def _expectations(pkg):
    return os.path.join(pkg, 'examples', 'test_MachineShape', 'good', 'expectations.yaml')


def test_an_absolute_example_path_is_refused(pkg, tmp_path):
    path = _expectations(pkg)
    text = open(path, encoding='utf-8').read()
    shutil.move(os.path.join(os.path.dirname(path), 'running.jsonld'), tmp_path / 'r.jsonld')
    open(path, 'w', encoding='utf-8').write(
        text.replace('path: running.jsonld', f'path: {tmp_path / "r.jsonld"}'))
    assert any('must be a relative path inside the package' in m
               for m in _messages(check(pkg)))


def test_an_example_path_above_the_package_is_refused(pkg):
    path = _expectations(pkg)
    text = open(path, encoding='utf-8').read()
    open(path, 'w', encoding='utf-8').write(
        text.replace('path: running.jsonld', 'path: ../../../../running.jsonld'))
    assert any("path '../../../../running.jsonld' leaves the package" in m
               for m in _messages(check(pkg)))


def test_an_include_outside_the_package_is_refused(pkg):
    path = _expectations(pkg)
    text = open(path, encoding='utf-8').read()
    open(path, 'w', encoding='utf-8').write(
        text.replace('    expect: valid', '    expect: valid\n    include:\n'
                     '      - ../../shared.jsonld'))
    assert any("include '../../shared.jsonld' leaves the package" in m
               for m in _messages(check(pkg)))


def test_the_kms_includes_stay_inside():
    # kms/example includes examples/subobjects/*: inside, so no complaint.
    here = os.path.dirname(os.path.abspath(__file__))
    report = check(os.path.join(here, '..', '..', '..', 'kms', 'default'))
    assert report.ok, _messages(report)


# --- 3: archives that break during extraction ----------------------------------------

def _corrupt_crc(archive_path, member):
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.getinfo(member)
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    with open(archive_path, 'r+b') as handle:
        handle.seek(offset + 3)
        byte = handle.read(1)
        handle.seek(offset + 3)
        handle.write(bytes([byte[0] ^ 0xFF]))


def test_a_corrupted_entry_is_named_and_leaves_nothing(pkg, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    pack(pkg, output=out, compress=False)
    _corrupt_crc(out, 'shacl.ttl')
    before = _leftovers()
    result = verify(out)
    assert not result.ok and [p.path for p in result.problems] == ['shacl.ttl']
    assert _leftovers() == before
    cli_result = CliRunner().invoke(cli, ['verify', out])
    assert cli_result.exit_code == 2 and 'shacl.ttl' in cli_result.output


def test_a_corrupted_sums_entry_is_named(pkg, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    pack(pkg, output=out, compress=False)
    _corrupt_crc(out, SUMS)
    result = verify(out)
    assert not result.ok and result.problems[0].path == SUMS


def _forged(target, entries):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')                # duplicate names
        with zipfile.ZipFile(target, 'w') as archive:
            for info, data in entries:
                archive.writestr(info, data)
    return target


def _sums_for(names_and_data):
    import hashlib
    return ''.join(f'{hashlib.sha256(d).hexdigest()}  {n}\n'
                   for n, d in sorted(names_and_data)).encode()


def test_a_file_and_a_directory_of_one_name(tmp_path):
    files = [('a', b'x'), ('a/b', b'y')]
    target = _forged(str(tmp_path / 't.zip'),
                     [(zipfile.ZipInfo(SUMS), _sums_for(files))] +
                     [(zipfile.ZipInfo(n), d) for n, d in files])
    before = _leftovers()
    result = verify(target)
    assert not result.ok and any(p.path == 'a/b' for p in result.problems)
    assert _leftovers() == before


@pytest.mark.parametrize('name', ['./kms.yaml', 'a/./b.ttl'])
def test_dot_segments_are_refused(tmp_path, name):
    target = _forged(str(tmp_path / 't.zip'), [(zipfile.ZipInfo(SUMS), _sums_for([(name, b'x')])),
                                               (zipfile.ZipInfo(name), b'x')])
    result = verify(target)
    assert any(p.path == name and '. or ..' in p.message for p in result.problems)


@pytest.mark.parametrize('name', ['/etc/x.ttl', 'a\\b.ttl', 'C:/x.ttl'])
def test_absolute_backslash_and_drive_paths(tmp_path, name):
    target = _forged(str(tmp_path / 't.zip'), [(zipfile.ZipInfo(SUMS), b''),
                                               (zipfile.ZipInfo(name), b'x')])
    result = verify(target)
    assert any(p.path == name for p in result.problems)


def _set_encrypted(target, name):
    """Set bit 0 of the general purpose flag of `name` in the central
    directory -- zipfile clears it when writing, so a forger patches bytes."""
    data = bytearray(open(target, 'rb').read())
    at = 0
    while True:
        at = data.find(b'PK\x01\x02', at)
        if at < 0:
            break
        length = int.from_bytes(data[at + 28:at + 30], 'little')
        if data[at + 46:at + 46 + length] == name.encode():
            data[at + 8] |= 0x1
        at += 4
    open(target, 'wb').write(bytes(data))


def test_an_encrypted_entry(tmp_path):
    target = _forged(str(tmp_path / 't.zip'), [(zipfile.ZipInfo(SUMS), b''),
                                               (zipfile.ZipInfo('kms.yaml'), b'x')])
    _set_encrypted(target, 'kms.yaml')
    assert any(p.path == 'kms.yaml' and 'encrypted' in p.message
               for p in verify(target).problems)


def test_duplicate_names(tmp_path):
    target = _forged(str(tmp_path / 't.zip'), [(zipfile.ZipInfo(SUMS), b''),
                                               (zipfile.ZipInfo('kms.yaml'), b'x'),
                                               (zipfile.ZipInfo('kms.yaml'), b'y')])
    assert any('appears twice' in p.message for p in verify(target).problems)


def test_a_directory_carrying_data(tmp_path):
    target = _forged(str(tmp_path / 't.zip'), [(zipfile.ZipInfo(SUMS), b''),
                                               (zipfile.ZipInfo('knowledge/'), b'data')])
    assert any('directory carrying data' in p.message for p in verify(target).problems)


# --- 4: a release record that does not parse ------------------------------------------

def test_a_malformed_record_is_a_problem(pkg, tmp_path):
    os.makedirs(os.path.join(pkg, '.kms'))
    with open(record_path(pkg), 'w', encoding='utf-8') as handle:
        handle.write('releases: [unclosed\n')
    assert any(m.startswith('.kms/releases.yaml: does not parse') for m in _messages(check(pkg)))
    result = CliRunner().invoke(cli, ['verify', pkg])
    assert result.exit_code == 2 and 'Traceback' not in result.output
    with pytest.raises(PackageInvalid):
        pack(pkg, output=str(tmp_path / 'p.kms.zip'))


def test_a_record_of_the_wrong_shape_is_a_problem(pkg):
    os.makedirs(os.path.join(pkg, '.kms'))
    with open(record_path(pkg), 'w', encoding='utf-8') as handle:
        handle.write('releases: just a string\n')
    assert any('releases.yaml' in m for m in _messages(check(pkg)))


# --- nits ------------------------------------------------------------------------------

@pytest.fixture
def publishable(pkg):
    with open(os.path.join(pkg, 'kms.yaml'), 'a', encoding='utf-8') as handle:
        handle.write('\ntests:\n  coverage: 5\n')
    return pkg


def test_publish_records_what_it_packed(publishable, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    published = publish(publishable, output=out, today=datetime.date(2026, 11, 9))
    assert verify(out).digest == published.digest
    assert read_record(record_path(publishable))[0]['digest'] == published.digest
    assert not glob.glob(str(tmp_path / '*.part'))


def test_a_refused_publish_leaves_no_archive(pkg, tmp_path):
    from semforge.package.releases import PublishRefused
    with pytest.raises(PublishRefused):
        publish(pkg, output=str(tmp_path / 'p.kms.zip'))
    assert not glob.glob(str(tmp_path / '*.kms.zip*'))


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads everything')
def test_an_unreadable_member_of_a_published_version(publishable, tmp_path):
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=datetime.date(2026, 11, 9))
    target = os.path.join(publishable, 'shacl.ttl')
    os.chmod(target, 0)
    try:
        assert any('cannot be read' in m for m in _messages(check(publishable, parse=False)))
    finally:
        os.chmod(target, 0o644)
