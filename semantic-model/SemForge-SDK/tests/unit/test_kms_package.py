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

"""The KMS package contract (openspec change gh-939-kms-package).

One test per scenario of `contracts/kms-package` and
`semforge-sdk/package-tools`, named after it where that is possible.
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import zipfile

import pytest
from click.testing import CliRunner

from semforge.cli.main import cli
from semforge.package import load
from semforge.package.archive import PackageInvalid, pack, verify, verify_directory
from semforge.package.conformance import SUMS, check
from semforge.package.scaffold import create_package

HERE = os.path.dirname(os.path.abspath(__file__))
KMS_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'kms'))
KMS = os.path.join(KMS_DIR, 'default')

TTL = '@prefix ex: <https://example.org/> .\nex:a ex:b ex:c .\n'
DESCRIPTOR = 'name: demo\nversion: 1.0.0\nformat: 1\n'


def _write(root, rel, text):
    path = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return path


@pytest.fixture
def pkg(tmp_path):
    """A minimal package that satisfies the contract and nothing more."""
    root = str(tmp_path / 'demo')
    _write(root, 'kms.yaml', DESCRIPTOR)
    _write(root, 'knowledge.ttl', TTL)
    _write(root, 'shacl.ttl', TTL)
    _write(root, 'model-instance.jsonld', '[]\n')
    return root


def _messages(report):
    return [str(p) for p in report.problems]


# --- A package is a directory with a descriptor -------------------------------

def test_complete_descriptor(pkg):
    report = check(pkg)
    assert report.ok, _messages(report)
    assert (report.name, report.version) == ('demo', '1.0.0')


def test_descriptor_without_a_version(pkg):
    _write(pkg, 'kms.yaml', 'name: demo\nformat: 1\n')
    assert any('no version' in m for m in _messages(check(pkg)))


def test_newer_format(pkg):
    _write(pkg, 'kms.yaml', 'name: demo\nversion: 1.0.0\nformat: 2\n')
    assert any('format 2 is not supported' in m for m in _messages(check(pkg)))


# --- Roles ---------------------------------------------------------------------

def test_shapes_split_over_several_files(pkg, tmp_path):
    os.unlink(os.path.join(pkg, 'shacl.ttl'))
    _write(pkg, 'shacl/base.ttl', TTL)
    _write(pkg, 'shacl/filter.ttl', TTL.replace('ex:c', 'ex:d'))
    report = check(pkg)
    assert report.ok, _messages(report)
    assert report.roles['shacl'] == ['shacl/base.ttl', 'shacl/filter.ttl']


def test_model_grouped_under_model(pkg):
    shutil.move(os.path.join(pkg, 'model-instance.jsonld'),
                _write(pkg, 'model/model-instance.jsonld', ''))
    report = check(pkg)
    assert report.ok, _messages(report)
    assert report.roles['model-instance'] == ['model/model-instance.jsonld']


def test_nested_directory_in_a_role_directory(pkg):
    os.unlink(os.path.join(pkg, 'model-instance.jsonld'))
    _write(pkg, 'model-instance/plant.jsonld', '[]')
    _write(pkg, 'model-instance/drafts/other.jsonld', '[]')
    report = check(pkg)
    assert report.ok, _messages(report)
    assert report.roles['model-instance'] == ['model-instance/plant.jsonld']
    assert 'model-instance/drafts/' in report.left_out


def test_file_and_directory_for_one_role(pkg):
    _write(pkg, 'knowledge/extra.ttl', TTL)
    problems = _messages(check(pkg))
    assert any('knowledge.ttl' in m and 'knowledge' in m and 'more than once' in m
               for m in problems), problems


def test_missing_role(pkg):
    os.unlink(os.path.join(pkg, 'model-instance.jsonld'))
    assert any('missing role model-instance' in m for m in _messages(check(pkg)))


def test_unparsable_document(pkg):
    os.unlink(os.path.join(pkg, 'knowledge.ttl'))
    _write(pkg, 'knowledge/good.ttl', TTL)
    _write(pkg, 'knowledge/extra.ttl', 'this is not turtle')
    assert any(m.startswith('knowledge/extra.ttl: does not parse')
               for m in _messages(check(pkg)))


def test_empty_role_directory(pkg):
    os.unlink(os.path.join(pkg, 'shacl.ttl'))
    os.makedirs(os.path.join(pkg, 'shacl'))
    assert any('holds no .ttl' in m for m in _messages(check(pkg)))


# --- Examples, standalone, members ------------------------------------------------

def test_grouped_layout_keeps_examples_out_of_the_model(pkg):
    shutil.move(os.path.join(pkg, 'model-instance.jsonld'),
                _write(pkg, 'model/model-instance.jsonld', ''))
    _write(pkg, 'model/examples/test_FilterShape/bad/without-cartridge.jsonld', '[]')
    report = check(pkg)
    assert report.ok, _messages(report)
    assert report.roles['model-instance'] == ['model/model-instance.jsonld']
    assert 'model/examples/test_FilterShape/bad/without-cartridge.jsonld' in report.members


def test_two_examples_suites(pkg):
    _write(pkg, 'examples/a.jsonld', '[]')
    _write(pkg, 'model/examples/b.jsonld', '[]')
    assert any('two examples suites' in m for m in _messages(check(pkg)))


def test_vocabulary_outside_the_package(pkg):
    _write(pkg, 'kms.yaml', DESCRIPTOR + 'ngsild:\n  source: ../ontology/ngsild.ttl\n')
    assert any('leaves the package root' in m for m in _messages(check(pkg)))


def test_vocabulary_inside_the_package_is_a_member(pkg):
    _write(pkg, 'kms.yaml', DESCRIPTOR + 'ngsild:\n  source: vocabulary/ngsild.ttl\n')
    _write(pkg, 'vocabulary/ngsild.ttl', TTL)
    report = check(pkg)
    assert report.ok, _messages(report)
    assert 'vocabulary/ngsild.ttl' in report.members


def test_derived_file_beside_the_roles(pkg):
    _write(pkg, 'model-instance.scorpio.jsonld', '[]')
    _write(pkg, 'README.md', '# demo\n')
    report = check(pkg)
    assert 'model-instance.scorpio.jsonld' in report.left_out
    assert 'README.md' in report.members


def test_tool_state(pkg):
    _write(pkg, '.semforge/cache/graphs/x', 'cached')
    _write(pkg, '.kms/releases.yaml', 'releases: []\n')
    report = check(pkg)
    assert not any(m.startswith(('.semforge', '.kms'))
                   for m in report.members + report.left_out)


def test_legacy_descriptor(pkg):
    os.rename(os.path.join(pkg, 'kms.yaml'), os.path.join(pkg, 'semforge.yaml'))
    problems = _messages(check(pkg))
    assert any(m.startswith('semforge.yaml: ') and 'kms.yaml' in m
               for m in problems), problems
    load(pkg)                        # the SDK itself still reads it


def test_legacy_format_key(pkg):
    _write(pkg, 'kms.yaml', 'name: demo\nversion: 1.0.0\nkmsPackage: 1\n')
    assert any('kmsPackage is not a key' in m for m in _messages(check(pkg)))


def test_two_descriptors(pkg):
    _write(pkg, 'semforge.yaml', DESCRIPTOR)
    assert any('two descriptors' in m for m in _messages(check(pkg)))


@pytest.mark.parametrize('value', ['101', '-1', 'lots', 'true'])
def test_coverage_threshold_must_be_a_percentage(pkg, value):
    _write(pkg, 'kms.yaml', DESCRIPTOR + f'tests:\n  coverage: {value}\n')
    assert any('tests.coverage must be a percentage' in m for m in _messages(check(pkg)))


def test_coverage_threshold_defaults_to_80(pkg):
    assert check(pkg).coverage_threshold == 80
    _write(pkg, 'kms.yaml', DESCRIPTOR + 'tests:\n  coverage: 60\n')
    assert check(pkg).coverage_threshold == 60


def test_legacy_shapes_directory(pkg):
    os.unlink(os.path.join(pkg, 'shacl.ttl'))
    _write(pkg, 'shapes/base.ttl', TTL)
    problems = _messages(check(pkg))
    assert any(m.startswith('shapes: ') and 'shacl/' in m for m in problems), problems
    load(pkg)                        # the SDK itself still reads it


# --- The distribution form ----------------------------------------------------------

def test_name_of_the_file(pkg, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    packed = pack(pkg)
    assert os.path.basename(packed.path) == 'demo-1.0.0.kms.zip'


def test_sums_are_first_and_complete(pkg, tmp_path):
    packed = pack(pkg, output=str(tmp_path / 'p.zip'))
    with zipfile.ZipFile(packed.path) as archive:
        names = archive.namelist()
        sums = archive.read(SUMS).decode()
        infos = archive.infolist()
    assert names[0] == SUMS
    assert names[1:] == sorted(names[1:], key=str.encode)
    assert [line.split('  ', 1)[1] for line in sums.splitlines()] == names[1:]
    assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in infos)
    assert all(stat.S_ISREG(i.external_attr >> 16) for i in infos)


def test_checking_with_standard_tools(pkg, tmp_path):
    packed = pack(pkg, output=str(tmp_path / 'p.zip'))
    out = tmp_path / 'x'
    with zipfile.ZipFile(packed.path) as archive:
        archive.extractall(out)
    if shutil.which('sha256sum') is None:
        pytest.skip('no sha256sum')
    done = subprocess.run(['sha256sum', '-c', SUMS], cwd=out,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_same_content_different_archive(pkg, tmp_path):
    a = pack(pkg, output=str(tmp_path / 'a.zip'), compress=True)
    b = pack(pkg, output=str(tmp_path / 'b.zip'), compress=False)
    assert a.digest == b.digest
    with zipfile.ZipFile(a.path) as archive:
        sums = archive.read(SUMS)
    assert a.digest == 'sha256:' + hashlib.sha256(sums).hexdigest()


def test_one_changed_byte(pkg, tmp_path):
    before = pack(pkg, output=str(tmp_path / 'a.zip')).digest
    _write(pkg, 'shacl.ttl', TTL.replace('ex:c', 'ex:e'))
    assert pack(pkg, output=str(tmp_path / 'b.zip')).digest != before


def test_pack_twice(pkg, tmp_path):
    a = pack(pkg, output=str(tmp_path / 'a.zip'))
    b = pack(pkg, output=str(tmp_path / 'b.zip'))
    with open(a.path, 'rb') as x, open(b.path, 'rb') as y:
        assert x.read() == y.read()


def test_packing_an_invalid_package(pkg, tmp_path):
    _write(pkg, 'kms.yaml', 'name: demo\nformat: 1\n')
    with pytest.raises(PackageInvalid):
        pack(pkg, output=str(tmp_path / 'p.zip'))
    assert not os.path.exists(tmp_path / 'p.zip')


# --- Verification -------------------------------------------------------------------

def _rewrite(source, target, change):
    """Copy an archive entry by entry, letting `change` alter the list of
    (ZipInfo, bytes) -- a forger with a zip tool, not with our packer."""
    with zipfile.ZipFile(source) as archive:
        entries = [(i, archive.read(i)) for i in archive.infolist()]
    entries = change(entries)
    with zipfile.ZipFile(target, 'w') as archive:
        for info, data in entries:
            archive.writestr(info, data)
    return target


@pytest.fixture
def packed(pkg, tmp_path):
    return pack(pkg, output=str(tmp_path / 'demo.zip'))


def test_valid_archive(packed, pkg, tmp_path):
    result = verify(packed.path, into=str(tmp_path / 'tree'))
    assert result.ok, result.problems
    assert (result.name, result.version, result.digest) == \
        ('demo', '1.0.0', packed.digest)
    a, b = load(pkg), load(result.tree)
    for role in ('knowledge', 'shapes', 'model'):
        assert len(getattr(a, role)) == len(getattr(b, role))


def test_directory_and_archive_agree(packed, pkg):
    assert verify_directory(pkg).digest == verify(packed.path).digest == packed.digest


def test_modified_member(packed, tmp_path):
    def change(entries):
        return [(i, d.replace(b'ex:c', b'ex:X') if i.filename == 'knowledge.ttl' else d)
                for i, d in entries]
    result = verify(_rewrite(packed.path, str(tmp_path / 't.zip'), change))
    assert not result.ok
    assert [p.path for p in result.problems] == ['knowledge.ttl']


def test_added_file(packed, tmp_path):
    def change(entries):
        return entries + [(zipfile.ZipInfo('extra.ttl'), TTL.encode())]
    result = verify(_rewrite(packed.path, str(tmp_path / 't.zip'), change))
    assert [p.path for p in result.problems] == ['extra.ttl']


def test_removed_file(packed, tmp_path):
    def change(entries):
        return [(i, d) for i, d in entries if i.filename != 'shacl.ttl']
    result = verify(_rewrite(packed.path, str(tmp_path / 't.zip'), change))
    assert [p.path for p in result.problems] == ['shacl.ttl']


def test_missing_sums(packed, tmp_path):
    def change(entries):
        return [(i, d) for i, d in entries if i.filename != SUMS]
    result = verify(_rewrite(packed.path, str(tmp_path / 't.zip'), change))
    assert [p.path for p in result.problems] == [SUMS]


def test_path_escaping_the_package(packed, tmp_path):
    evil = TTL.encode()

    def change(entries):
        sums = [d for i, d in entries if i.filename == SUMS][0]
        line = f'{hashlib.sha256(evil).hexdigest()}  ../evil.ttl\n'.encode()
        rest = [(i, d) for i, d in entries if i.filename != SUMS]
        return [(zipfile.ZipInfo(SUMS), line + sums)] + rest + \
            [(zipfile.ZipInfo('../evil.ttl'), evil)]
    target = tmp_path / 'deep' / 'nested'
    target.parent.mkdir()
    result = verify(_rewrite(packed.path, str(tmp_path / 't.zip'), change),
                    into=str(target))
    assert not result.ok
    assert any(p.path == '../evil.ttl' for p in result.problems)
    assert not (tmp_path / 'deep' / 'evil.ttl').exists()
    assert not target.exists()


def test_link_entry(packed, tmp_path):
    def change(entries):
        link = zipfile.ZipInfo('knowledge.ttl')
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        return [(link, b'/etc/passwd') if i.filename == 'knowledge.ttl' else (i, d)
                for i, d in entries]
    result = verify(_rewrite(packed.path, str(tmp_path / 't.zip'), change))
    assert any('link' in p.message for p in result.problems)


def test_oversized_archive(packed):
    result = verify(packed.path, limit=10)
    assert not result.ok and 'exceed the limit' in str(result.problems[0])


def test_consistent_but_invalid_package(pkg, tmp_path):
    # A forger's archive whose SHA256SUMS is right but whose tree is ambiguous.
    target = str(tmp_path / 't.zip')
    files = {'kms.yaml': DESCRIPTOR, 'knowledge.ttl': TTL, 'shacl.ttl': TTL,
             'shacl/base.ttl': TTL, 'model-instance.jsonld': '[]'}
    sums = ''.join(f'{hashlib.sha256(files[n].encode()).hexdigest()}  {n}\n'
                   for n in sorted(files))
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr(SUMS, sums)
        for name, text in files.items():
            archive.writestr(name, text)
    result = verify(target)
    assert not result.ok
    assert any('more than once' in p.message for p in result.problems)


# --- Commands -------------------------------------------------------------------------

def test_cli_pack_and_verify(pkg, tmp_path):
    runner = CliRunner()
    out = str(tmp_path / 'demo.zip')
    packed = runner.invoke(cli, ['pack', pkg, '-o', out])
    assert packed.exit_code == 0, packed.output
    assert 'digest   sha256:' in packed.output
    verified = runner.invoke(cli, ['verify', out, '--format', 'json'])
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)['ok'] is True


def test_cli_tampered_archive(packed, tmp_path):
    def change(entries):
        return [(i, d + b'#' if i.filename == 'shacl.ttl' else d) for i, d in entries]
    target = _rewrite(packed.path, str(tmp_path / 't.zip'), change)
    result = CliRunner().invoke(cli, ['verify', target])
    assert result.exit_code == 2
    assert 'shacl.ttl' in result.output


def test_cli_packing_an_invalid_package(pkg, tmp_path):
    _write(pkg, 'kms.yaml', 'name: demo\nformat: 1\n')
    result = CliRunner().invoke(cli, ['pack', pkg, '-o', str(tmp_path / 'p.zip')])
    assert result.exit_code == 2 and 'no version' in result.output
    assert not os.path.exists(tmp_path / 'p.zip')


def test_edit_an_archive(packed):
    result = CliRunner().invoke(cli, ['accept', packed.path])
    assert result.exit_code == 2 and 'read-only' in result.output


def test_fresh_package_verifies(tmp_path):
    for layout in ('grouped', 'flat'):
        root = tmp_path / layout
        root.mkdir()
        create_package(str(root), name=f'fresh-{layout}', layout=layout)
        report = check(str(root))
        assert report.ok, (layout, _messages(report))
        assert report.version == '0.1.0'


# --- the kms --------------------------------------------------------------------------

def test_the_default_package():
    """kms/default links to kms/example, which is a valid package."""
    assert os.path.islink(KMS) and os.readlink(KMS) == 'example'
    report = check(KMS)
    assert report.ok, _messages(report)
    assert (report.name, report.descriptor) == ('example', 'kms.yaml')
    assert 'model-instance.scorpio.jsonld' in report.left_out


def test_the_kms_directory():
    """One package, the default; the examples beside it are not a package."""
    from semforge.package.discover import packages_below
    assert [(n, d) for n, _, d in packages_below(KMS_DIR)] == [('example', True)]
    assert os.path.isdir(os.path.join(KMS_DIR, 'SchweissenUndSchneiden'))


def test_the_kms_vocabulary_is_the_shared_copy():
    """Standalone means a copy; this keeps the copy from drifting."""
    shared = os.path.join(KMS_DIR, '..', 'ontology', 'ngsild.ttl')
    with open(os.path.join(KMS, 'vocabulary', 'ngsild.ttl'), 'rb') as a, \
            open(shared, 'rb') as b:
        assert a.read() == b.read()


def test_validate_an_archive(tmp_path):
    """`semforge validate` on the kms and on its archive: same verdicts."""
    runner = CliRunner()
    out = str(tmp_path / 'example.kms.zip')
    assert runner.invoke(cli, ['pack', KMS, '-o', out]).exit_code == 0
    direct = runner.invoke(cli, ['validate', KMS])
    packed = runner.invoke(cli, ['validate', out])
    assert direct.exit_code == packed.exit_code

    def verdicts(result):
        # The `package:` line says where it was read from -- the one line
        # that is meant to differ.
        return [line for line in result.output.splitlines()
                if not line.startswith('package: ')]
    assert verdicts(direct) == verdicts(packed)
    assert 'verified archive, read-only' in packed.output


def test_a_legacy_descriptor_still_anchors_discovery(pkg):
    """A package with only semforge.yaml is still found -- and named as such."""
    from semforge.package.discover import find
    os.rename(os.path.join(pkg, 'kms.yaml'), os.path.join(pkg, 'semforge.yaml'))
    os.unlink(os.path.join(pkg, 'shacl.ttl'))          # a role missing
    root, why = find(os.path.join(pkg, 'knowledge.ttl'))
    assert (root, why) == (pkg, 'semforge.yaml')
