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

"""A constraint holds in a case only where the case checked something.

An entity without an attribute satisfies that attribute's maxCount, datatype
and value form -- of nothing. Counted as "holds", an empty valid case made
every attribute of its type look tested: a user's MeasurementsType page said
"tested both ways" for hasAmbientHumidity because a bad case fired it and an
empty good case "held" it, and removing the attribute from the good case
changed nothing. Leaving an attribute out tests presence, and that is proven
where its absence makes minCount FIRE.
"""

import pytest
from rdflib import Graph

from semforge.expect import coverage
from semforge.expect.store import Example
from semforge.validate.orchestrator import validate_graphs
from semforge.validate.results import Status

SHAPES = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:TShape a sh:NodeShape ; sh:targetClass ex:T ;
  sh:property [ sh:path ex:hasA ; sh:minCount 0 ; sh:maxCount 1 ; sh:nodeKind sh:BlankNode ;
    sh:property [ sh:path ngsi-ld:hasValue ; sh:datatype xsd:double ] ] ;
  sh:property [ sh:path ex:hasState ; sh:nodeKind sh:BlankNode ;
    sh:property [ sh:path ex:hasMode ; sh:maxCount 1 ] ] .
'''
PREFIXES = '''
@prefix ex: <https://example.org/> .
@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
'''
EMPTY = PREFIXES + '<urn:e> a ex:T .'
GOOD = PREFIXES + '<urn:e> a ex:T ; ex:hasA [ a ngsi-ld:Property ; ngsi-ld:hasValue "1.5"^^xsd:double ] .'
BAD = PREFIXES + '<urn:e> a ex:T ; ex:hasA [ a ngsi-ld:Property ; ngsi-ld:hasValue "x" ] .'
NESTED = PREFIXES + '<urn:e> a ex:T ; ex:hasState [ a ngsi-ld:Property ; ex:hasMode [ ngsi-ld:hasValue 1 ] ] .'


def _report(data):
    return validate_graphs(Graph().parse(data=data, format='turtle'),
                           Graph().parse(data=SHAPES, format='turtle'), Graph(), strict=False)


def _conformant(report, attribute):
    return {r.component: r.vacuous for r in report.results
            if r.attribute == attribute and r.status is Status.CONFORMANT}


def test_an_absent_attribute_holds_of_nothing():
    marks = _conformant(_report(EMPTY), 'hasA')
    assert marks and all(marks.values()), marks


def test_a_present_attribute_holds_for_real():
    marks = _conformant(_report(GOOD), 'hasA')
    assert marks and not any(marks.values()), marks


def test_a_sub_attribute_counts_where_it_is():
    """NGSI-LD attributes are blank nodes: a sub-attribute hangs off its
    attribute, not the entity."""
    assert not any(_conformant(_report(NESTED), 'hasMode').values())
    assert all(_conformant(_report(EMPTY), 'hasMode').values())


def _entries(*cases):
    return {e.constraint.split('/', 1)[1]: e for e in coverage(
        [(Example(path=name), _report(data)) for name, data in cases])}


def test_an_empty_valid_case_proves_nothing_held():
    """The user's MeasurementsType: fired in a bad case, 'held' in an empty
    one -- 'tested both ways'. Now: fires only."""
    entries = _entries(('bad.jsonld', BAD), ('empty.jsonld', EMPTY))
    datatype = entries['hasA/DatatypeConstraintComponent']
    assert datatype.firing_examples == ['bad.jsonld']
    assert datatype.conforming_examples == []
    assert datatype.status == 'no-conforming-example'


def test_a_case_with_a_valid_value_proves_it_held():
    entries = _entries(('bad.jsonld', BAD), ('good.jsonld', GOOD))
    assert entries['hasA/DatatypeConstraintComponent'].status == 'two-sided'


def test_an_attribute_no_case_has_is_not_covered_at_all():
    """Neither side: the page says untested, not 'never fired'."""
    entries = _entries(('empty.jsonld', EMPTY), ('good.jsonld', GOOD))
    assert not any(name.startswith('hasMode/') for name in entries)


@pytest.mark.parametrize('cases, status', [
    ((('bad.jsonld', BAD), ('empty.jsonld', EMPTY)), 'fires only'),
    ((('bad.jsonld', BAD), ('good.jsonld', GOOD)), 'both ways'),
    ((('empty.jsonld', EMPTY),), None),
])
def test_the_type_page_row_says_so(cases, status):
    from semforge.cooked.typepage import _known_coverage

    rows = _known_coverage([(Example(path=name), None, _report(data)) for name, data in cases])
    assert rows.get(('ex:TShape', 'hasA')) == status


INVERSE_SHAPES = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
ex:CShape a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ( [ sh:inversePath ngsi-ld:hasObject ] [ sh:inversePath ex:hasC ] ) ;
                sh:maxCount 1 ] .
'''
INVERSE_DATA = PREFIXES + '''
<urn:f> a ex:F ; ex:hasC [ a ngsi-ld:Relationship ; ngsi-ld:hasObject <urn:c> ] .
<urn:c> a ex:C .
<urn:lone> a ex:C .
'''


def test_an_inverse_relationship_counts_where_something_points_at_it():
    """The kms' cartridge rule: one cartridge in at most one filter. The
    filter reaches it through the relationship's node, so the attribute's
    name is a step further back than the predicate that points at it."""
    report = validate_graphs(Graph().parse(data=INVERSE_DATA, format='turtle'),
                             Graph().parse(data=INVERSE_SHAPES, format='turtle'),
                             Graph(), strict=False)
    marks = {r.resource: r.vacuous for r in report.results
             if r.status is Status.CONFORMANT and r.component == 'MaxCountConstraintComponent'}
    assert marks == {'urn:c': False, 'urn:lone': True}, marks
