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

"""An attribute whose value may take several forms: the payload alternatives.

A value layer is one `sh:property` on a payload predicate. An OPC UA Variable
may be a scalar or an array -- its ValueRank decides -- so the OPC UA tools
write the value as a CHOICE of value layers:

    sh:or ( [ sh:property [ sh:path ngsi-ld:hasValue ;
                            sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string ] ]
            [ sh:property [ sh:path ngsi-ld:hasValueList ;
                            sh:minCount 1 ; sh:maxCount 1 ;
                            sh:or ( [ sh:nodeKind sh:BlankNode ;
                                      sh:property [ sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ;
                                                    sh:datatype xsd:string ] ]
                                    [ sh:hasValue () ] ) ] ] )

"a string, or a list of strings (possibly empty)". 564 of the 1,123 sh:or in
the OPC UA pump shapes are this, and the cooked views showed each as "any
value" with the sh:or verbatim beside it.

alternatives() reads such an sh:or into one Alternative per value layer --
the payload, the NGSI-LD kind it makes, and the constraints on the value (on
a list: on each member). It reads exactly these forms and nothing near them:
anything else is None, and stays shown verbatim, as before. Never a guess.
"""

from dataclasses import dataclass
from functools import lru_cache

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, SH

from ..ngsild.kinds import KINDS_OF_PAYLOAD, LIST_PAYLOADS, PAYLOAD_PATHS

# The constraints a value (or a list member) may carry and still be said in
# words; anything else on it makes the form not one of these.
MEMBER = {SH.datatype, SH['class'], SH.nodeKind, SH.minInclusive, SH.maxInclusive,
          SH.minExclusive, SH.maxExclusive, SH.minLength, SH.maxLength, SH.pattern,
          SH.flags, SH['in'], SH.hasValue,
          # An expression on the value (cooked/expression.py), kept as written.
          SH['or'], SH['and'], SH.xone, SH['not']}
COUNTS = {SH.minCount, SH.maxCount}
# What every member of an RDF list is: ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ).
LIST_KIND = {'hasValue': 'Property', 'hasObject': 'Relationship',
             'hasValueList': 'ListProperty', 'hasObjectList': 'ListRelationship'}


@dataclass(frozen=True)
class Alternative:
    payload: str           # hasValue | hasValueList | hasObject | hasObjectList | ...
    kind: str              # Property | ListProperty | Relationship | ...
    member: tuple          # ((curie, text), ...) on the value, or on each list member
    least: str = ''        # sh:minCount of the payload, as written
    most: str = ''         # sh:maxCount of the payload
    may_be_empty: bool = False   # a list that may be `()`

    @property
    def is_list(self):
        return self.payload in ('hasValueList', 'hasObjectList')


def alternatives(text, prefixes):
    """The payload alternatives an sh:or's text says, or None.

    `text` is the sh:or's object as written -- `( [ … ] [ … ] )`; `prefixes`
    the shapes graph's (prefix, namespace) pairs, to read it with.
    """
    return _alternatives(str(text).strip(), _key(prefixes))


def list_form(text, prefixes):
    """((curie, text) …, may be empty) for the sh:or of a list payload's own
    value layer -- `( [ sh:nodeKind sh:BlankNode ; sh:property [ <members> ] ]
    [ sh:hasValue () ] )` -- or None."""
    return _list_form(str(text).strip(), _key(prefixes))


def prefixes_of(package):
    """The prefixes the shapes are written with: every shapes file's own, over
    the graph's. The graph binds a namespace to ONE prefix, so a file saying
    both `ngsild:` and `ngsi-ld:` -- as the OPC UA package does once merged
    with SemForge's own -- loses one, and its sh:or could not be read back."""
    from ..rdfio.frozen import derived
    from ..rdfio.turtle_index import _prefixes

    def compute():
        found = {str(p): str(n) for p, n in package.shapes.namespaces()}
        for index in package.index('shapes').indexes.values():
            found.update(_prefixes(index.source)[0])
        return tuple(sorted(found.items()))
    return derived(package.shapes, 'file_prefixes', compute, key=(package.path,))


def _key(prefixes):
    if isinstance(prefixes, tuple):
        return _sorted_key(prefixes)      # prefixes_of's: the same tuple every row
    return tuple(sorted((str(p), str(n)) for p, n in prefixes))


@lru_cache(maxsize=16)
def _sorted_key(prefixes):
    return tuple(sorted((str(p), str(n)) for p, n in prefixes))


OR = SH['or']
HOLDER = URIRef('urn:semforge:holder')


@lru_cache(maxsize=512)
def _parse(text, prefixes):
    # The same few texts recur hundreds of times (every string attribute of
    # the OPC UA shapes writes the same sh:or): each is parsed once.
    head = ''.join(f'@prefix {p}: <{n}> .\n' for p, n in prefixes)
    try:
        graph = Graph().parse(data=f'{head}<{HOLDER}> <{OR}> {text} .', format='turtle')
    except Exception:                              # noqa: BLE001
        return None, None
    return graph, graph.value(HOLDER, OR)


@lru_cache(maxsize=512)
def _alternatives(text, prefixes):
    graph, head_node = _parse(text, prefixes)
    found = []
    for member in _members(graph, head_node) or ():
        alternative = _alternative(graph, member)
        if alternative is None:
            return None
        found.append(alternative)
    return tuple(found) or None


@lru_cache(maxsize=512)
def _list_form(text, prefixes):
    graph, _ = _parse(text, prefixes)
    if graph is None:
        return None
    holder = Graph()
    for triple in graph:
        holder.add(triple)
    # The sh:or as the value layer of a list payload holds it.
    layer = BNode()
    holder.add((layer, OR, graph.value(HOLDER, OR)))
    holder.namespace_manager = graph.namespace_manager
    member, empty, _ = _list_member(holder, layer)
    if member is None:
        return None
    params = _member(holder, member)
    return None if params is None else (params, empty)


def _members(graph, node):
    if node is None or (node != RDF.nil and (node, RDF.first, None) not in graph):
        return None
    return list(Collection(graph, node))


def _predicates(graph, node):
    return {p for p, _ in graph.predicate_objects(node)}


def _alternative(graph, member):
    """[ sh:property [ sh:path <payload> ; counts ; value ] ] -> Alternative."""
    if not isinstance(member, BNode) or _predicates(graph, member) != {SH.property}:
        return None
    layers = list(graph.objects(member, SH.property))
    if len(layers) != 1:
        return None
    layer = layers[0]
    path = graph.value(layer, SH.path)
    if not isinstance(path, URIRef) or str(path) not in PAYLOAD_PATHS:
        return None
    payload = str(path).rsplit('/', 1)[-1]
    rest = _predicates(graph, layer) - {SH.path} - COUNTS
    empty = False
    if str(path) in LIST_PAYLOADS:
        member_node, empty, extra = _list_member(graph, layer)
        if member_node is None or rest - extra:
            return None
        params = _member(graph, member_node)
    else:
        if rest - MEMBER:
            return None
        params = _member(graph, layer)
    if params is None:
        return None
    kind = LIST_KIND.get(payload) or KINDS_OF_PAYLOAD[payload][0]
    return Alternative(payload=payload, kind=kind, member=params,
                       least=_text(graph.value(layer, SH.minCount)),
                       most=_text(graph.value(layer, SH.maxCount)),
                       may_be_empty=empty)


def _list_member(graph, layer):
    """(the shape every member must satisfy, may the list be empty, the
    predicates of `layer` that said so) -- or (None, …) for another form.

    Either the member shape directly on the list payload's value, or an sh:or
    of it and `sh:hasValue ()` -- the empty list, which has no members to
    satisfy anything and is rdf:nil, not a blank node."""
    choice = graph.value(layer, OR)
    if choice is not None:
        options = _members(graph, choice) or []
        empty = [o for o in options
                 if _predicates(graph, o) == {SH.hasValue}
                 and graph.value(o, SH.hasValue) == RDF.nil]
        lists = [o for o in options if o not in empty]
        if len(empty) != 1 or len(lists) != 1:
            return None, False, set()
        holder = _list_holder(graph, lists[0])
        return holder, True, {OR}
    holder = _list_holder(graph, layer, allow=COUNTS | {SH.path})
    return holder, False, {SH.nodeKind, SH.property}


def _list_holder(graph, node, allow=frozenset()):
    """The member shape of [ sh:nodeKind sh:BlankNode ; sh:property [ sh:path
    ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ; … ] ], or None."""
    if _predicates(graph, node) - set(allow) != {SH.nodeKind, SH.property}:
        return None
    if graph.value(node, SH.nodeKind) != SH.BlankNode:
        return None
    inner = list(graph.objects(node, SH.property))
    if len(inner) != 1 or not _is_member_path(graph, graph.value(inner[0], SH.path)):
        return None
    if _predicates(graph, inner[0]) - {SH.path} - MEMBER:
        return None
    return inner[0]


def _is_member_path(graph, path):
    steps = _members(graph, path)
    if not steps or len(steps) != 2 or steps[1] != RDF.first:
        return False
    return graph.value(steps[0], SH.zeroOrMorePath) == RDF.rest and \
        _predicates(graph, steps[0]) == {SH.zeroOrMorePath}


def _member(graph, node):
    params = []
    for predicate, value in sorted(graph.predicate_objects(node)):
        if predicate not in MEMBER:
            continue
        if len(list(graph.objects(node, predicate))) != 1:
            return None
        params.append(('sh:' + str(predicate)[len(str(SH)):], _token(value, graph)))
    return tuple(params)


def _token(value, graph):
    """A member's value as Turtle, ready to be written back: a quoted string
    stays quoted (an sh:pattern was written back bare), a list or an
    expression is written out whole."""
    from .expression import _Reader

    return _Reader(graph, graph.namespace_manager.normalizeUri).term(value)


def _text(value, graph=None):
    if value is None:
        return ''
    if isinstance(value, Literal):
        return str(value)
    if graph is not None and isinstance(value, URIRef):
        return graph.namespace_manager.normalizeUri(value)
    return str(value)


# --- writing them back -----------------------------------------------------------
#
# What alternatives() read, written as it read it: an edit of a value that may be
# a scalar or a list changes the member constraints of every form at once, and
# the shapes file says the same thing afterwards as an OPC UA tool would have.

def _spelled(member, name):
    return [f'{name(SH[key[3:]])} {value}' for key, value in member]


def render_list_value(member, name):
    """The sh:or of a list payload's own value: its members, or the empty list."""
    path = f'( [ {name(SH.zeroOrMorePath)} {name(RDF.rest)} ] {name(RDF.first)} )'
    inner = ' ; '.join([f'{name(SH.path)} {path}'] + _spelled(member, name))
    return (f'( [ {name(SH.nodeKind)} {name(SH.BlankNode)} ; {name(SH.property)} [ {inner} ] ] '
            f'[ {name(SH.hasValue)} () ] )')


def _layer(alternative, name):
    from ..ngsild.kinds import NGSILD

    parts = [f'{name(SH.path)} {name(URIRef(NGSILD + alternative.payload))}']
    parts += [f'{name(predicate)} {value}'
              for predicate, value in ((SH.minCount, alternative.least),
                                       (SH.maxCount, alternative.most)) if value]
    if not alternative.is_list:
        parts += _spelled(alternative.member, name)
    elif alternative.may_be_empty:
        parts.append(f'{name(OR)} {render_list_value(alternative.member, name)}')
    else:
        path = f'( [ {name(SH.zeroOrMorePath)} {name(RDF.rest)} ] {name(RDF.first)} )'
        inner = ' ; '.join([f'{name(SH.path)} {path}'] + _spelled(alternative.member, name))
        parts.append(f'{name(SH.nodeKind)} {name(SH.BlankNode)} ; {name(SH.property)} [ {inner} ]')
    return ' ; '.join(parts)


def render(found, name, indent=''):
    """The text of an sh:or saying these alternatives, one per line under
    `indent`. `name(iri)` spells an IRI as the file being written does (its
    prefixes, else <…>)."""
    forms = [f'[ {name(SH.property)} [ {_layer(a, name)} ] ]' for a in found]
    return '( ' + f'\n{indent}  '.join(forms) + ' )'
