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

"""Plain JSON numbers as JSON-LD 1.1 types them (#958).

JSON-LD 1.1 (Object to RDF Conversion, steps 10 and 11) makes a plain number
an xsd:double only when it has a non-zero fractional part or an absolute value
of at least 10^21; every other plain number is an xsd:integer, 80.0 included.
rdflib types a number by its notation instead and reads a plain 80.0 as an
xsd:double, so pyshacl accepted it on an xsd:double shape where shacl2flink,
Flink and a conformant SHACL engine reject it.

The same rule is implemented in shacl2flink (lib/jsonld_numbers.py), which
SemForge runs without. Both are tested against one table,
semantic-model/shacl2flink/tests/jsonld-number-vectors.json, and the
cross-check compares the two at run time.
"""

LIMIT = 1e21  # JSON-LD 1.1: from here on a plain number is a double


def as_jsonld_numbers(node):
    """`node` (parsed JSON-LD) with its plain numbers as JSON-LD 1.1 types them.

    A whole-valued plain number below 10^21 becomes that integer. A value
    object with an "@type" is left alone -- its declared type decides -- and
    so is "@context", where a "@version" of 1.1 is not data.
    """
    if isinstance(node, list):
        return [as_jsonld_numbers(item) for item in node]
    if isinstance(node, dict):
        if '@value' in node and '@type' in node:
            return node
        return {key: (value if key == '@context' else as_jsonld_numbers(value))
                for key, value in node.items()}
    if isinstance(node, float) and node.is_integer() and abs(node) < LIMIT:
        return int(node)
    return node
