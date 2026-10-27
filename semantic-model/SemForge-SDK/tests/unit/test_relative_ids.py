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

"""An entity whose id is not an IRI: its violations still reach it.

An OPC UA package wrote ids like `sn1234c3Z1PX...`. JSON-LD resolved them
against the reading process's directory -- `file:///.../SemForge-SDK/sn1234...`
-- so the two violations of the Main model were counted and attached to no
card, no row and no tree entry: every way to them led nowhere. Read against
one base and reported as written, they reach their rows; and sanity says the
ids are not IRIs, once per file.
"""

import os
import shutil

import pytest

RELATIVE = 'cutter1'


@pytest.fixture
def package(tmp_path, corpus_path):
    from semforge.package import load

    root = tmp_path / 'kms'
    shutil.copytree(corpus_path, root, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    model = root / 'model-instance.jsonld'
    model.write_text(model.read_text().replace('"id": "urn:cutter:1"', f'"id": "{RELATIVE}"', 1))
    return load(str(root))


@pytest.fixture
def verdicts(package):
    from semforge.editor.verdicts import compute
    return compute(package, 'x')


def test_a_violation_names_the_id_as_written(verdicts):
    resources = {r.resource for r in verdicts.model.violations}
    assert RELATIVE in resources, resources
    assert not any(r.startswith(('file:', 'https://relative')) for r in resources), resources


def test_it_reaches_its_card_on_the_main_page(package, verdicts):
    from semforge.cooked.casepage import build_model_page

    page = build_model_page(package, verdicts)
    card = next(c for f in page['files'] for c in f['cards'] if c['id'] == RELATIVE)
    assert [v['text'] for v in card['violations']] == ['hasXXXWorkpiece is required but missing']


def test_it_is_a_problem_on_its_line_and_the_id_is_one_too(package, verdicts):
    from semforge.editor.analysis import analyse

    found, _ = analyse(package.path, package=package, verdicts=verdicts)
    items = found[os.path.abspath(package.sources['model'])]
    assert any(f.kind == 'violation' and f.subject == RELATIVE for f in items)
    [not_iri] = [f for f in items if f.code == 'id-not-iri']
    assert not_iri.severity == 'error' and f'"{RELATIVE}" is not an IRI' in not_iri.message


def test_the_type_page_counts_it(package, verdicts):
    from semforge.cooked.typepage import build_type_page

    page = build_type_page(package, 'iffBaseEntities:Machine', verdicts)
    row = next(r for r in page['attributes'] if r['label'] == 'hasXXXWorkpiece')
    assert RELATIVE in row['violations'], row['violations']


def test_many_relative_ids_are_one_finding(tmp_path, corpus_path):
    from semforge.package import load
    from semforge.sanity import sanity

    root = tmp_path / 'kms'
    shutil.copytree(corpus_path, root, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    model = root / 'model-instance.jsonld'
    # Every entity's: urn:cutter:1 -> cutter1, which has no scheme.
    import re
    model.write_text(re.sub(r'"id": "urn:([\w-]+):(\w+)"', r'"id": "\1\2"', model.read_text()))
    found = [f for f in sanity(load(str(root))) if f.code == 'id-not-iri']
    assert len(found) == 1, found
    assert 'entity ids in this file are not IRIs' in found[0].message
