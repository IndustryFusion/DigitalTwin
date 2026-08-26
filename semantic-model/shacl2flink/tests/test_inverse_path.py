#
# Copyright (c) 2026 Intel Corporation
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

"""
Inverse NGSI-LD relationships: who points AT the focus node.

"A cartridge is installed in at most one filter" -- the focus node is the
REFERENCED entity and the value nodes are the entities referring to it, which
the forward machinery cannot express because it walks an entity down to its
OWN attributes.

The path spells out both hops, because NGSI-LD stores a relationship through
a blank node and a bare inverse of the relationship predicate therefore
matches nothing at all:

    sh:path ( [ sh:inversePath ngsi-ld:hasObject ]
              [ sh:inversePath iff:hasCartridge ] )
"""

import os
import tempfile

import pytest
import rdflib

import lib.shacl_properties_to_sql as props


SHAPES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

iff:ExclusiveCartridgeShape
    a sh:NodeShape ;
    sh:targetClass iff:FilterCartridge ;
    sh:property [ sh:path ( [ sh:inversePath ngsild:hasObject ]
                            [ sh:inversePath iff:hasCartridge ] ) ;
                  sh:maxCount 1 ] .
"""

FORBIDDEN = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

iff:ExclusiveCartridgeShape
    a sh:NodeShape ;
    sh:targetClass iff:FilterCartridge ;
    sh:property [ sh:path ( [ sh:inversePath ngsild:hasObject ]
                            [ sh:inversePath iff:hasCartridge ] ) ;
                  sh:maxCount 0 ] .
"""

WITH_CLASS = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

iff:ExclusiveCartridgeShape
    a sh:NodeShape ;
    sh:targetClass iff:FilterCartridge ;
    sh:property [ sh:path ( [ sh:inversePath ngsild:hasObject ]
                            [ sh:inversePath iff:hasCartridge ] ) ;
                  sh:maxCount 1 ;
                  sh:class iff:Filter ] .
"""

BARE = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

iff:ExclusiveCartridgeShape
    a sh:NodeShape ;
    sh:targetClass iff:FilterCartridge ;
    sh:property [ sh:path [ sh:inversePath iff:hasCartridge ] ;
                  sh:maxCount 1 ] .
"""

NESTED_PATH = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

iff:ExclusiveCartridgeShape
    a sh:NodeShape ;
    sh:targetClass iff:FilterCartridge ;
    sh:property [ sh:path ( [ sh:inversePath ngsild:hasObject ]
                            [ sh:inversePath [ sh:alternativePath ( iff:hasCartridge iff:hasSpare ) ] ] ) ;
                  sh:maxCount 1 ] .
"""

UNBOUNDED = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

iff:ExclusiveCartridgeShape
    a sh:NodeShape ;
    sh:targetClass iff:FilterCartridge ;
    sh:property [ sh:path ( [ sh:inversePath ngsild:hasObject ]
                            [ sh:inversePath iff:hasCartridge ] ) ] .
"""

KNOWLEDGE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
iff:FilterCartridge a rdfs:Class .
"""

PREFIXES = {
    'sh': rdflib.Namespace('http://www.w3.org/ns/shacl#'),
    'rdfs': rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#'),
    'rdf': rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#'),
    'ngsi-ld': rdflib.Namespace('https://uri.etsi.org/ngsi-ld/'),
    'iff': rdflib.Namespace('https://industry-fusion.com/types/v0.9/'),
}


def _translate(shapes_ttl, tmp_path):
    shapes, knowledge = tmp_path / 'shacl.ttl', tmp_path / 'knowledge.ttl'
    shapes.write_text(shapes_ttl)
    knowledge.write_text(KNOWLEDGE)
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())          # translate() writes into ./output
    try:
        sqlite, _ = props.translate(str(shapes), str(knowledge), PREFIXES)
    finally:
        os.chdir(cwd)
    return sqlite


@pytest.fixture(scope='module')
def translated(tmp_path_factory):
    return _translate(SHAPES, tmp_path_factory.mktemp('inverse'))


def test_inverse_shape_lands_in_constraint_table(translated):
    """The constraint row carries the marker, the FORWARD path and the bound.

    The marker keeps the row out of every attribute-shaped template, all of
    which select on genuine NGSI-LD type IRIs; the forward path is what the
    check joins attribute names against.
    """
    row = next((line for line in translated.splitlines()
                if 'constraint_table' in line and
                props.INVERSE_RELATIONSHIP_TYPE in line), None)
    assert row is not None, 'no constraint row with the inverse marker'
    assert 'https://industry-fusion.com/types/v0.9/hasCartridge' in row
    assert 'FilterCartridge' in row


def test_inverse_check_groups_by_the_referenced_entity(translated):
    """The event name says inverse (^) and referrers are counted DISTINCT.

    DISTINCT is SHACL semantics: the value nodes of an inverse path are a SET
    of referring entities, so a referrer with two attribute instances of the
    relationship still counts once.
    """
    assert "'CountConstraintComponent(^' ||" in translated
    assert 'COUNT(DISTINCT CASE WHEN NOT edeleted AND NOT adeleted ' \
           'AND NOT redeleted THEN referrer' in translated


def test_inverse_check_reads_every_liveness_flag(translated):
    """A reference has two owners and the focus node is a third liveness.

    adeleted covers the attribute row, redeleted the REFERRING entity,
    edeleted the focus node -- a deleted referrer whose attribute rows have
    not been swept must not keep a violation alive, and a deleted focus node
    must not alert at all.
    """
    assert 'MAX(CASE WHEN edeleted THEN 1 ELSE 0 END) = 0' in translated
    assert "COALESCE(R.`deleted`, false) as adeleted" in translated
    assert "IFNULL(RE.`deleted`, false) as redeleted" in translated


def test_inverse_check_pins_its_state(translated):
    """Join inputs and the accumulator are pinned never-expire.

    The group key is the attribute VALUE, so re-pointing a reference migrates
    rows between groups: the retraction landing in the OLD group is what
    clears its violation, and an expired accumulator would drop it in silence
    and freeze the alert forever.
    """
    assert "STATE_TTL('A' = '0d', 'D' = '0d', 'R' = '0d', 'RE' = '0d')" \
        in translated
    inverse_part = translated[translated.find('CountConstraintComponent(^'):]
    assert "STATE_TTL('A1' = '0d')" in translated
    assert inverse_part, 'inverse check missing entirely'


def test_maxcount_zero_compiles(tmp_path_factory):
    """'must not be referenced at all' is a bound of ZERO, not a missing one.

    rdflib.Literal(0) is falsy, so a truthiness test would read this shape as
    'no bound given' and drop it from the build -- the exact failure the
    zero-valued-parameter discipline exists to prevent, and the one that makes
    a decommissioning guard silently unenforced.
    """
    translated = _translate(FORBIDDEN, tmp_path_factory.mktemp('forbidden'))
    row = next((line for line in translated.splitlines()
                if 'constraint_table' in line and
                props.INVERSE_RELATIONSHIP_TYPE in line), None)
    assert row is not None, 'sh:maxCount 0 on an inverse path was dropped'
    assert "'0'" in row, f'the zero bound is not in the constraint row: {row}'


def test_unsupported_parameter_on_inverse_shape_fails_loud(tmp_path_factory):
    """sh:class on an inverse shape is not evaluated, so it must not compile.

    Only count bounds are checked on an inverse path. Accepting sh:class
    would ship 'every referrer must be a Filter' as a constraint nobody
    evaluates.
    """
    with pytest.raises(Exception, match='does not evaluate'):
        _translate(WITH_CLASS, tmp_path_factory.mktemp('withclass'))


def test_bare_inverse_path_fails_loud(tmp_path_factory):
    """A bare sh:inversePath matches NOTHING in NGSI-LD, so it is refused.

    NGSI-LD stores a relationship through a blank node, so nothing points at
    the target entity with the relationship's own predicate: a standard SHACL
    engine reports no violation for this shape, whatever the data. Giving it
    the meaning the author intended would make this compiler disagree with
    the reference engine about what a shape MEANS, so the build fails and
    names the spelling that works.
    """
    with pytest.raises(Exception, match='reaches its target through'):
        _translate(BARE, tmp_path_factory.mktemp('bare'))


def test_nested_second_hop_fails_loud(tmp_path_factory):
    """The second hop must name a plain predicate.

    A path expression there never matches the extraction pattern, so without
    this the shape would vanish from the build without a word.
    """
    with pytest.raises(Exception, match='not a supported NGSI-LD'):
        _translate(NESTED_PATH, tmp_path_factory.mktemp('nested'))


def test_unbounded_inverse_path_fails_loud(tmp_path_factory):
    """An inverse path without a count bound constrains nothing.

    Accepting it would ship a shape that is never checked, which is the
    failure mode the fail-loud pass exists to prevent.
    """
    with pytest.raises(Exception, match='produced no constraint'):
        _translate(UNBOUNDED, tmp_path_factory.mktemp('unbounded'))
