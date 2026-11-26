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

"""A SPARQL constraint's sh:message: what it is filled from, and what is wrong in it.

`{?x}` and `{$x}` (the same) stand for the query's variable x in the row that
violates. One rule everywhere: the name is compared as written, case included,
and a placeholder the row has no value for stays as it is -- that is what
pyshacl does, so it is what `semforge test` and the editor show. The workbench
page fills its preview by the same rule (vscode/src/sparqlmessage.js).

The platform fills it in SQL: shacl2flink's add_variables_to_message turns
every `{?x}` into the column `x` of the compiled query, and the query has a
column for each variable it SELECTs and no others. The message stands in that
SQL between apostrophes, unescaped. And its query for what to compile asks for
sh:message and sh:select together: a constraint without one is not compiled.
"""

import functools
import re
from dataclasses import dataclass

# Any name \w+ is filled; shacl2flink also takes an empty one (\w*).
PLACEHOLDER = re.compile(r'\{([?$])(\w+)\}')
EMPTY = re.compile(r'\{[?$]\}')
BARE = re.compile(r'\{\s*[?$]?\s*(\w+)\s*\}')

MISSING = ('it has no sh:message: the platform compiles only a constraint that has one, so '
           'this one is not checked there. SemForge validates it all the same.')


@dataclass(frozen=True)
class MessageProblem:
    code: str          # message-missing | message-variable | message-apostrophe
    message: str
    part: str = ''     # the part of the message it is about


def locked(count, is_text):
    """Why sh:message values are not edited from a page; '' when they are.
    `count` is how many the constraint has, `is_text` whether its one value
    is a text."""
    if count > 1:
        return (f'it has {count} sh:message values: which one is meant cannot be told '
                'here. Edit them in the .ttl.')
    if count and not is_text:
        return 'its sh:message is not a text. Edit it in the .ttl.'
    return ''


def locked_in(graph, holder):
    """`locked` of a constraint's node in a graph."""
    from rdflib import Literal
    from rdflib.namespace import SH

    values = list(graph.objects(holder, SH.message))
    return locked(len(values), bool(values) and isinstance(values[0], Literal))


def fill(template, row):
    """The message of one violating row ({name: text}); what the row has no
    value for stays as written."""
    return PLACEHOLDER.sub(lambda m: row[m.group(2)] if m.group(2) in row else m.group(0),
                           template or '')


def placeholders(template):
    """The variables a message names, each once, in order."""
    return list(dict.fromkeys(m.group(2) for m in PLACEHOLDER.finditer(template or '')))


@functools.lru_cache(maxsize=256)
def _projection(query):
    from rdflib.plugins.sparql import prepareQuery

    try:
        prepared = prepareQuery(query)
    except Exception:                                # noqa: BLE001 -- said by the query's own check
        return None
    if prepared.algebra.name != 'SelectQuery':
        return None
    names = list(dict.fromkeys(str(v) for v in prepared.algebra.PV))
    return tuple((['this'] if 'this' in names else []) + [n for n in names if n != 'this'])


def variables(query, prefix_lines=()):
    """What the query SELECTs -- `SELECT *` and `(… AS ?x)` as the parser
    reads them -- `this` first; None when it is no SELECT that parses."""
    found = _projection('\n'.join(list(prefix_lines) + [query]))
    return None if found is None else list(found)


def _unselected(name, written, known):
    near = next((k for k in known if k.lower() == name.lower()), None)
    said = f'{written} is not a variable the query selects'
    if near is not None:
        said += f' (names are compared with their case: {{?{near}}} is)'
    return (f'{said}: SemForge shows it as text, and the platform\'s SQL would read a column '
            f'"{name}" the query does not give')


def check(template, known):
    """[MessageProblem] of a message over the variables `known` (None: not
    known, the query does not parse -- nothing is said about variables)."""
    if not (template or '').strip():
        return [MessageProblem('message-missing', MISSING)]
    found = []
    if known is not None:
        for match in PLACEHOLDER.finditer(template):
            if match.group(2) not in known:
                found.append(MessageProblem(
                    'message-variable', _unselected(match.group(2), match.group(0), known),
                    match.group(0)))
        for match in BARE.finditer(template):
            if not PLACEHOLDER.fullmatch(match.group(0)) and match.group(1) in known:
                found.append(MessageProblem(
                    'message-variable', f'{match.group(0)} is text, not a variable: '
                    f'{{?{match.group(1)}}} is filled', match.group(0)))
    for match in EMPTY.finditer(template):
        found.append(MessageProblem(
            'message-variable', f'{match.group(0)} names no variable: SemForge shows it as '
            'text, and the platform\'s SQL would read a column without a name',
            match.group(0)))
    if "'" in template:
        found.append(MessageProblem(
            'message-apostrophe', 'an apostrophe (\') ends the text in the SQL the platform '
            'compiles from it, which then does not run: write it without, or with ’', "'"))
    return list(dict.fromkeys(found))
