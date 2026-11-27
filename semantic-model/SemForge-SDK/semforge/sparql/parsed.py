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

"""A SPARQL query text is parsed once per process, not once per call.

pyshacl runs a SPARQL constraint (and a SPARQL target, a SPARQL constraint
component, a rule) once per focus node, passing the same query TEXT each time
with `$this` in initBindings -- and rdflib parses a text on every call. Its
pyparsing grammar takes ~70 ms for a constraint with the package's prefixes
in front: re-validating a 931-node model after adding one attribute spent
3.9 s of 6.4 s parsing three constraints 52 times.

The translated query is what rdflib's own prepareQuery returns, and reusing
it is what that function is for: evaluation never changes it. Keyed on the
text, the base and the initial namespaces -- everything translation reads.
Registered as rdflib's 'sparql' query processor, so every Graph.query in the
process goes through it.
"""

from functools import lru_cache

from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.processor import SPARQLProcessor


@lru_cache(maxsize=1024)
def _translated(text, base, namespaces):
    return translateQuery(parseQuery(text), base, dict(namespaces) if namespaces else None)


def translated(text, base=None, initNs=None):
    return _translated(text, base, tuple(sorted(initNs.items())) if initNs else ())


class CachingSPARQLProcessor(SPARQLProcessor):
    """rdflib's SPARQLProcessor, parsing each distinct text once."""

    def query(self, strOrQuery, initBindings=None, initNs=None, base=None, DEBUG=False):
        if isinstance(strOrQuery, str):
            strOrQuery = translated(strOrQuery, base, initNs)
        return evalQuery(self.graph, strOrQuery, initBindings, base)


def install():
    """Make it the 'sparql' processor of this process. Idempotent."""
    from rdflib import plugin
    from rdflib.query import Processor

    plugin.register('sparql', Processor, __name__, 'CachingSPARQLProcessor')


def uninstall():
    from rdflib import plugin
    from rdflib.query import Processor

    plugin.register('sparql', Processor, 'rdflib.plugins.sparql.processor', 'SPARQLProcessor')
