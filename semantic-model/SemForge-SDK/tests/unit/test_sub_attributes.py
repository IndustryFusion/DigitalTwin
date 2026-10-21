"""Sub-attributes: an attribute hung off another attribute's node.

In NGSI-LD a sub-attribute (`hasTrust` inside `hasFilter`) is carried by the
parent's attribute node, so everything about it is one level down: the
knowledge declares its domain as the parent's KIND of node, the shape nests its
property shape inside the parent's, and the data puts it inside the parent's
instance. Each of those is checked here on a copy of the corpus.
"""

import json
import os
import shutil

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import SH, XSD

from semforge.cooked.constrain import (add_sub_attribute_constraint,
                                       sub_attribute_options)
from semforge.cooked.examples import add_attribute
from semforge.cooked.knowledge import add_attribute_term, attribute_namespaces
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
CUTTER = BASE + 'base_shacl/CutterShape'
MACHINE = BASE + 'base_shacl/MachineShape'
FILTER_REL = ['iffBaseEntities:hasFilter']
NGSILD = 'https://uri.etsi.org/ngsi-ld/'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _declare(root, name, kind, carrier):
    return add_attribute_term(load(root), name, kind, carrier)


def _shapes(root):
    with open(os.path.join(root, 'shacl.ttl'), encoding='utf-8') as handle:
        return handle.read()


def _nested(graph, parent_iri, child_iri):
    """The child's property shape, if it hangs inside the parent's."""
    for parent in graph.subjects(SH.path, URIRef(parent_iri)):
        for child in graph.objects(parent, SH.property):
            if (child, SH.path, URIRef(child_iri)) in graph:
                return child
    return None


# --- what may nest -----------------------------------------------------------

def test_the_options_say_what_is_already_inside(kms):
    options = {o['label']: o for o in sub_attribute_options(load(kms), CUTTER, FILTER_REL)}
    assert options['hasTrust']['status'] == 'here'


def test_a_declared_sub_attribute_is_offered_inside_its_carrier(kms):
    made = _declare(kms, 'hasConfidence', 'Property', 'iffBaseEntities:hasFilter')
    options = {o['iri']: o for o in sub_attribute_options(load(kms), CUTTER, FILTER_REL)}
    assert options[made['iri']]['status'] == 'free'
    # An entity attribute is never offered inside an attribute.
    assert not any(o['label'] == 'hasStrength' for o in options.values())


def test_a_new_sub_attribute_defaults_to_its_carriers_namespace(kms):
    spaces = attribute_namespaces(load(kms), 'iffBaseEntities:hasFilter')
    assert spaces[0]['default'] and spaces[0]['prefix'] == 'iffBaseEntities'


def test_the_places_an_attribute_is_constrained_include_nested_ones(kms):
    from semforge.cooked.constrain import attribute_places

    package = load(kms)
    places = attribute_places(package, 'iffBaseEntities:hasTrust')
    assert [(p['shapeName'], p['path']) for p in places] == [
        ('iffBaseShacl:CutterShape', ['iffBaseEntities:hasFilter',
                                      'iffBaseEntities:hasTrust'])]
    assert attribute_places(package, 'iffBaseEntities:hasNothing') == []


# --- the constraint, nested -----------------------------------------------------

def test_a_property_sub_attribute_nests_with_both_layers(kms):
    made = _declare(kms, 'hasConfidence', 'Property', 'iffBaseEntities:hasFilter')
    done = add_sub_attribute_constraint(load(kms), CUTTER, FILTER_REL, made['iri'],
                                        required=True, datatype='xsd:double')
    graph = load(kms).shapes
    child = _nested(graph, BASE + 'base_entities/hasFilter', made['iri'])
    assert child is not None, 'not nested inside hasFilter'
    assert (child, SH.minCount, Literal(1)) in graph
    assert (child, SH.nodeKind, SH.BlankNode) in graph
    value = graph.value(child, SH.property)
    assert (value, SH.path, URIRef(NGSILD + 'hasValue')) in graph
    assert (value, SH.datatype, XSD.double) in graph
    assert 'hasConfidence' in _shapes(kms).split('\n')[done['line'] - 1]


def test_a_relationship_sub_attribute_points_at_an_entity(kms):
    made = _declare(kms, 'hasOperator', 'Relationship', 'iffBaseEntities:hasState')
    add_sub_attribute_constraint(load(kms), MACHINE, ['iffBaseEntities:hasState'],
                                 made['iri'], value_class='iffBaseEntities:Cutter')
    graph = load(kms).shapes
    child = _nested(graph, BASE + 'base_entities/hasState', made['iri'])
    value = graph.value(child, SH.property)
    assert (value, SH.path, URIRef(NGSILD + 'hasObject')) in graph
    assert (value, SH['class'], URIRef(BASE + 'base_entities/Cutter')) in graph


def test_nesting_changes_nothing_else(kms):
    from semforge.validate import validate_package

    def verdicts(root):
        report = validate_package(load(root), strict=False)
        return {(v.resource, v.component, v.attribute) for v in report.violations}

    before_text, before = _shapes(kms), verdicts(kms)
    made = _declare(kms, 'hasConfidence', 'Property', 'iffBaseEntities:hasFilter')
    add_sub_attribute_constraint(load(kms), CUTTER, FILTER_REL, made['iri'])
    assert verdicts(kms) == before
    for line in before_text.splitlines():
        if line.lstrip().startswith('#'):
            assert line in _shapes(kms)


@pytest.mark.parametrize('attribute, parent, says', [
    ('iffBaseEntities:hasStrength', FILTER_REL, 'carried by an entity'),
    ('iffBaseEntities:hasXXXWorkpiece', FILTER_REL, 'cannot nest inside hasFilter'),
    ('iffBaseEntities:hasTrust', FILTER_REL, 'already carries hasTrust'),
])
def test_what_cannot_nest_is_refused_and_nothing_written(kms, attribute, parent, says):
    before = _shapes(kms)
    with pytest.raises(PackageError, match=says):
        add_sub_attribute_constraint(load(kms), CUTTER, parent, attribute)
    assert _shapes(kms) == before


def test_a_nested_sub_attribute_passes_the_sanity_check(kms):
    from semforge.sanity import sanity

    made = _declare(kms, 'hasConfidence', 'Property', 'iffBaseEntities:hasFilter')
    add_sub_attribute_constraint(load(kms), CUTTER, FILTER_REL, made['iri'])
    loud = [f for f in sanity(load(kms)) if f.severity in ('error', 'warning')
            or f.subject == made['iri']]
    assert loud == []


# --- the data, nested -----------------------------------------------------------

def _entity(path, identifier):
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    return next(e for e in document if e['id'] == identifier)


def test_a_sub_attribute_goes_inside_the_attribute_instance(kms):
    made = _declare(kms, 'hasConfidence', 'Property', 'iffBaseEntities:hasFilter')
    model = os.path.join(kms, 'model-instance.jsonld')
    add_attribute(load(kms), 'urn:plasmacutter:1', made['term'], value='0.9',
                  file=model, under=FILTER_REL)
    relationship = _entity(model, 'urn:plasmacutter:1')['iffBaseEntities:hasFilter']
    if isinstance(relationship, list):
        relationship = relationship[0]
    assert relationship[made['term']] == {'type': 'Property', 'value': 0.9}
    assert relationship['object'] == 'urn:filter:1', 'the parent is untouched'


@pytest.mark.parametrize('name, parent, says', [
    ('iffBaseEntities:hasStrength', FILTER_REL, 'not something'),
    ('iffBaseEntities:hasTrust', FILTER_REL, 'already has'),
    ('iffBaseEntities:hasTrust', ['iffBaseEntities:hasNothing'], 'no iffBaseEntities:hasNothing'),
])
def test_what_cannot_go_inside_is_refused(kms, name, parent, says):
    model = os.path.join(kms, 'model-instance.jsonld')
    before = open(model, encoding='utf-8').read()
    with pytest.raises(PackageError, match=says):
        add_attribute(load(kms), 'urn:plasmacutter:1', name, value='1',
                      file=model, under=parent)
    assert open(model, encoding='utf-8').read() == before


def test_with_several_datasets_the_row_s_dataset_decides(kms):
    made = _declare(kms, 'hasConfidence', 'Property', 'iffBaseEntities:hasFilter')
    model = os.path.join(kms, 'model-instance.jsonld')
    with open(model, encoding='utf-8') as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:plasmacutter:1')
    first = entity['iffBaseEntities:hasFilter']
    first = first[0] if isinstance(first, list) else first
    second = {'type': 'Relationship', 'object': 'urn:filter:2',
              'datasetId': 'urn:dataset:spare'}
    entity['iffBaseEntities:hasFilter'] = [first, second]
    with open(model, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)

    with pytest.raises(PackageError, match='datasets'):
        add_attribute(load(kms), 'urn:plasmacutter:1', made['term'], value='1',
                      file=model, under=FILTER_REL)
    add_attribute(load(kms), 'urn:plasmacutter:1', made['term'], value='1',
                  file=model, under=FILTER_REL, dataset='urn:dataset:spare')
    instances = _entity(model, 'urn:plasmacutter:1')['iffBaseEntities:hasFilter']
    spare = next(i for i in instances if i.get('datasetId') == 'urn:dataset:spare')
    assert made['term'] in spare
    assert made['term'] not in next(i for i in instances if 'datasetId' not in i)
