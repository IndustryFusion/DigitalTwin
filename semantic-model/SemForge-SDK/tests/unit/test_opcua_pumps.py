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

"""What the OPC UA tool chain writes, through SemForge (tests/corpus/opcua-pumps).

The corpus is a slice of the pump example as the OPC UA tools write it
(tests/corpus/slice_opcua.py): its shapes, model and cases verbatim, its
knowledge a directory of five files cut down to what they name. Every
Variable is `sh:or ( [hasValue …] [hasValueList …] )` -- one value or a list
of the same -- which the kms never says: a valid case written by New test…
came out as "text" for a number, and passed none of its own tests.

With SEMFORGE_OPCUA_KMS pointing at a whole OPC UA package, the timings are
checked on it too: New test… took 10 s there.
"""

import os
import shutil
import time

import pytest

PUMPS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus', 'opcua-pumps'))
PUMP = 'http://opcfoundation.org/UA/Pumps/'
# Types whose attributes are each a Variable: one value or a list of them.
MEASURED = [PUMP + 'DriveMeasurementsType', PUMP + 'OutletConnectionMeasurementsType',
            PUMP + 'MeasurementsType']


@pytest.fixture(scope='module')
def pumps():
    from semforge.package import load
    return load(PUMPS)


def _copy(tmp_path):
    from semforge.package import load

    root = tmp_path / 'opcua-pumps'
    shutil.copytree(PUMPS, root, ignore=shutil.ignore_patterns('.semforge'))
    return load(str(root))


def _rows(package, cls):
    from semforge.cooked.typepage import build_type_page
    return build_type_page(package, cls)['attributes']


# --- reading it ---------------------------------------------------------------------

def test_the_knowledge_is_a_directory_of_files(pumps):
    assert [os.path.basename(f) for f in pumps.files('knowledge')] == [
        'core.owl.ttl', 'di.owl.ttl', 'machinery.owl.ttl', 'pumpexample.owl.ttl',
        'pumps.owl.ttl']


def test_every_type_with_shapes_has_a_page(pumps):
    from semforge.cooked.tree import build_tree

    types = [node.target_class for node in build_tree(pumps) if node.children]
    assert len(types) >= 40, len(types)
    for cls in types:
        rows = _rows(pumps, cls)
        assert all(r['value'] for r in rows if not r.get('inherited')), cls


@pytest.mark.parametrize('cls', MEASURED)
def test_a_variable_is_one_value_or_a_list_of_them(pumps, cls):
    rows = [r for r in _rows(pumps, cls) if not r.get('inherited')]
    assert rows, cls
    variables = [r for r in rows if r.get('kinds') == ['Property', 'ListProperty']]
    assert variables, [(r['label'], r.get('kinds')) for r in rows]
    for row in variables:
        assert row['value'].endswith(', or a list of them (possibly empty)'), row['value']
        assert [f['payload'] for f in row['forms']] == ['hasValue', 'hasValueList']


def test_the_value_editor_reads_both_forms(pumps):
    from rdflib import URIRef

    from semforge.cooked.valueforms import read_value, to_payload

    row = next(r for r in _rows(pumps, PUMP + 'DriveMeasurementsType')
               if r['label'] == 'hasVoltage')
    holder = pumps.index('shapes').file_for(URIRef(row['shape']))
    with open(holder, encoding='utf-8') as handle:
        payload = to_payload(read_value(pumps, handle.read(), row['shape'], row['path']))
    assert payload['editable'], payload['reason']
    assert [f['payload'] for f in payload['forms']] == ['ngsi-ld:hasValue',
                                                        'ngsi-ld:hasValueList']
    assert payload['lists'] == 'allowed'
    assert payload['said'] == 'number, or a list of them (possibly empty)'


def test_its_own_cases_pass(pumps):
    from semforge.expect.runner import run_tests
    from semforge.expect.store import compose, load_expectations
    from semforge.sanity import known_constraints
    from semforge.validate.orchestrator import validate_graphs

    examples = load_expectations(pumps.path).examples
    assert len(examples) >= 3
    reports = [(e, validate_graphs(compose(pumps, e), pumps.shapes, pumps.knowledge,
                                   strict=False)) for e in examples]
    outcomes = run_tests(reports, known_constraints(pumps))
    assert all(o.passed for o in outcomes), [(o.example, o.failures) for o in outcomes]


# --- New test… on it ----------------------------------------------------------------

@pytest.mark.parametrize('cls', MEASURED)
def test_a_valid_case_is_valid(tmp_path, cls):
    """New test… → valid: a number where the Variable is a number."""
    from semforge.expect.attributecase import new_attribute_test

    package = _copy(tmp_path)
    for row in [r for r in _rows(package, cls) if not r.get('inherited')][:3]:
        made = new_attribute_test(package, cls, row['path'], 'valid', f'valid {row["label"]}')
        assert made['passes'], (row['label'], made['failures'])


def test_every_automatic_case_proves_what_it_says(tmp_path):
    """Each constraint New test… offers to make fire, on a Variable: the case
    it writes violates that constraint and passes."""
    from semforge.expect.attributecase import attribute_test_options, new_attribute_test

    package = _copy(tmp_path)
    cls = PUMP + 'DriveMeasurementsType'
    row = next(r for r in _rows(package, cls) if r['label'] == 'hasVoltage')
    options = attribute_test_options(package, cls, row['path'])['options']
    automatic = [o for o in options if o['automatic'] and o['purpose'] != 'valid']
    assert automatic, options
    for number, option in enumerate(automatic):
        made = new_attribute_test(package, cls, row['path'], option['purpose'],
                                  f'fires {number}')
        assert made['passes'], (option['label'], made['failures'])


# --- how long it takes ----------------------------------------------------------------

def _timed(package, cls, label):
    from semforge.expect.attributecase import attribute_test_options, new_attribute_test

    row = next(r for r in _rows(package, cls) if not r.get('inherited'))
    start = time.perf_counter()
    attribute_test_options(package, cls, row['path'])
    new_attribute_test(package, cls, row['path'], 'valid', label)
    return time.perf_counter() - start


def test_new_test_does_not_read_the_package_again(tmp_path, monkeypatch):
    """The case is files under examples/: the knowledge and the shapes are the
    graphs already loaded -- reading them again was 7.5 s on the full pumps."""
    from semforge.package import graphcache

    package = _copy(tmp_path)
    _rows(package, MEASURED[0])
    parsed = []
    real = graphcache.parse_turtle
    monkeypatch.setattr(graphcache, 'parse_turtle',
                        lambda *args, **kwargs: parsed.append(args[1]) or real(*args, **kwargs))
    _timed(package, MEASURED[0], 'not again')
    assert parsed == []


@pytest.mark.skipif(not os.environ.get('SEMFORGE_OPCUA_KMS'),
                    reason='SEMFORGE_OPCUA_KMS names a whole OPC UA package to time')
def test_on_the_whole_package_new_test_takes_seconds_not_ten(tmp_path):
    from semforge.package import load

    root = tmp_path / 'kms'
    shutil.copytree(os.environ['SEMFORGE_OPCUA_KMS'], root,
                    ignore=shutil.ignore_patterns('examples'))
    package = load(str(root))
    _rows(package, MEASURED[0])                    # the page the click comes from
    _timed(package, MEASURED[0], 'warm up')
    assert _timed(package, MEASURED[0], 'timed') < 3.0
