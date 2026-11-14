#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Plain JSON numbers as JSON-LD 1.1 types them.

JSON-LD 1.1 (Object to RDF Conversion, steps 10 and 11) makes a plain number
an xsd:double only when it has a non-zero fractional part or an absolute value
of at least 10^21; every other plain number is an xsd:integer, 80.0 included.
rdflib types a number by its notation instead, so it reads a plain 80.0 as an
xsd:double. Flink never sees that notation -- the bridge is JavaScript, which
writes 80.0 as 80 -- so the SQLite checks and Flink disagreed on exactly the
values the standard is clear about (#958).

`as_jsonld_numbers` gives rdflib what the standard means: a whole-valued
plain number below 10^21 becomes that integer before the document is parsed.
A value object with an "@type" is left alone, since its declared type decides
-- that includes an expanded "@json" literal -- and so is "@context" (a
"@version" of 1.1 is not data). Numbers inside a compact JsonProperty are read
like any other: JSON-LD's canonical form of a JSON literal writes 80.0 as 80,
and so does the bridge.
"""
import json
import pathlib

LIMIT = 1e21  # JSON-LD 1.1: from here on a plain number is a double


def _plain(value):
    """`value`, a plain JSON value, read as JSON-LD types it."""
    if isinstance(value, float) and value.is_integer() and abs(value) < LIMIT:
        return int(value)
    return value


def as_jsonld_numbers(node):
    """`node` (parsed JSON-LD) with its plain numbers as JSON-LD 1.1 types them."""
    if isinstance(node, list):
        return [as_jsonld_numbers(item) for item in node]
    if isinstance(node, dict):
        if '@value' in node and '@type' in node:
            return node  # a declared type decides, whatever the value
        return {key: (value if key == '@context' else as_jsonld_numbers(value))
                for key, value in node.items()}
    return _plain(node)


def read_jsonld(path):
    """The JSON-LD file at `path` as text for rdflib, numbers as JSON-LD types them,
    and the base its relative references resolve against."""
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    return json.dumps(as_jsonld_numbers(document)), pathlib.Path(path).absolute().as_uri()
