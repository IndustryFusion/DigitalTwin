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

"""A compiled query answers what SPARQL answers.

Every query is evaluated by rdflib on the model and the knowledge -- that is
what an author sees while writing it -- and as the SQL it compiles to, in
SQLite. The same entities must come out of both.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys

import pytest
import rdflib

import lib.utils as utils
from lib.jsonld_numbers import read_jsonld
from lib.query_check import check
from lib.sparql_to_sql import translate_sparql

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
EX = 'https://example.org/'
PREFIXES = f'''PREFIX ex: <{EX}>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
'''
CONTEXT = {'@context': [{'ex': {'@id': EX, '@prefix': True},
                         'base': {'@id': EX + 'base/', '@prefix': True},
                         'xsd': {'@id': 'http://www.w3.org/2001/XMLSchema#', '@prefix': True},
                         'ngsi-ld': {'@id': 'https://uri.etsi.org/ngsi-ld/', '@prefix': True},
                         'id': '@id', 'type': '@type', 'value': 'ngsi-ld:hasValue',
                         'object': {'@id': 'ngsi-ld:hasObject', '@type': '@id'},
                         'Property': 'ngsi-ld:Property', 'Relationship': 'ngsi-ld:Relationship',
                         'observedAt': {'@id': 'ngsi-ld:observedAt', '@type': 'ngsi-ld:DateTime'},
                         'datasetId': {'@id': 'ngsi-ld:datasetId', '@type': '@id'}}]}
SHAPES = f'''@prefix ex: <{EX}> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:MachineShape a sh:NodeShape ; sh:targetClass ex:Machine ;
    sh:property [ sh:path ex:speed ; sh:nodeKind sh:BlankNode ; sh:minCount 0 ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ; sh:minCount 1 ] ] ;
    sh:property [ sh:path ex:state ; sh:nodeKind sh:BlankNode ; sh:minCount 0 ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:IRI ; sh:minCount 1 ] ] .
ex:PartShape a sh:NodeShape ; sh:targetClass ex:Part ;
    sh:property [ sh:path ex:weight ; sh:nodeKind sh:BlankNode ; sh:minCount 0 ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ; sh:minCount 1 ] ] .
# Reached through sh:node alone, as an instance declaration of OPC UA is.
ex:PartsDeclarationShape a sh:NodeShape ;
    sh:property [ sh:path ex:hasPart ; sh:nodeKind sh:BlankNode ; sh:minCount 0 ;
        sh:property [ sh:path ngsild:hasObject ; sh:nodeKind sh:IRI ; sh:minCount 1 ] ] .
'''
KNOWLEDGE = f'''@prefix ex: <{EX}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Machine a owl:Class . ex:Part a owl:Class .
ex:Press a owl:Class ; rdfs:subClassOf ex:Machine, ex:Base .
ex:on ex:label "on" ; ex:follows ex:off ; ex:word "abc" ; ex:twenty 20 .
ex:off ex:follows ex:third . ex:hasPart ex:unit "pieces" .
ex:off ex:label "off" .
ex:speed ex:unit "rpm" . ex:limit ex:unit "rpm" . ex:text ex:unit "words" .
ex:on ex:maximum 20 ; ex:range [ ex:max 10 ] ; ex:words [ ex:w "abc", "9" ] .
'''


def prop(value, **more):
    return dict({'type': 'Property', 'value': value}, **more)


def machine(number, **attributes):
    kind = attributes.pop('kind', 'ex:Machine')
    return dict({'id': f'urn:m:{number}', 'type': kind},
                **{f'ex:{name}': value for name, value in attributes.items()})


MODEL = [
    machine(1, speed=prop(9), limit=prop(10), bound=prop(10), state=prop({'@id': 'ex:on'}), text=prop('abc'),
            dangling={'type': 'Relationship', 'object': 'urn:nowhere:1'}),
    machine(2, speed=prop(10), limit=prop(9), bound=prop(10), state=prop({'@id': 'ex:off'}), text=prop('abd')),
    machine(3, speed=prop(100.5), limit=prop(20), text=prop('9')),
    # (its spare is another part than its part)
    machine(4, speed=prop({'@value': '7.0', '@type': 'xsd:double'}), limit=prop(7), kind='ex:Press',
            spare={'type': 'Relationship', 'object': 'urn:p:2'},
            hasPart=dict({'type': 'Relationship', 'object': 'urn:p:1'}, observedAt='2024-02-28T13:52:32.000Z')),
    machine(5, limit=prop(3), state=prop({'@id': 'ex:on'}), spare={'type': 'Relationship', 'object': 'urn:p:2'},
            hasPart={'type': 'Relationship', 'object': 'urn:p:2'}),
    machine(6, speed=prop(5, observedAt='2024-02-28T13:52:32.000Z'),
            spare={'type': 'Relationship', 'object': 'urn:p:2', 'observedAt': '2024-02-28T13:52:32.000Z'},
            undeclared=prop('yes'), kind='ex:Press'),
    machine(7),
    {'id': 'urn:p:1', 'type': 'ex:Part', 'ex:weight': prop(12), 'ex:name': prop('wheel')},
    {'id': 'urn:p:2', 'type': 'ex:Part', 'ex:weight': prop(3), 'ex:name': prop('axle')}]

SAME = {
    # an attribute, in every way it can be written
    'blank node': '$this ex:speed [ ngsild:hasValue ?v ]',
    'named instance': '$this ex:speed ?a . ?a ngsild:hasValue ?v',
    'path': '$this ex:speed/ngsild:hasValue ?v . FILTER(?v > 9)',
    'two payloads': '$this ex:speed [ ngsild:hasValue ?v ; ngsild:observedAt ?t ] . FILTER(?v < 6)',
    'constant iri': '$this ex:state [ ngsild:hasValue ex:on ]',
    'constant text': '$this ex:text [ ngsild:hasValue "abc" ]',
    'constant number': '$this ex:limit [ ngsild:hasValue 10 ]',
    'constant object': '$this ex:hasPart [ ngsild:hasObject <urn:p:2> ]',
    # whatever shape says what it is, or none
    'from a shape without target': '$this ex:hasPart [ ngsild:hasObject ?p ]',
    'in no shape': '$this ex:undeclared [ ngsild:hasValue ?v ]',
    'in no shape, compared': '$this ex:undeclared [ ngsild:hasValue ?v ] . FILTER(?v = "yes")',
    'an entity compared': '$this ex:hasPart [ ngsild:hasObject ?p ] . FILTER(?p = <urn:p:1>)',
    'an entity not': '$this ex:hasPart [ ngsild:hasObject ?p ] . FILTER(?p != <urn:p:1>)',
    'another entity': '?o a ex:Press . $this ex:speed [ ngsild:hasValue ?v ] . ?o ex:speed [ ngsild:hasValue ?w ] . '
                      'FILTER(?o != $this && ?v < ?w)',
    'through a relationship': '$this ex:hasPart [ ngsild:hasObject ?p ] . ?p ex:weight [ ngsild:hasValue ?w ] . '
                              'FILTER(?w < 12)',
    # any attribute
    'any property': '$this ?attribute [ ngsild:hasValue ?v ]',
    'any property, by value': '$this ?attribute [ ngsild:hasValue ?v ] . FILTER(?v = ex:on)',
    'any property, by text': '$this ?attribute [ ngsild:hasValue ?v ] . FILTER(?v = "abd")',
    'any property, by number': '$this ?attribute [ ngsild:hasValue ?v ] . '
                               'FILTER(?attribute IN (ex:speed, ex:limit) && ?v > 50)',
    'any property, by name': '$this ?attribute [ ngsild:hasValue ?v ] . FILTER(?attribute = ex:undeclared)',
    'any property, one of': '$this ?attribute [ ngsild:hasValue ?v ] . FILTER(?attribute IN (ex:state, ex:text))',
    'any property, none of':
        '$this ?attribute [ ngsild:hasValue ?v ] . FILTER(?attribute NOT IN (ex:speed, ex:limit))',
    'any property, by knowledge': '$this ?attribute [ ngsild:hasValue ?v ] . ?attribute ex:unit "rpm" . '
        'FILTER(?v > 15)',
    'any property, name known first': '?attribute ex:unit "words" . $this ?attribute [ ngsild:hasValue ?v ]',
    'any relationship': '$this ?r [ ngsild:hasObject ?p ] . ?p a ex:Part',
    'any relationship, on': '$this ?r [ ngsild:hasObject ?p ] . ?p ?a [ ngsild:hasValue ?w ] . FILTER(?w = "axle")',
    'two attributes, one value': '$this ?a [ ngsild:hasValue ?v ] . $this ?b [ ngsild:hasValue ?w ] . '
        'FILTER(?a = ex:speed && ?b = ex:limit && ?v > ?w)',
    'the same attribute of another': '$this ?a [ ngsild:hasValue ?v ] . ?o ?a [ ngsild:hasValue ?w ] . '
        '?o a ex:Press . FILTER(?v < ?w)',
    # numbers are numbers
    'greater': '$this ex:speed [ ngsild:hasValue ?v ] ; ex:limit [ ngsild:hasValue ?w ] . FILTER(?v > ?w)',
    'less': '$this ex:speed [ ngsild:hasValue ?v ] ; ex:limit [ ngsild:hasValue ?w ] . FILTER(?v < ?w)',
    'at least': '$this ex:speed [ ngsild:hasValue ?v ] ; ex:limit [ ngsild:hasValue ?w ] . FILTER(?v >= ?w)',
    'than a constant': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v >= 10)',
    'a constant than': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(10 > ?v)',
    'than a decimal': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v > 100.25)',
    'equal': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v = 7)',
    'not equal': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v != 7)',
    'one of': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v IN (5, 9))',
    'none of': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v NOT IN (5, 9))',
    'cast': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(xsd:double(?v) > 9.5)',
    'cast against a variable': '$this ex:speed [ ngsild:hasValue ?v ] ; ex:limit [ ngsild:hasValue ?w ] . '
        'FILTER(xsd:double(?v) > ?w)',
    'decimal cast': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER(xsd:decimal(?v) < 9.5)',
    'texts': '$this ex:text [ ngsild:hasValue ?v ] . FILTER(?v > "abc")',
    'optional first': 'OPTIONAL { $this ex:limit [ ngsild:hasValue ?max ] } '
        'OPTIONAL { $this ex:text [ ngsild:hasValue ?t ] } '
        '$this ex:speed [ ngsild:hasValue ?v ] . '
        'FILTER((bound(?max) && ?v > ?max) || (bound(?t) && ?t = "abc"))',
    'optional last': '$this ex:speed [ ngsild:hasValue ?v ] . OPTIONAL { $this ex:limit [ ngsild:hasValue ?max ] } '
        'FILTER(!bound(?max))',
    'not exists': 'FILTER NOT EXISTS { $this ex:speed [ ngsild:hasValue ?v ] }',
    'exists': 'FILTER EXISTS { $this ex:hasPart [ ngsild:hasObject ?p ] }',
    'not exists any': 'FILTER NOT EXISTS { $this ?attribute [ ngsild:hasValue ?v ] }',
    'not exists a value': '$this ex:limit [ ngsild:hasValue ?w ] . '
        'FILTER NOT EXISTS { $this ex:state [ ngsild:hasValue ex:on ] }',
    'not exists, the same attribute': '$this ex:state [ ngsild:hasValue ?s ] . '
        'FILTER NOT EXISTS { $this ex:state [ ngsild:hasValue ex:on ] }',
    'exists, the same attribute': '$this ex:state [ ngsild:hasValue ?s ] . '
        'FILTER EXISTS { $this ex:state [ ngsild:hasValue ex:off ] }',
    'exists, the same attribute of another': '$this ex:speed [ ngsild:hasValue ?v ] . '
        'FILTER EXISTS { ?o ex:speed [ ngsild:hasValue ?w ] . ?o a ex:Press . '
        'FILTER(?w > ?v) }',
    'not exists, with an outer value': '$this ex:speed [ ngsild:hasValue ?v ] . '
        'FILTER NOT EXISTS { $this ex:limit [ ngsild:hasValue ?w ] . FILTER(?w >= ?v) }',
    'not exists, any of the same': '$this ?a [ ngsild:hasValue ex:on ] . '
        'FILTER NOT EXISTS { $this ?b [ ngsild:hasValue "abc" ] }',
    'not exists, over a relationship': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'FILTER NOT EXISTS { $this ex:hasPart [ ngsild:hasObject ?p ] }',
    'exists, in two': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'FILTER EXISTS { $this ex:state [ ngsild:hasValue ex:on ] } '
        'FILTER NOT EXISTS { $this ex:state [ ngsild:hasValue ex:off ] }',
    'optional, then compared': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'OPTIONAL { $this ex:state [ ngsild:hasValue ?s ] } FILTER(!bound(?s) || ?s = ex:off)',
    'optional constant': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'OPTIONAL { $this ex:state [ ngsild:hasValue ex:on ] . $this ex:text [ ngsild:hasValue ?t ] } '
        'FILTER(bound(?t))',
    'optional relationship': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'OPTIONAL { $this ex:hasPart [ ngsild:hasObject ?p ] . '
        '?p ex:weight [ ngsild:hasValue ?w ] } '
        'FILTER(!bound(?w) || ?w > 5)',
    'optional three': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'OPTIONAL { $this ex:speed [ ngsild:hasValue ?v ] . $this ex:text [ ngsild:hasValue ?t ] . '
        '$this ex:state [ ngsild:hasValue ?s ] . FILTER(?v > 9) } FILTER(bound(?s))',
    'optional with a filter': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'OPTIONAL { $this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v > ?l) } '
        'FILTER(!bound(?v))',
    'one value in two attributes': '$this ex:limit [ ngsild:hasValue ?v ] . $this ex:bound [ ngsild:hasValue ?v ]',
    'one value of two entities': '?o a ex:Press . $this ex:speed [ ngsild:hasValue ?v ] . '
        '?o ex:speed [ ngsild:hasValue ?v ]',
    'one target twice': '$this ex:hasPart [ ngsild:hasObject ?p ] . $this ex:spare [ ngsild:hasObject ?p ]',
    'the time apart': '$this ex:speed [ ngsild:hasValue ?v ] . $this ex:speed [ ngsild:observedAt ?t ] . '
        'FILTER(?v < 6)',
    'of a certain entity': '<urn:m:1> ex:limit [ ngsild:hasValue ?v ] . $this ex:bound [ ngsild:hasValue ?v ]',
    'of another entity, by value': '$this ex:bound [ ngsild:hasValue ?v ] . ?o ex:limit [ ngsild:hasValue ?v ] . '
        'FILTER(?o != $this)',
    'a target that does not exist': '$this ex:dangling [ ngsild:hasObject <urn:nowhere:1> ]',
    'not a target that does not exist':
        'FILTER NOT EXISTS { $this ex:dangling [ ngsild:hasObject <urn:nowhere:1> ] }',
    'with a time': '$this ex:speed [ ngsild:hasValue ?v ; ngsild:observedAt ?t ]',
    'without a time': '$this ex:speed [ ngsild:hasValue ?v ] . '
        'FILTER NOT EXISTS { $this ex:speed [ ngsild:hasValue ?w ; ngsild:observedAt ?t ] }',
    'perhaps with a time': '$this ex:speed [ ngsild:hasValue ?v ] . '
        'OPTIONAL { $this ex:speed [ ngsild:observedAt ?t ] } FILTER(bound(?t))',
    'another name': '$this ex:limit [ ngsild:hasValue ?v ] . BIND(?v AS ?w) FILTER(?w > 9)',
    'a computed number': '$this ex:speed [ ngsild:hasValue ?v ] . $this ex:limit [ ngsild:hasValue ?l ] . '
        'BIND(xsd:float(?v) AS ?w) FILTER(?w > ?l)',
    'a chosen number': '$this ex:limit [ ngsild:hasValue ?v ] . BIND(IF(?v > 9, 100, 5) AS ?w) FILTER(?w > 20)',
    'backwards, then on': '$this ex:state [ ngsild:hasValue ?s ] . ?s ^ex:follows/ex:label "on"',
    'three steps': '$this ex:state/ngsild:hasValue/ex:follows/ex:follows ex:third',
    'a subclass': '$this a ?c . ?c rdfs:subClassOf* ex:Press',
    'optional in optional': '$this ex:limit [ ngsild:hasValue ?l ] . OPTIONAL { $this ex:speed [ ngsild:hasValue ?v ] '
        'OPTIONAL { $this ex:text [ ngsild:hasValue ?t ] . FILTER(?v > 8.5) } } FILTER(bound(?t))',
    'a time after an optional': '$this ex:speed [ ngsild:hasValue ?v ] . OPTIONAL { $this ex:limit [ ngsild:hasValue '
        '?l ] } $this ex:speed [ ngsild:observedAt ?t ]',
    'a number bound before': 'BIND(20 AS ?w) . $this ex:limit [ ngsild:hasValue ?w ]',
    'a target and an entity of one IRI': '$this ex:hasPart [ ngsild:hasObject <urn:p:2> ] . <urn:p:2> ex:name '
        '[ ngsild:hasValue ?x ]',
    'one time in two attributes': '$this ex:speed [ ngsild:hasValue ?v ; ngsild:observedAt ?t ] . '
        '$this ?r [ ngsild:hasObject ?p ; ngsild:observedAt ?t ]',
    'a superclass nothing declares': '$this a ?c . ?c rdfs:subClassOf* ex:Base',
    'one value, with the knowledge': '$this ex:state [ ngsild:hasValue ?s ] . ex:on ex:follows ?s',
    'with the knowledge': '$this ex:limit [ ngsild:hasValue ?v ] ; ex:state [ ngsild:hasValue ?s ] . '
        '?s ex:maximum ?max . FILTER(?v < ?max)',
    'optional with the knowledge': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'OPTIONAL { $this ex:state [ ngsild:hasValue ?s ] . ?s ex:maximum ?max } '
        'FILTER(bound(?max))',
    'two named instances': '$this ex:speed ?a . ?a ngsild:hasValue ?v . $this ex:limit ?b . ?b ngsild:hasValue ?w . '
        'FILTER(?v > ?w)',
    'a named instance in not exists': 'FILTER NOT EXISTS { $this ex:speed ?a . ?a ngsild:hasValue ?v }',
    'exists, the same relationship': '$this ex:hasPart [ ngsild:hasObject ?p ] . '
        'FILTER EXISTS { $this ex:hasPart [ ngsild:hasObject ?p ] . '
        '?p ex:weight [ ngsild:hasValue ?w ] . FILTER(?w > 5) }',
    'not exists, the same relationship': '$this ex:limit [ ngsild:hasValue ?l ] . '
        'FILTER NOT EXISTS { $this ex:hasPart [ ngsild:hasObject <urn:p:1> ] }',
    'a relationship between two known': '$this ex:hasPart [ ngsild:hasObject ?p ] . '
        '$this ?r [ ngsild:hasObject ?p ] . ?p ex:name [ ngsild:hasValue "axle" ]',
    'class': '$this a ex:Press',
    'and or': '$this ex:speed [ ngsild:hasValue ?v ] . FILTER((?v > 9 && ?v < 50) || ?v = 5)',
    'iri of a state': '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:label "off"',
    'a blank node of the knowledge': '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows [ ex:follows ?x ]',
    'a blank node of the knowledge, compared': '$this ex:state [ ngsild:hasValue ?s ] . '
                                               '?s ex:follows [ ex:label ?l ] . FILTER(?l = "off")',
    'a text of the knowledge in a blank node': '$this ex:text [ ngsild:hasValue ?t ] . ex:on ex:words [ ex:w ?t ]',
    'path in the knowledge': '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows/ex:label "off"',
    'inverse path': '$this ex:state [ ngsild:hasValue ?s ] . ?s ^ex:follows ex:on',
}

REFUSED = {
    'plain triple': ('$this ex:speed ?v', 'ngsild:hasValue'),
    'any plain triple': ('$this ?p ?o', 'variable as predicate'),
    'sub-attribute': ('$this ex:speed [ ngsild:hasValue ?v ; ex:trust [ ngsild:hasValue ?t ] ]', 'sub-attribute'),
    'unit': ('$this ex:speed [ ngsild:unitCode ?u ; ngsild:hasValue ?v ]', 'unitCode'),
    'union': ('{ $this ex:speed [ ngsild:hasValue ?v ] } UNION { $this ex:limit [ ngsild:hasValue ?v ] }', 'UNION'),
    'values': ('VALUES ?v { 1 2 } $this ex:speed [ ngsild:hasValue ?v ]', 'VALUES'),
    'minus': ('$this ex:speed [ ngsild:hasValue ?v ] MINUS { $this ex:limit [ ngsild:hasValue ?v ] }', 'MINUS'),
    'alternative path': ('$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows|ex:label ?x', 'path'),
    'loose optional': ('OPTIONAL { $this ?a [ ngsild:hasValue ?v ] . ?a ex:unit "words" } '
                       '$this ex:limit [ ngsild:hasValue ?l ]', 'OPTIONAL'),
    'two values': ('$this ex:speed [ ngsild:hasValue ?v ] . $this ex:speed [ ngsild:hasValue ?w ]', 'two values'),
    'two values, one optional': ('$this ex:speed [ ngsild:hasValue ?v ] . '
                                 'OPTIONAL { $this ex:speed [ ngsild:hasValue ?w ] }', 'two values'),
    'two constants': ('$this ex:state [ ngsild:hasValue ex:on ] . $this ex:state [ ngsild:hasValue ex:off ]',
                      'two values'),
    'two values of any': ('$this ?a [ ngsild:hasValue ?v ] . $this ?a [ ngsild:hasValue ?w ]', 'two values'),
    'two targets': ('$this ex:hasPart [ ngsild:hasObject ?p ] . $this ex:hasPart [ ngsild:hasObject ?q ]',
                    'two targets'),
    'one or more': ('$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows+ ex:third', 'path'),
    'any number of': ('$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows* ex:third', 'path'),
    'a sequence with any number of': ('$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows*/ex:label "off"', 'path'),
    'optional, read already': ('$this ex:speed [ ngsild:hasValue ?v ] . OPTIONAL { $this ex:speed '
                               '[ ngsild:observedAt ?t ] . FILTER(?v > 100) } FILTER(bound(?t))', 'OPTIONAL'),
    'entities joined by a time': ('$this ex:speed [ ngsild:hasValue ?v ; ngsild:observedAt ?t ] . '
                                  '?o ex:hasPart [ ngsild:hasObject ?p ; ngsild:observedAt ?t ]', 'not connected'),
    'a number of the knowledge after': (
        '$this ex:limit [ ngsild:hasValue ?v ] . ?s ex:maximum ?v',
        'literal of the knowledge'),
    'a number of the knowledge before': (
        'ex:on ex:maximum ?m . $this ex:limit [ ngsild:hasValue ?m ]',
        'literal of the knowledge'),
    'a number of the knowledge in exists': (
        '$this ex:limit [ ngsild:hasValue ?v ] . FILTER EXISTS { ?s ex:maximum ?v }',
        'literal of the knowledge'),
    'another name of an entity': (
        '$this ex:hasPart [ ngsild:hasObject ?p ] . BIND(?p AS ?q) FILTER(?q = <urn:p:1>)',
        'another name for an entity'),
    'another name, read on': (
        '$this ex:hasPart [ ngsild:hasObject ?p ] . BIND(?p AS ?q) . '
        '?q ex:weight [ ngsild:hasValue ?w ] . FILTER(?w > 5)',
        'another name for an entity'),
    'the knowledge first, in exists': (
        '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:word ?m . '
        'FILTER EXISTS { $this ex:text [ ngsild:hasValue ?m ] }',
        'literal of the knowledge'),
    'the knowledge first, in not exists': (
        '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:word ?m . '
        'FILTER NOT EXISTS { $this ex:bound [ ngsild:hasValue ?m ] } '
        'FILTER NOT EXISTS { $this ex:hasPart [ ngsild:hasObject ?p ] }',
        'literal of the knowledge'),
    'the knowledge first, not in exists': (
        '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:word ?m . '
        'FILTER NOT EXISTS { $this ex:text [ ngsild:hasValue ?m ] }',
        'literal of the knowledge'),
    'the knowledge first, optional': (
        '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:word ?m . '
        'OPTIONAL { $this ex:text [ ngsild:hasValue ?m ] } '
        'FILTER(?m = "abc" && ?s = ex:on) FILTER NOT EXISTS { $this ex:text ?a . '
        '?a ngsild:hasValue "x" }',
        'literal of the knowledge'),
    'a constant in a blank node of the knowledge': (
        '$this ex:state [ ngsild:hasValue ?s ] . ?s ex:follows [ ex:label "off" ]', '?s ex:follows [ ex:label "off" ]'),
    'another name, as a target': (
        '$this ex:hasPart [ ngsild:hasObject ?p ] . BIND(?p AS ?q) . ?m ex:spare [ ngsild:hasObject ?q ] . '
        'FILTER(?m != $this)', 'another name for an entity'),
    'another name, in an optional': (
        '$this ex:hasPart [ ngsild:hasObject ?p ] . OPTIONAL { BIND(?p AS ?q) } '
        '?q ex:weight [ ngsild:hasValue ?w ] . FILTER(?w > 5)', 'another name for an entity'),
    'another name, of an entity by its IRI': (
        '$this ex:hasPart [ ngsild:hasObject ?p ] . BIND(?p AS ?q) . <urn:m:5> ex:spare [ ngsild:hasObject ?q ]',
        'another name for an entity'),
    'read again after an optional first': (
        'OPTIONAL { $this ex:speed [ ngsild:hasValue ?v ] . FILTER(?v > 100) } $this ex:speed [ ngsild:observedAt ?t ]',
        'read again'),
    'read again after an optional that finds nothing': (
        '$this ex:limit [ ngsild:hasValue ?l ] . OPTIONAL { $this ex:speed [ ngsild:hasValue ?v ] . '
        '$this ex:nothing [ ngsild:hasValue ?n ] } $this ex:speed [ ngsild:observedAt ?t ]', 'read again'),
    'a loose blank node': ('$this ex:hasPart [ ngsild:hasObject ?p ] . [] ex:spare ?p', 'blank node'),
    'a blank node with a constant': (
        '$this ex:hasPart [ ngsild:hasObject ?p ] . [] ex:follows ex:off', '[ ex:follows ex:off ]'),
    'read again after an optional': (
        '$this ex:spare [ ngsild:hasObject ?p ] . OPTIONAL { $this ex:speed [ ngsild:hasValue ?v ] . '
        'FILTER(?v > 100) } $this ex:speed [ ngsild:observedAt ?t ]', 'read again'),
    'an entity by its IRI in an optional': (
        '$this ex:limit [ ngsild:hasValue ?l ] . OPTIONAL { $this ex:hasPart [ ngsild:hasObject <urn:p:2> ] . '
        '<urn:p:2> ex:weight [ ngsild:hasValue ?w ] } FILTER(bound(?w))', 'IRI'),
    'instance of two': ('$this ex:speed ?a . $this ex:limit ?a . ?a ngsild:hasValue ?v', 'two attributes'),
    'function': ('$this ex:text [ ngsild:hasValue ?v ] . FILTER(regex(?v, "a"))', 'regex'),
    'unbound': ('$this ex:speed [ ngsild:hasValue ?v ] . FILTER(?nobody > 5)', '?nobody'),
    'unbound test': ('$this ex:speed [ ngsild:hasValue ?v ] . FILTER(bound(?nobody))', '?nobody'),
    'a second root': ('?m ex:hasPart [ ngsild:hasObject ?p ] . FILTER(?m = $this)', 'not connected'),
    'loose': ('$this ex:speed [ ngsild:hasValue ?v ] . ?x ex:follows ?y', 'not connected'),
    'syntax': ('$this ex:speed [ ngsild:hasValue ?v ', 'parse'),
}


def select(where):
    return f'{PREFIXES}SELECT $this WHERE {{ {where} }}'


@pytest.fixture(scope='module')
def platform(tmp_path_factory):
    """(graph the query is written against, graph it is compiled with, database)."""
    root = str(tmp_path_factory.mktemp('platform'))

    def write(name, text):
        with open(os.path.join(root, name), 'w') as handle:
            handle.write(text)
    write('shacl.ttl', SHAPES)
    write('knowledge.ttl', KNOWLEDGE)
    write('model.jsonld', json.dumps([dict(entity, **CONTEXT) for entity in MODEL]))
    os.makedirs(os.path.join(root, 'output'))
    for script, args in (('create_rdf_table.py', ['knowledge.ttl']), ('create_core_tables.py', []),
                         ('create_ngsild_tables.py', []),
                         ('create_ngsild_models.py', ['shacl.ttl', 'knowledge.ttl', 'model.jsonld'])):
        subprocess.run([sys.executable, os.path.join(TOOLS, script)] + args, cwd=root, check=True,
                       env=dict(os.environ, PYTHONPATH=TOOLS), capture_output=True)
    database = sqlite3.connect(':memory:')
    database.create_function('REGEXP', 2, lambda pattern, text: text is not None and
                             re.search(pattern, str(text)) is not None)
    for name in ('rdf', 'core', 'ngsild', 'ngsild-models'):
        with open(os.path.join(root, 'output', f'{name}.sqlite')) as handle:
            database.executescript(handle.read())
    written = rdflib.Graph()
    text, base = read_jsonld(os.path.join(root, 'model.jsonld'))
    written.parse(data=text, format='json-ld', publicID=base)
    knowledge = utils.load_graph(os.path.join(root, 'shacl.ttl'), os.path.join(root, 'knowledge.ttl'))
    compiled_with = utils.transitive_closure(knowledge)
    written.parse(data=KNOWLEDGE, format='turtle')
    return written, compiled_with, database


MACHINES = [f'urn:m:{n}' for n in range(1, 8)]
PARTS = ['urn:p:1', 'urn:p:2']


def in_sparql(graph, where, entities=MACHINES):
    """Each entity on its own, $this bound to it: as SHACL runs a constraint."""
    query = select(where)
    return [entity for entity in entities
            if len(list(graph.query(query, initBindings={'this': rdflib.URIRef(entity)})))]


def in_sql(platform, where, target='Machine'):
    sql, _ = translate_sparql(None, None, select(where), rdflib.URIRef(EX + target), platform[1])
    utils.process_sql_dialect(sql, False)                       # what Flink gets is complete, too
    rows = platform[2].execute(utils.process_sql_dialect(sql, True)).fetchall()
    return sorted({row[0] for row in rows})


@pytest.mark.parametrize('name', sorted(SAME))
def test_a_query_answers_the_same(platform, name):
    expected = in_sparql(platform[0], SAME[name])
    assert expected, 'a query nothing answers proves nothing'
    assert expected != MACHINES, 'nor does one everything answers'
    assert in_sql(platform, SAME[name]) == expected


@pytest.mark.parametrize('where', [
    '?m ex:hasPart [ ngsild:hasObject $this ] . ?m ex:state [ ngsild:hasValue ?s ]',
    '?m ?relationship [ ngsild:hasObject $this ] . ?m ex:state [ ngsild:hasValue ex:on ]',
    '?m ex:hasPart [ ngsild:hasObject $this ] . ?m ex:limit [ ngsild:hasValue ?l ] . FILTER(?l > 5)',
    '?m ex:hasPart [ ngsild:hasObject $this ] . ?m a ex:Press',
    '?m ?r [ ngsild:hasObject $this ] . ?r ex:unit "pieces" . ?m a ex:Press',
    '<urn:m:4> ex:hasPart [ ngsild:hasObject $this ]'])
def test_a_query_from_the_other_end(platform, where):
    """What points at the target, whatever it is."""
    expected = in_sparql(platform[0], where, PARTS)
    assert len(expected) == 1
    assert in_sql(platform, where, 'Part') == expected


@pytest.mark.parametrize('name', sorted(REFUSED))
def test_what_is_not_compiled_is_refused_by_name(platform, name):
    where, said = REFUSED[name]
    problems = check(platform[1], draft={'target': rdflib.URIRef(EX + 'Machine'), 'query': select(where)})
    assert len(problems) == 1 and said.lower() in problems[0].reason.lower(), problems
    assert 'defect' not in problems[0].reason


@pytest.mark.parametrize('text, number', [('5', True), ('-5.5', True), ('.5', True), ('5.', True), ('1e+21', True),
                                          ('5d', False), ('0x10', False), (' 5 ', False), ('NaN', False),
                                          ('Infinity', False), ('', False), ('abc', False)])
def test_what_is_a_number(platform, text, number):
    """By one pattern on both targets: Flink's own conversion takes more than SQLite's."""
    quoted = text.replace("'", "''")
    sql = utils.process_sql_dialect(f"SQL_DIALECT_NUMBER{{'{quoted}'}}", True)
    assert (platform[2].execute(f'SELECT {sql}').fetchone()[0] is not None) == number
    assert utils.NUMBER_TEXT in utils.process_sql_dialect("SQL_DIALECT_NUMBER{x}", False)


def test_a_target_that_is_read_is_an_entity(platform):
    """The one thing in which the platform knows more than the graph: a target
    nobody created, or that was deleted, is no solution."""
    where = '$this ex:dangling [ ngsild:hasObject ?p ]'
    assert in_sparql(platform[0], where) == ['urn:m:1']
    assert in_sql(platform, where) == []
