#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""tests/e2e-kms/without_shapes.py: the e2e KMS for SPARQL_ENGINE=ladder."""
import importlib.util
import re
from pathlib import Path

import pytest
import rdflib
from rdflib import SH

HERE = Path(__file__).resolve().parent
KMS = HERE / 'e2e-kms'
spec = importlib.util.spec_from_file_location('without_shapes', KMS / 'without_shapes.py')
without_shapes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(without_shapes)

DROPPED = 'E2EQueryAnyAttributeShape'


def shapes(graph):
    return {str(s).rsplit('/', 1)[-1] for s in graph.subjects(rdflib.RDF.type, SH.NodeShape)}


def test_the_copy_lacks_the_shape_and_nothing_else(tmp_path):
    without_shapes.main(str(KMS), str(tmp_path / 'kms'), [DROPPED])
    original = rdflib.Graph().parse(KMS / 'shacl.ttl')
    copy = rdflib.Graph().parse(tmp_path / 'kms' / 'shacl.ttl')
    assert DROPPED in shapes(original)
    assert shapes(copy) == shapes(original) - {DROPPED}
    # the blank nodes the shape held go with it: its query is nowhere left
    assert 'NOT IN (e:hasE2EUpper' not in (tmp_path / 'kms' / 'shacl.ttl').read_text()
    assert len(copy) < len(original)
    for name in ('knowledge.ttl', 'model-instance.jsonld'):
        assert (tmp_path / 'kms' / name).read_bytes() == (KMS / name).read_bytes()
    assert not list((tmp_path / 'kms').glob('*.py'))


def test_the_copy_is_the_original_text_without_one_block(tmp_path):
    """The deploy suite edits the package as text (changed_package): every other
    line stays as it was, in its place."""
    without_shapes.main(str(KMS), str(tmp_path / 'kms'), [DROPPED])
    original = (KMS / 'shacl.ttl').read_text().splitlines()
    copy = (tmp_path / 'kms' / 'shacl.ttl').read_text().splitlines()
    start = next(i for i, line in enumerate(original) if line.startswith(f':{DROPPED} '))
    removed = len(original) - len(copy)
    assert removed > 1
    assert copy == original[:start] + original[start + removed:]
    # the line changed_package edits is the cartridge's own, as in the original
    cartridge = next(i for i, line in enumerate(copy) if 'hasE2ECartridge' in line)
    assert any('sh:maxCount 1 ;' in line for line in copy[cartridge:cartridge + 4])


def test_a_line_of_a_query_ending_with_a_dot_does_not_end_the_block():
    text = (':Kept a sh:NodeShape .\n'
            ':Gone a sh:NodeShape ;\n'
            '    sh:sparql [ sh:select """\n'
            'SELECT $this WHERE {\n'
            '    $this ex:p ?o .\n'
            '}\n'
            '""" ] .\n'
            '\n'
            '# the next one\n'
            ':Also a sh:NodeShape .\n')
    # the blank line after a block goes with it
    assert without_shapes.without_text(text, ['Gone']) == (':Kept a sh:NodeShape .\n# the next one\n'
                                                           ':Also a sh:NodeShape .\n')


def test_a_shape_that_is_not_there_is_an_error(tmp_path):
    with pytest.raises(SystemExit, match='not in the KMS: NoSuchShape'):
        without_shapes.main(str(KMS), str(tmp_path / 'kms'), ['NoSuchShape'])


def test_the_makefile_names_only_shapes_the_ladder_refuses():
    """LADDER_REFUSED_E2E: each shape there is refused by the ladder, and is in the KMS."""
    import lib.sparql_ladder as ladder
    import lib.sparql_to_sql as classic
    import lib.utils as utils
    named = re.search(r'^LADDER_REFUSED_E2E := (.*)$', (HERE.parent / 'Makefile').read_text(), re.M)[1].split()
    graph = utils.transitive_closure(utils.load_graph(str(KMS / 'shacl.ttl'), str(KMS / 'knowledge.ttl')))
    classic.read_attributes(graph)
    refused = set()
    for shape in graph.subjects(SH.sparql, None):
        for node in graph.objects(shape, SH.sparql):
            query = ladder.Query(set(classic.relationships))
            try:
                query.finish(query.tree(ladder.parse(str(graph.value(node, SH.select)))))
            except ladder.UnsupportedQuery:
                refused.add(str(shape).rsplit('/', 1)[-1])
    assert set(named) == refused
