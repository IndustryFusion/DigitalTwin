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
"""lib.shape_rows gives the rows of the two big shape queries -- checked
against rdflib's own evaluation of their SPARQL, on every shape set in the
tests and on edge cases the corpus does not have."""

import collections
import glob
import os

import pytest
from rdflib import RDFS, Graph, Literal, Namespace, RDF, URIRef

import lib.shacl_properties_to_sql as props
import lib.shape_rows as shape_rows

HERE = os.path.dirname(os.path.abspath(__file__))
NS = {'sh': Namespace('http://www.w3.org/ns/shacl#'), 'rdf': RDF, 'rdfs': RDFS,
      'ngsi-ld': Namespace('https://uri.etsi.org/ngsi-ld/')}
# The walk's `ins` holds the sh:in members as shape_rows.in_token() writes
# them, not the query's CONCAT of them (which rdflib fails on for anything but
# a string). So the reference query aggregates the raw members instead --
# lexical form, language, datatype -- and the test turns them into tokens;
# everything else about the rows (which members, how often) is still rdflib's.
FIELD, MEMBER = '\x01', '\x02'
IN_CONCAT = "(GROUP_CONCAT(CONCAT('\"', ?in, '\"'); separator=',') as ?ins)"
# BOUND: an unbound ?in must be skipped, as GROUP_CONCAT skips an unbound
# CONCAT; ?unbound is never bound, so the else branch is exactly that.
IN_RAW = ("(GROUP_CONCAT(IF(BOUND(?in), IF(isIRI(?in), CONCAT(STR(?in), '\\u0001@id'), "
          "CONCAT(STR(?in), '\\u0001', LANG(?in), '\\u0001', STR(DATATYPE(?in)))), ?unbound); "
          "separator='\\u0002') as ?ins)")
assert props.sparql_get_all_properties.count(IN_CONCAT) == 1
PROPERTIES_REFERENCE = props.sparql_get_all_properties.replace(IN_CONCAT, IN_RAW)

# (name, SPARQL reference, the query text the walk is given, walk)
QUERIES = [('relationships', props.sparql_get_all_relationships, props.sparql_get_all_relationships,
            shape_rows.relationship_rows),
           ('properties', PROPERTIES_REFERENCE, props.sparql_get_all_properties, shape_rows.property_rows)]


def reference_ins(value):
    """The reference query's raw sh:in members, as sorted in_token() tokens."""
    tokens = []
    for member in str(value).split(MEMBER) if str(value) else []:
        fields = member.split(FIELD)
        if len(fields) == 2:
            term = URIRef(fields[0])
        else:
            assert len(fields) == 3, f'unexpected member {member!r}'
            lexical, language, datatype = fields
            term = Literal(lexical, lang=language) if language else Literal(lexical, datatype=datatype or None)
        tokens.append(shape_rows.in_token(term))
    return ','.join(sorted(tokens))


def canonical(row, reference=False):
    """A row as a tuple. `datatypes` as sorted pieces: SPARQL leaves the order of
    GROUP_CONCAT undefined (rdflib's varies with string hashing), and the walk
    sorts it. `ins` of a reference row turned into tokens (see above)."""
    values = row.asdict()
    out = []
    for var in row.labels:
        value = values.get(var)
        if str(var) == 'ins' and value is not None and reference:
            value = reference_ins(value)
        elif str(var) == 'datatypes' and value is not None:
            value = ','.join(sorted(str(value).split(',')))
        elif str(var) == 'ins' and value is not None:
            value = str(value)
        out.append(value)
    return tuple(out)


def graph_of(shacl, knowledge=None):
    """The graph translate() queries: shapes plus knowledge, sh:node inlined."""
    g = Graph()
    g.parse(data=shacl, format='turtle') if '\n' in shacl else g.parse(shacl)
    if knowledge:
        h = Graph()
        h.parse(data=knowledge, format='turtle') if '\n' in knowledge else h.parse(knowledge)
        g += h
    props.expand_node_shapes(g)
    return g


def assert_same_rows(g):
    """Both queries give the same rows by walk and by SPARQL; returns how many."""
    total = 0
    for name, reference, text, walk in QUERIES:
        expected = collections.Counter(canonical(r, reference=True) for r in g.query(reference, initNs=NS))
        actual = collections.Counter(canonical(r) for r in walk(g, text))
        assert actual == expected, f'{name}: only SPARQL {list((expected - actual).elements())[:2]}, ' \
                                   f'only walk {list((actual - expected).elements())[:2]}'
        total += sum(expected.values())
    return total


def corpus():
    """Every checked-in shape set with its knowledge; generated output/
    directories are left out, so the test does not depend on what other make
    targets ran before it."""
    pairs = []
    for shacl in sorted(glob.glob(os.path.join(HERE, '**', 'shacl.ttl'), recursive=True)):
        where = os.path.dirname(shacl)
        knowledge = os.path.join(where, 'knowledge.ttl')
        if 'output' not in os.path.relpath(where, HERE).split(os.sep) and os.path.exists(knowledge):
            pairs.append(pytest.param(shacl, knowledge, id=os.path.relpath(where, HERE)))
    return pairs


@pytest.mark.parametrize('shacl,knowledge', corpus())
def test_the_rows_of_every_shape_set_in_the_tests(shacl, knowledge):
    assert_same_rows(graph_of(shacl, knowledge))


PREFIXES = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
@prefix ex: <http://example.org/> .
'''

EDGE_CASES = {
    'sh:in with strings, numbers, booleans and IRIs': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasMode ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( "a" 1 2.5 true ex:iri "b"@en ) ] ] .
''',
    'several datatypes, in an sh:or and on the value shape': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasLevel ; sh:maxCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:string ;
      sh:or ( [ sh:datatype xsd:integer ] [ sh:datatype xsd:double ] [ sh:datatype xsd:boolean ] ) ] ] .
''',
    'connectives on the property and on the value shape': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasA ;
    sh:xone ( [ sh:minCount 1 ; sh:property [ sh:path ngsi-ld:hasValue ; sh:minInclusive 0 ] ]
              [ sh:maxCount 0 ] ) ] ;
  sh:property [ sh:path ex:hasB ; sh:not [ sh:property [ sh:path ngsi-ld:hasValue ; sh:hasValue "x" ] ] ] ;
  sh:property [ sh:path ex:hasC ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ;
      sh:and ( [ sh:minExclusive 1 ] [ sh:maxExclusive 9 ; sh:pattern "^[0-9]+$" ] ) ] ] .
''',
    'relationships with classes, connectives and severities': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasPeer ; sh:minCount 1 ; sh:maxCount 2 ; sh:severity sh:Warning ;
    sh:property [ sh:path ngsi-ld:hasObject ; sh:class ex:Peer ] ] ;
  sh:property [ sh:path ex:hasOther ;
    sh:or ( [ sh:property [ sh:path ngsi-ld:hasObject ; sh:class ex:A ] ]
            [ sh:property [ sh:path ngsi-ld:hasObject ;
                sh:or ( [ sh:class ex:B ] [ sh:class ex:C ] ) ] ] ) ] .
sh:Warning rdfs:label "warning" .
''',
    'inherited target classes and a subclass chain': '''
ex:S a sh:NodeShape ; sh:targetClass ex:Base ;
  sh:property [ sh:path ex:hasX ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:minLength 2 ; sh:maxLength 5 ] ] .
ex:Mid rdfs:subClassOf ex:Base . ex:Leaf rdfs:subClassOf ex:Mid . ex:Other rdfs:subClassOf ex:Leaf .
''',
    'a list of elements and a JSON value': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasList ; sh:maxCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValueList ;
      sh:property [ sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ; sh:datatype xsd:integer ] ] ] ;
  sh:property [ sh:path ex:hasJson ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasJSON ; sh:nodeKind sh:Literal ] ] .
''',
    'a repeated list member and two value shapes': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasR ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( "x" "x" "y" ) ] ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:string ] ] .
''',
    # rdflib keeps each UNION's solutions as a
    # set, so a list naming one shape twice, or an rdf:rest cycle, counts once.
    'one shape named twice in a connective list': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasA ; sh:or ( ex:B ex:B ) ] ;
  sh:property [ sh:path ex:hasD ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:or ( ex:E ex:E ) ] ] .
ex:B sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:string ] ;
     sh:property [ sh:path ngsi-ld:hasObject ; sh:class ex:K ] .
ex:E sh:datatype xsd:integer .
''',
    'an rdf:rest cycle back to the list head': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P .
ex:P sh:path ex:hasA ; sh:or ex:L1 .
ex:L1 rdf:first ex:Q ; rdf:rest ex:L2 . ex:L2 rdf:first ex:R ; rdf:rest ex:L1 .
ex:R sh:property [ sh:path ngsi-ld:hasObject ; sh:xone ex:L1 ] .
''',
    # Falsy members (0, false, ""): a path that walks on from a member would
    # take them for an unbound subject and collect every list in the graph.
    'falsy members of sh:in': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasMode ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( "" "a" "b" ) ; sh:datatype xsd:string ] ] ;
  sh:property [ sh:path ex:hasLevel ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( 0 1 2 ) ] ] ;
  sh:property [ sh:path ex:hasFlag ; sh:minCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( false true ) ] ] .
''',
    'a literal where a connective list belongs': '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasA ; sh:minCount 1 ; sh:or false ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:string ] ] ;
  sh:property [ sh:path ex:hasB ; sh:or ( [ sh:minCount 1 ] ) ] .
''',
}


@pytest.mark.parametrize('name', sorted(EDGE_CASES))
def test_edge_cases(name):
    shapes = PREFIXES + '@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n' + EDGE_CASES[name]
    assert assert_same_rows(graph_of(shapes)) > 0, 'the edge case must produce rows to test anything'


def test_the_concatenations_are_sorted():
    g = graph_of(PREFIXES + EDGE_CASES['several datatypes, in an sh:or and on the value shape'])
    rows = shape_rows.property_rows(g, props.sparql_get_all_properties)
    datatypes = {str(r.datatypes) for r in rows}
    assert datatypes and all(d.split(',') == sorted(d.split(',')) for d in datatypes)


def test_sh_in_members_carry_their_datatype():
    """Strings, numbers, booleans and IRIs alike become `"lexical"^^datatype`;
    a double quote is escaped as the SQL escapes it in a value."""
    g = graph_of(PREFIXES + EDGE_CASES['sh:in with strings, numbers, booleans and IRIs'])
    ins = {str(r.ins) for r in shape_rows.property_rows(g, props.sparql_get_all_properties)}
    xsd = 'http://www.w3.org/2001/XMLSchema#'
    assert ins == {','.join(sorted([
        f'"a"^^{xsd}string', f'"1"^^{xsd}integer', f'"2.5"^^{xsd}decimal', f'"true"^^{xsd}boolean',
        '"http://example.org/iri"^^@id', '"b"^^http://www.w3.org/1999/02/22-rdf-syntax-ns#langString']))}
    assert shape_rows.in_token(Literal('say "hi"')) == f'"say \\"hi\\""^^{xsd}string'


def test_sh_in_holds_only_its_own_members():
    """A falsy member (0, false) must not let the list take in the members of
    other lists -- sh:in lists, connective lists of blank nodes -- which a path
    walking on from each member did."""
    g = graph_of(PREFIXES + '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:hasLevel ; sh:maxCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( 0 1 2 ) ] ] ;
  sh:property [ sh:path ex:hasFlag ; sh:maxCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( false true ) ] ] ;
  sh:property [ sh:path ex:hasMode ; sh:maxCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:in ( "ON" "OFF" ) ] ] ;
  sh:property [ sh:path ex:hasStrength ; sh:maxCount 1 ;
    sh:property [ sh:path ngsi-ld:hasValue ;
      sh:or ( [ sh:datatype xsd:integer ] [ sh:datatype xsd:double ] ) ] ] .
''')
    xsd = 'http://www.w3.org/2001/XMLSchema#'
    ins = {str(r.propertypath).rsplit('/', 1)[-1]: str(r.ins)
           for r in shape_rows.property_rows(g, props.sparql_get_all_properties) if str(r.ins)}
    assert ins == {
        'hasLevel': ','.join(sorted(f'"{n}"^^{xsd}integer' for n in (0, 1, 2))),
        'hasFlag': ','.join(sorted(f'"{b}"^^{xsd}boolean' for b in ('false', 'true'))),
        'hasMode': ','.join(sorted(f'"{m}"^^{xsd}string' for m in ('ON', 'OFF'))),
    }
