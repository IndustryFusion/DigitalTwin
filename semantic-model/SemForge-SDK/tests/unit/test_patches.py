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

"""An edit is verified on what it changed, and the reload patches the graph.

On the OPC UA pump shapes (21,000 lines) every click in the value editor
parsed the whole file twice: once to verify the write, once to reload it.
Both now read only the statements the edit touched -- and must say exactly
what parsing the whole file would.
"""

import gc
import shutil
import weakref

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from semforge.cooked.tree import _changed_statements, _write_verified
from semforge.errors import PackageError
from semforge.package import patches

FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/FilterShape'
CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/CutterShape'

TEXT = '''@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

ex:A a sh:NodeShape ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .

ex:B a sh:NodeShape ; sh:property [ sh:path ex:b ; sh:maxCount 2 ] .
'''


@pytest.fixture
def root(tmp_path, corpus):
    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    return root


def test_only_the_statements_an_edit_touched_are_read():
    new = TEXT.replace('sh:minCount 1', 'sh:minCount 1 ; sh:maxCount 3')
    changed, before = _changed_statements(TEXT, new)
    assert 'ex:A a sh:NodeShape' in changed and 'ex:B' not in changed
    assert 'sh:maxCount 3' in changed and 'sh:maxCount 3' not in before
    assert changed.startswith('@prefix ex: <https://example.org/> .')


@pytest.mark.parametrize('edit', [
    lambda t: t.replace('@prefix ex: <https://example.org/> .',
                        '@prefix ex: <https://example.org/x/> .'),    # a prefix
    lambda t: t + '\nex:C a sh:NodeShape .\n',                           # between statements
    lambda t: t,                                                         # nothing
])
def test_what_cannot_be_said_locally_is_read_whole(edit):
    assert _changed_statements(TEXT, edit(TEXT)) is None


def test_a_broken_edit_is_refused_and_the_file_kept(tmp_path):
    path = tmp_path / 'shapes.ttl'
    path.write_text(TEXT)
    with pytest.raises(Exception):
        _write_verified(str(path), TEXT.replace('sh:minCount 1 ]', 'sh:minCount 1'))
    with pytest.raises(PackageError, match='at least 5'):
        _write_verified(str(path), TEXT.replace('sh:maxCount 2', 'sh:maxCount 2 ; sh:minCount 5'))
    assert path.read_text() == TEXT


def test_the_patched_graph_is_the_parsed_one(root):
    from semforge.cooked.valueforms import edit_value
    from semforge.package import load

    shapes = root / 'shacl.ttl'
    for action in ({'op': 'addform', 'kind': 'ListProperty'},
                   {'op': 'set', 'form': 1, 'node': [0], 'parameter': 'sh:datatype',
                    'value': 'xsd:integer'},
                   {'op': 'removeform', 'form': 1}):
        before = load(str(root))
        edit_value(before, FILTER, ['iffBaseEntities:hasStrength'], action)
        patched = patches.patched(str(shapes), before.shapes)
        assert patched is not None, action
        assert isomorphic(patched, Graph().parse(str(shapes), format='turtle')), action


def test_a_file_changed_since_is_parsed_again(root):
    from semforge.cooked.valueforms import edit_value
    from semforge.package import load

    shapes = root / 'shacl.ttl'
    before = load(str(root))
    edit_value(before, CUTTER, ['iffBaseEntities:hasList'], {'op': 'addform', 'kind': 'JsonProperty'})
    shapes.write_text(shapes.read_text() + '\n# by hand\n')
    assert patches.patched(str(shapes), before.shapes) is None


def test_a_replaced_graph_is_freed_once_the_edits_are_quiet():
    from semforge.editor import session

    graph = Graph()
    graph.add((graph.identifier, graph.identifier, graph.identifier))
    gone = weakref.ref(graph)
    gc.freeze()                   # as after a load: everything there is, frozen
    try:
        del graph
        assert gone() is not None, 'a frozen cycle is not collected'
        session._tidy()
        assert gone() is None
    finally:
        gc.unfreeze()
