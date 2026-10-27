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

"""What a large package (the OPC UA pump example: 12.8 MB of knowledge) needs.

Validation scaled; the editor paths did not. One `semforge check` indexed the
same ontologies sixteen times, each index counting line numbers from the start
of the file (quadratic: 34 s for one file), and re-read the prefix table 5,600
times. And OPC UA ExtensionObjects -- JsonProperty payloads -- were scanned
for attribute keys.
"""

import json
import os
import time

from semforge.rdfio import turtle_index
from semforge.rdfio.turtle_index import TurtleIndex

PREFIXES = '@prefix ex: <https://example.org/> .\n'


def _statements(count):
    return PREFIXES + ''.join(
        f'ex:S{n} a ex:Thing ;\n    ex:p "{n}" ;\n    ex:q ex:O{n} .\n\n' for n in range(count))


def test_line_numbers_are_those_of_a_count_from_the_start():
    text = '# a comment\n\n' + _statements(50)
    for block in TurtleIndex(text).blocks:
        assert block.start_line == text.count('\n', 0, block.start) + 1
        assert block.end_line == text.count('\n', 0, block.end) + 1


def test_indexing_is_linear_in_the_size_of_the_file():
    small, large = _statements(2000), _statements(20000)
    timings = []
    for text in (small, large):
        turtle_index._PARSED.clear()
        start = time.perf_counter()
        TurtleIndex(text)
        timings.append(time.perf_counter() - start)
    # Ten times the statements: about ten times the work. Quadratic was ~100x.
    assert timings[1] < timings[0] * 30, timings


def test_one_text_is_parsed_once_and_an_edit_is_parsed_again():
    text = _statements(10)
    first, second = TurtleIndex(text), TurtleIndex(text, path='x.ttl')
    assert first.blocks is second.blocks
    assert second.path == 'x.ttl'
    edited = TurtleIndex(text.replace('ex:S3 ', 'ex:T3 '))
    assert edited.blocks is not first.blocks
    assert edited.block_for('https://example.org/T3') is not None
    assert first.block_for('https://example.org/T3') is None


def test_the_cache_is_bounded():
    for n in range(turtle_index._PARSED_LIMIT + 10):
        TurtleIndex(_statements(1) + f'# {n}\n')
    assert len(turtle_index._PARSED) <= turtle_index._PARSED_LIMIT


def test_the_prefix_table_is_read_once_and_an_edit_is_seen(tmp_path):
    from semforge.package import prefixes

    config = tmp_path / 'semforge.yaml'
    config.write_text('namespaces:\n  ex: https://example.org/\n')
    calls = []
    read = prefixes._declared_prefixes

    def counting(path):
        calls.append(path)
        return read(path)

    prefixes_before = prefixes._declared_prefixes
    prefixes._declared_prefixes = counting
    try:
        for _ in range(50):
            assert prefixes.declared_prefixes(str(tmp_path)) == {'ex': 'https://example.org/'}
        assert len(calls) == 1

        config.write_text('namespaces:\n  ex: https://example.org/\n  ey: https://example.org/y/\n')
        os.utime(config, ns=(time.time_ns(), time.time_ns() + 1_000_000))
        assert prefixes.declared_prefixes(str(tmp_path))['ey'] == 'https://example.org/y/'
        assert len(calls) == 2
    finally:
        prefixes._declared_prefixes = prefixes_before


def test_a_caller_cannot_change_the_cached_table(tmp_path):
    from semforge.package.prefixes import declared_prefixes

    (tmp_path / 'semforge.yaml').write_text('namespaces:\n  ex: https://example.org/\n')
    declared_prefixes(str(tmp_path))['junk'] = 'x'
    assert 'junk' not in declared_prefixes(str(tmp_path))


def test_a_json_payload_is_not_read_as_attributes(tmp_path):
    from semforge.expect.vocabulary import _keys

    document = [{
        'id': 'urn:x:1', 'type': 'ex:Pump',
        'ex:hasClass': {'type': 'JsonProperty', 'json': {
            'xsd:TypeId': {'xsd:Identifier': 'ns=2;i=5008'},
            'xsd:Body': {'xsd:OptionSet': {'xsd:Value': 'AAA='}}}},
        'ex:hasPoint': {'type': 'Property', 'value': {'ex:x': 1, 'ex:y': 2}},
        'ex:hasState': {'type': 'Property', 'value': 1,
                        'ex:hasTrust': {'type': 'Property', 'value': 0.5}}}]
    path = tmp_path / 'model-instance.jsonld'
    path.write_text(json.dumps(document, indent=2))
    keys = {key for key, _ in _keys(str(path))}
    assert keys == {'ex:hasClass', 'ex:hasPoint', 'ex:hasState', 'ex:hasTrust'}
