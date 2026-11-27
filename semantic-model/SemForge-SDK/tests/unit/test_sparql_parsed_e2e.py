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

"""End to end: `semforge test` on the corpus parses each text of a SPARQL
constraint once, although pyshacl runs it for every focus node of every case."""

from click.testing import CliRunner
from rdflib.plugins.sparql import parser, processor

from semforge.cli import cli
from semforge.sparql import parsed

# A line of iffBaseShacl:StateOnCutterShape's query, which runs for every cutter.
MARK = '$this iffBaseEntities:hasFilter [ ngsild:hasObject ?f ]'


def test_semforge_test_parses_a_constraint_once(corpus_path, monkeypatch):
    calls = []
    real = parser.parseQuery

    def counted(text, *args, **kwargs):
        calls.append(str(text))
        return real(text, *args, **kwargs)
    # Wherever rdflib parses: its own processor, and SemForge's cached one.
    for module in (parser, processor, parsed):
        monkeypatch.setattr(module, 'parseQuery', counted)
    parsed._translated.cache_clear()
    monkeypatch.setenv('SEMFORGE_HISTORY', 'off')

    result = CliRunner().invoke(cli, ['test', corpus_path])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    runs = [c for c in calls if MARK in c]
    # Its text as pyshacl sends it, and SemForge's own reading of what the
    # query reads (validate/readset.py): each parsed once, not per focus node.
    assert runs and len(runs) == len(set(runs)), f'{len(runs)} parses of {len(set(runs))} texts'
