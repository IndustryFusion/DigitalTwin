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

"""A number is declared as its shape asks, whatever prefix the data writes the
attribute with, and a decimal in a form that its datatype accepts."""

import json
import re

import pytest

from semforge.cooked.casepage import build_case_page
from semforge.cooked.constrain import add_attribute_constraint
from semforge.cooked.examples import add_attribute, set_value
from semforge.cooked.knowledge import add_attribute_term
from semforge.cooked.tree import build_tree
from semforge.expect.attributecase import new_attribute_test
from semforge.package import load
from semforge.package.scaffold import create_package

XSD = 'http://www.w3.org/2001/XMLSchema#'


def _package(tmp_path, datatype):
    root = str(tmp_path / 'my-model')
    create_package(root)
    machine = str(next(c for c in load(root).knowledge.subjects() if str(c).endswith('/Machine')))
    add_attribute_term(load(root), 'hasMode', 'Property', machine, label='Mode')
    package = load(root)
    shape = str(next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape')))
    add_attribute_constraint(package, shape, 'hasMode', required=False, datatype=datatype)
    path = next(list(a.path_chain) for r in build_tree(load(root)) if r.target_class == machine
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasMode'))
    made = new_attribute_test(load(root), machine, path, 'valid', 'mode')
    with open(made['file']) as handle:
        key = next(k for d in json.load(handle) for k in d if k.endswith('hasMode'))
    return root, made, key


def _value(made, key):
    with open(made['file']) as handle:
        return next(d for d in json.load(handle) if d.get('id') == made['resource'])[key]['value']


def _fired(root, made):
    page = build_case_page(load(root), made['case'])
    return [v['constraint'] for f in page['files'] for c in f['cards']
            for a in c['attributes'] for v in a['violations']]


def _two_prefixes(root, made, key, namespace=None):
    """The shapes say other:hasMode; `other` is the namespace of `key`, unless given."""
    shapes = next(p for p in load(root).files('shapes') if 'hasMode' in open(p).read())
    prefix = key.split(':')[0]
    with open(shapes) as handle:
        text = handle.read()
    own = re.search(rf'@prefix {prefix}: <([^>]*)>', text).group(1)
    with open(shapes, 'w') as handle:
        handle.write(f'@prefix other: <{namespace or own}> .\n'
                     + text.replace(f'{prefix}:hasMode', 'other:hasMode'))


# --- one namespace, two prefixes -----------------------------------------------------------

def test_a_double_is_declared_whatever_prefix_the_shape_uses(tmp_path):
    """The data says a:hasMode, the shape b:hasMode, two prefixes of one namespace:
    50.0 was written plain, an integer."""
    root, made, key = _package(tmp_path, 'xsd:double')
    _two_prefixes(root, made, key)
    set_value(load(root), made['resource'], [key, 'value'], '50.0', made['file'])
    assert _value(made, key) == {'@value': 50.0, '@type': XSD + 'double'}
    assert _fired(root, made) == []

    # The same when it is added, not changed.
    with open(made['file']) as handle:
        scene = json.load(handle)
    del next(d for d in scene if d.get('id') == made['resource'])[key]
    with open(made['file'], 'w') as handle:
        json.dump(scene, handle)
    add_attribute(load(root), made['resource'], key, kind='Property', value='50', file=made['file'])
    assert _value(made, key) == {'@value': 50.0, '@type': XSD + 'double'}


def test_a_decimal_is_one_that_its_datatype_accepts(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:decimal')
    for typed in ('50', '50.0', '50.5'):
        set_value(load(root), made['resource'], [key, 'value'], typed, made['file'])
        assert _fired(root, made) == [], typed


def test_the_type_may_be_written_with_the_other_prefix(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:double')
    with open(made['file']) as handle:
        scene = json.load(handle)
    entity = next(d for d in scene if d.get('id') == made['resource'])
    prefix, name = entity['type'].split(':', 1)
    shapes = next(p for p in load(root).files('shapes') if 'hasMode' in open(p).read())
    with open(shapes) as handle:
        text = handle.read()
    own = re.search(rf'@prefix {prefix}: <([^>]*)>', text).group(1)
    with open(shapes, 'w') as handle:
        handle.write(f'@prefix other: <{own}> .\n' + text)
    entity['type'] = f'other:{name}'
    with open(made['file'], 'w') as handle:
        json.dump(scene, handle)
    set_value(load(root), made['resource'], [key, 'value'], '50.0', made['file'])
    assert _value(made, key) == {'@value': 50.0, '@type': XSD + 'double'}


def test_the_same_name_in_another_namespace_is_another_attribute(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:double')
    _two_prefixes(root, made, key, 'http://example.org/elsewhere/')
    set_value(load(root), made['resource'], [key, 'value'], '50.0', made['file'])
    assert _value(made, key) == 50.0 and not isinstance(_value(made, key), dict)


def test_an_unknown_prefix_is_written_plain(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:double')
    with open(made['file']) as handle:
        text = handle.read()
    with open(made['file'], 'w') as handle:
        handle.write(text.replace(f'"{key}"', '"nobody:hasMode"'))
    set_value(load(root), made['resource'], ['nobody:hasMode', 'value'], '50.0', made['file'])
    assert _value(made, 'nobody:hasMode') == 50.0


@pytest.mark.parametrize('number, said', [(50, '50'), (50.0, '50.0'), (1e-07, '0.0000001'),
                                          (1e22, '10000000000000000000000')])
def test_a_decimal_is_written_without_an_exponent(number, said):
    from semforge.expect.attributecase import declared_value

    assert declared_value(number, XSD + 'decimal') == {'@value': said, '@type': XSD + 'decimal'}
