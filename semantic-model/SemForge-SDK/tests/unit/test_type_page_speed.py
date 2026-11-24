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

"""What made a type page slow: 14 s on a large OPC UA package, and more with
every test case. Each shape without a class target, for the model and each
case, walked the whole shapes graph to see which shapes use it."""

import json
import os
import time

import pytest
from rdflib import Graph
from rdflib.namespace import SH

import scale_package
from semforge.cooked.shapes import every_node_shape, used_by
from semforge.cooked.typepage import build_type_page
from semforge.editor import cache
from semforge.package import load
from semforge.rdfio import turtle_index

USING = '''
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix x: <http://x/> .
x:A a sh:NodeShape ; sh:property [ sh:path x:p ; sh:or ( [ sh:node x:T ] [ sh:node x:U ] ) ] .
x:B a sh:NodeShape ; sh:node x:T , x:B .
x:C a sh:NodeShape ; sh:property x:P .
x:P sh:path x:q ; sh:node x:T .
x:T a sh:NodeShape . x:U a sh:NodeShape .
'''


class _Package:
    def __init__(self, graph):
        self.shapes = graph


@pytest.mark.parametrize('package', ['made', 'targets', 'corpus'])
def test_the_shapes_using_a_shape_are_those_whose_body_names_it(package, request):
    held = _Package(Graph().parse(data=USING, format='turtle')) if package == 'made' \
        else request.getfixturevalue(package)
    graph = held.shapes
    for shape in every_node_shape(graph):
        walked = [str(other) for other in every_node_shape(graph) if other != shape and
                  any(p == SH.node and o == shape for _, p, o in graph.cbd(other))]
        assert used_by(held, shape) == walked, shape


def test_a_page_of_a_large_package_with_untargeted_shapes_and_cases(tmp_path):
    """The chain a click takes, on a generated package: 300 types, ten shapes
    without a class target, five cases."""
    root = scale_package.make(str(tmp_path / 'pkg'), 300, 100)
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        for number in range(10):
            handle.write(f'\n<http://x/Extra{number}> a <http://www.w3.org/ns/shacl#NodeShape> ; '
                         f'<http://www.w3.org/ns/shacl#property> [ <http://www.w3.org/ns/shacl#path> '
                         f'<http://x/p{number}> ; <http://www.w3.org/ns/shacl#maxCount> 1 ] .\n')
    good = os.path.join(root, 'examples', 'test_Extra', 'good')
    os.makedirs(good)
    with open(os.path.join(root, 'model-instance.jsonld'), encoding='utf-8') as handle:
        entity = json.load(handle)[0]
    for number in range(5):
        with open(os.path.join(good, f'c{number}.jsonld'), 'w', encoding='utf-8') as handle:
            json.dump([entity], handle)
    with open(os.path.join(good, 'expectations.yaml'), 'w', encoding='utf-8') as handle:
        handle.write('examples:\n' + ''.join(f'  - path: c{n}.jsonld\n    expect: valid\n' for n in range(5)))
    package = load(root)

    from semforge.editor.verdicts import Verdicts
    from semforge.validate.results import Report
    verdicts = Verdicts('x', Report(), {f'test_Extra/good/c{n}.jsonld': Report() for n in range(5)})
    wanted = scale_package.ENTITIES + 'GenType0'
    build_type_page(package, wanted, verdicts)           # what is derived once per package
    started = time.perf_counter()
    page = build_type_page(package, wanted, verdicts)
    seconds = time.perf_counter() - started
    assert page['label'] == 'GenType0' and len(page['exercisedBy']) in (0, 5)
    assert seconds < 1.5, f'{seconds:.1f} s'


def test_a_cached_view_is_written_by_the_fast_encoder_and_reads_back(tmp_path, monkeypatch):
    def slow(*args, **kwargs):
        raise AssertionError('json.dump: the slow encoder')
    monkeypatch.setattr(cache.json, 'dump', slow)
    payload = {'roots': [{'label': 'Grün', 'children': [None, 1.5, True]}]}
    cache.store(str(tmp_path), 'view', payload, 'stamp')
    assert cache.load(str(tmp_path), 'view', 'stamp') == payload


def test_one_text_is_split_into_statements_once():
    turtle_index._statement_spans.cache_clear()
    text = USING + '# asked for three times'
    for _ in range(3):
        spans = turtle_index._statement_spans(text)
    assert isinstance(spans, tuple) and turtle_index._statement_spans.cache_info().misses == 1
