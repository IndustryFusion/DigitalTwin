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

"""The new-shape flow through the real language server on a large package
(issue #991).

The editor is started as VS Code starts it, on a generated package of the
shape the OPC UA packages have: hundreds of entity types and thousands of
entities sharing one @context. The flow is the one that took 10 to 20 s in the
OPC UA demo package: the type picker, adding a shape, the SHACL Shapes view,
the requests after the edit.

The budgets lie well above what the fixed editor needs and well below what
it needed before, measured through this test: entityTypes 18.0 s before,
0.2 s after; the Knowledge view 16.2 s / 1.6 s; the first request after a
shape edit 3.4 s / 0.4 s; the SHACL Shapes view after the edit 0.2 s, while
its verdicts are still evaluated.
"""

import os
import time

import pytest

import scale_package
from test_lsp_protocol import Session

ENTITIES = scale_package.ENTITIES
TYPES, COUNT = 300, 3000


@pytest.fixture(scope='module')
def large(tmp_path_factory):
    root = scale_package.make(str(tmp_path_factory.mktemp('scale') / 'pkg'), TYPES, COUNT)
    # The server is timed as users run it: without the coverage tracer, which
    # pytest-cov hands to every subprocess and which makes it several times
    # slower (the Knowledge view 1.6 s -> 7.2 s under `make test`).
    traced = {name: os.environ.pop(name) for name in list(os.environ)
              if name.startswith('COV_CORE')}
    try:
        session = Session(os.path.join(root, 'shacl.ttl'))
    finally:
        os.environ.update(traced)
    session.next_id = 100

    def ask(method, params, seconds=180):
        session.next_id += 1
        asked = session.next_id
        started = time.perf_counter()
        session.send({'jsonrpc': '2.0', 'id': asked, 'method': method,
                      'params': dict({'uri': 'file://' + root + '/kms.yaml'}, **params)})
        replies = session.wait_for(lambda m: m.get('id') == asked, seconds)
        assert replies, f'no reply to {method}'
        assert 'error' not in replies[0], replies[0]
        return replies[0]['result'], time.perf_counter() - started

    session.ask = ask
    session.root = root
    session.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                  'params': {'processId': os.getpid(), 'rootUri': 'file://' + root,
                             'capabilities': {}}})
    assert session.wait_for(lambda m: m.get('id') == 1), 'server did not initialize'
    session.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
    # Loading the package is not what is measured: a cheap request pays it.
    answer, _ = ask('semforge/attributes', {'entityType': ENTITIES + 'GenType0'})
    assert answer.get('attributes'), answer
    yield session
    session.close()


def test_the_type_picker_answers_at_once_on_hundreds_of_types(large):
    """New shape -> what does it check? -> a class: 20 s on the OPC UA demo."""
    answer, seconds = large.ask('semforge/entityTypes', {})
    print(f'entityTypes {seconds:.2f} s')
    generated = [t for t in answer['types'] if t['iri'].startswith(ENTITIES + 'GenType')]
    assert len(generated) == TYPES
    # Each generated type has a shape of its own, which a new attribute goes in.
    assert all(t['ownShape'].endswith(t['label'] + 'Shape') for t in generated)
    assert seconds < 5, f'entityTypes took {seconds:.1f} s'


def test_the_knowledge_view_does_not_scan_the_shapes_per_attribute(large):
    answer, seconds = large.ask('semforge/knowledge', {})
    print(f'knowledge {seconds:.2f} s')
    assert answer.get('roots'), answer
    assert seconds < 6, f'the Knowledge view took {seconds:.1f} s'


def test_after_a_new_shape_the_views_answer_without_parsing_the_model_again(large):
    before_edit = len(large.messages)
    made, _ = large.ask('semforge/addShape', {
        'name': 'ScaleShape', 'targetKind': 'class', 'target': ENTITIES + 'GenType7'})
    assert made.get('ok'), made
    # The first request after the edit pays the reload: the knowledge and the
    # 3,000 entities are unchanged and must be kept, not parsed again.
    answer, reload = large.ask('semforge/attributes', {'entityType': ENTITIES + 'GenType7'})
    print(f'first request after the edit {reload:.2f} s')
    assert answer.get('attributes'), answer
    assert reload < 1.5, f'the first request after an edit took {reload:.1f} s'

    # The SHACL Shapes view takes its counts from the background verdicts: it
    # answers while they are evaluated, and says so.
    shapes, seconds = large.ask('semforge/shapes', {})
    print(f'shapes after the edit {seconds:.2f} s, verdicts {shapes.get("verdicts")}')
    assert any(row['shape'] == made['iri'] for row in shapes['roots'])
    assert shapes['verdicts']['state'] in ('evaluating', 'ready')
    assert seconds < 5, f'the SHACL Shapes view took {seconds:.1f} s after an edit'

    # The verdicts arrive by notification; the view then has them. Only a
    # notice sent after the edit counts: one for the version before would
    # leave the view still evaluating.
    deadline = time.time() + 300
    while not any(m.get('method') == 'semforge/verdicts'
                  and (m.get('params') or {}).get('state') == 'ready'
                  for m in large.messages[before_edit:]):
        assert time.time() < deadline, 'no verdicts after the edit'
        time.sleep(0.2)
    shapes, _ = large.ask('semforge/shapes', {})
    assert shapes['verdicts']['state'] == 'ready'
