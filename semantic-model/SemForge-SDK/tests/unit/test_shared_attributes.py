"""One attribute, several unrelated types: its rdfs:domain becomes a union.

`rdfs:domain A , B` says every carrier is an A AND a B; the union says an A
or a B, which is what sharing an attribute means. So SemForge writes the
union -- and reads both forms as "any of", because generated packages (the
OPC UA mapping writes one triple per type) mean the union by the triples.
"""

import shutil
import subprocess
import sys
import os
from unittest import mock

import pytest
from rdflib import URIRef
from rdflib.namespace import SH

from semforge.cooked.choices import attribute_terms, attributes_for, domains_of
from semforge.cooked.constrain import add_attribute_constraint, attribute_options
from semforge.cooked.knowledge import extend_domain
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
ENT = BASE + 'base_entities/'
STRENGTH = ENT + 'hasStrength'                  # the knowledge gives it to Filter
WORKPIECE = BASE + 'base_shacl/WorkpieceShape'
SEMFORGE = os.path.join(os.path.dirname(sys.executable), 'semforge')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _locals(iris):
    return [str(i).rsplit('/', 1)[-1] for i in iris]


# --- reading ----------------------------------------------------------------------------

def test_one_triple_several_triples_and_a_union_all_read_as_any_of(kms):
    knowledge = kms / 'knowledge.ttl'
    knowledge.write_text(_read(knowledge) + (
        '\niffBaseEntities:hasTwo a owl:DatatypeProperty ;\n'
        '    rdfs:domain iffBaseEntities:Filter , iffBaseEntities:Workpiece ;\n'
        '    rdfs:range <https://uri.etsi.org/ngsi-ld/Property> .\n'
        '\niffBaseEntities:hasUnion a owl:DatatypeProperty ;\n'
        '    rdfs:domain [ a owl:Class ; owl:unionOf ( iffBaseEntities:Filter '
        'iffBaseEntities:Workpiece ) ] ;\n'
        '    rdfs:range <https://uri.etsi.org/ngsi-ld/Property> .\n'))
    package = load(str(kms))
    assert _locals(domains_of(package.knowledge, STRENGTH)) == ['Filter']
    for name in ('hasTwo', 'hasUnion'):
        assert sorted(_locals(domains_of(package.knowledge, ENT + name))) == \
            ['Filter', 'Workpiece'], name
    terms = {t.label: t for t in attribute_terms(package)}
    assert terms['hasUnion'].domains == ('iffBaseEntities:Filter', 'iffBaseEntities:Workpiece')
    mine, _ = attributes_for(package, ENT + 'Workpiece')
    assert {'hasTwo', 'hasUnion'} <= {a.label for a in mine}
    assert 'hasStrength' not in {a.label for a in mine}


# --- writing the domain -----------------------------------------------------------------

def test_extending_a_one_class_domain_writes_the_union(kms):
    before = _read(kms / 'knowledge.ttl')
    done = extend_domain(load(str(kms)), STRENGTH, [ENT + 'Workpiece'])
    assert done['added'] == [ENT + 'Workpiece']
    after = _read(kms / 'knowledge.ttl')
    # Only hasStrength's own domain line changed, byte for byte.
    at = before.index('iffBaseEntities:hasStrength a')
    head, tail = before[:at], before[at:]
    assert head + tail.replace(
        '    rdfs:domain iffBaseEntities:Filter ;\n',
        '    rdfs:domain [ a owl:Class ;\n'
        '        owl:unionOf ( iffBaseEntities:Filter iffBaseEntities:Workpiece ) ] ;\n', 1) == after
    assert _locals(domains_of(load(str(kms)).knowledge, STRENGTH)) == ['Filter', 'Workpiece']


def test_extending_a_union_appends_and_a_repeat_changes_nothing(kms):
    extend_domain(load(str(kms)), STRENGTH, [ENT + 'Workpiece'])
    extend_domain(load(str(kms)), STRENGTH, [ENT + 'FilterCartridge'])
    text = _read(kms / 'knowledge.ttl')
    assert 'owl:unionOf ( iffBaseEntities:Filter iffBaseEntities:Workpiece ' \
        'iffBaseEntities:FilterCartridge ) ]' in text
    assert extend_domain(load(str(kms)), STRENGTH, [ENT + 'Workpiece'])['added'] == []
    assert _read(kms / 'knowledge.ttl') == text


def test_several_triples_become_one_union(kms):
    knowledge = kms / 'knowledge.ttl'
    knowledge.write_text(_read(knowledge) + (
        '\niffBaseEntities:hasTwo a owl:DatatypeProperty ;\n'
        '    rdfs:domain iffBaseEntities:Filter ;\n'
        '    rdfs:label "two" ;\n'
        '    rdfs:domain iffBaseEntities:Workpiece ;\n'
        '    rdfs:range <https://uri.etsi.org/ngsi-ld/Property> .\n'))
    extend_domain(load(str(kms)), ENT + 'hasTwo', [ENT + 'FilterCartridge'])
    text = _read(knowledge)
    statement = text[text.index('iffBaseEntities:hasTwo a'):]
    assert statement.count('rdfs:domain') == 1
    assert 'rdfs:label "two" ;' in statement, 'the rest of the statement is untouched'
    assert sorted(_locals(domains_of(load(str(kms)).knowledge, ENT + 'hasTwo'))) == \
        ['Filter', 'FilterCartridge', 'Workpiece']


def test_an_attribute_without_a_domain_gets_one(kms):
    knowledge = kms / 'knowledge.ttl'
    knowledge.write_text(_read(knowledge) + (
        '\niffBaseEntities:hasNone a owl:DatatypeProperty ;\n'
        '    rdfs:range <https://uri.etsi.org/ngsi-ld/Property> .\n'))
    extend_domain(load(str(kms)), ENT + 'hasNone', [ENT + 'Workpiece'])
    assert _locals(domains_of(load(str(kms)).knowledge, ENT + 'hasNone')) == ['Workpiece']
    assert 'rdfs:domain iffBaseEntities:Workpiece' in _read(knowledge)


def test_a_rewrite_that_changes_more_than_the_domain_writes_nothing(kms):
    from semforge.cooked import knowledge

    before = _read(kms / 'knowledge.ttl')
    real = knowledge._domain_entry

    def lossy(text, classes):
        return real(text, classes[1:])             # drops the class it already had

    with mock.patch.object(knowledge, '_domain_entry', lossy), \
            pytest.raises(PackageError, match='more than its domain'):
        extend_domain(load(str(kms)), STRENGTH, [ENT + 'Workpiece'])
    assert _read(kms / 'knowledge.ttl') == before


# --- adding it to a shape ----------------------------------------------------------------

def test_without_the_extension_the_add_is_refused_and_says_how(kms):
    with pytest.raises(PackageError, match='with its domain extended'):
        add_attribute_constraint(load(str(kms)), WORKPIECE, STRENGTH)


def test_added_with_the_extension_it_is_on_the_shape_and_in_the_domain(kms):
    made = add_attribute_constraint(load(str(kms)), WORKPIECE, STRENGTH, extend_domain=True)
    assert made['domainAdded'] == ['iffBaseEntities:Workpiece']
    package = load(str(kms))
    paths = {o for g in package.shapes.objects(URIRef(WORKPIECE), SH.property)
             for o in package.shapes.objects(g, SH.path)}
    assert URIRef(STRENGTH) in paths
    assert _locals(domains_of(package.knowledge, STRENGTH)) == ['Filter', 'Workpiece']
    options = {o['label']: o for o in attribute_options(package, WORKPIECE)}
    assert options['hasStrength']['status'] == 'here'
    assert subprocess.run([SEMFORGE, 'test', str(kms)], capture_output=True).returncode == 0


def test_a_shape_that_cannot_take_it_leaves_the_knowledge_as_it_was(kms):
    from semforge.cooked import constrain

    before = _read(kms / 'knowledge.ttl')
    with mock.patch.object(constrain, '_add_to_shape', side_effect=PackageError('no')), \
            pytest.raises(PackageError, match='no'):
        add_attribute_constraint(load(str(kms)), WORKPIECE, STRENGTH, extend_domain=True)
    assert _read(kms / 'knowledge.ttl') == before


def test_declaring_it_again_says_where_it_is_and_how_to_share_it(kms):
    from semforge.cooked.knowledge import add_attribute_term

    with pytest.raises(PackageError, match='already declared, for Filter.*Declared for '
                                           'other types'):
        add_attribute_term(load(str(kms)), 'hasStrength', 'Property', 'iffBaseEntities:Workpiece')


# --- what reads it ----------------------------------------------------------------------

def test_the_knowledge_tree_lists_it_under_each_type(kms):
    from semforge.cooked.knowledge import build_knowledge, flatten

    extend_domain(load(str(kms)), STRENGTH, [ENT + 'Workpiece'])
    roots = build_knowledge(load(str(kms)))
    holders = [parent.label for parent, node in _with_parents(roots)
               if node.label == 'iffBaseEntities:hasStrength']
    assert {'iffBaseEntities:Filter', 'iffBaseEntities:Workpiece'} <= set(holders), holders
    assert flatten


def _with_parents(nodes, parent=None):
    for node in nodes:
        yield parent, node
        yield from _with_parents(node.children, node)


def test_the_type_page_of_the_new_type_shows_it(kms):
    from semforge.cooked.typepage import build_type_page

    add_attribute_constraint(load(str(kms)), WORKPIECE, STRENGTH, extend_domain=True)
    page = build_type_page(load(str(kms)), ENT + 'Workpiece')
    assert 'hasStrength' in {row['label'] for row in page['attributes']}


def test_a_sparql_term_names_every_type(kms):
    from semforge.sparql.terms import terms_for

    extend_domain(load(str(kms)), STRENGTH, [ENT + 'Workpiece'])
    term = terms_for(load(str(kms))).terms[STRENGTH]
    assert term.detail.endswith('on iffBaseEntities:Filter or iffBaseEntities:Workpiece')


# --- the server ------------------------------------------------------------------------

def test_the_server_passes_the_extension_on(kms):
    from semforge.editor import server

    uri = f'file://{kms}/shacl.ttl'
    with mock.patch.object(server, '_publish'):
        refused = server.add_attribute_constraint_feature(mock.MagicMock(), {
            'uri': uri, 'shape': WORKPIECE, 'attribute': STRENGTH})
        assert not refused['ok'] and 'domain extended' in refused['error']
        made = server.add_attribute_constraint_feature(mock.MagicMock(), {
            'uri': uri, 'shape': WORKPIECE, 'attribute': STRENGTH, 'extendDomain': True})
        assert made['ok'] and made['domainAdded'] == ['iffBaseEntities:Workpiece'], made
