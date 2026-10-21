"""Adding an attribute to a shape from the Constraints view.

The write is checked three ways: as text (only the shape's own statement
changes, comments survive), as a graph (both NGSI-LD layers, the right inner
path for the kind), and as behaviour -- a required attribute added to a shape
makes data that lacks it fail, which is the only proof the constraint is live
rather than merely present.
"""

import shutil

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import SH

from semforge.cooked.constrain import add_attribute_constraint, attribute_options
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
NGSILD = 'https://uri.etsi.org/ngsi-ld/'
CARTRIDGE = BASE + 'base_shacl/CartridgeShape'
FILTER = BASE + 'base_shacl/FilterShape'
WORKPIECE = BASE + 'base_shacl/WorkpieceShape'
STATE_ON_CUTTER = BASE + 'base_shacl/StateOnCutterShape'
WASTECLASS = BASE + 'filter_entities/hasWasteclass'


@pytest.fixture
def kms(tmp_path, corpus_path):
    """A writable copy of the corpus, symlinks resolved."""
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return load(str(target))


def _shapes_text(package):
    with open(package.sources['shapes'], encoding='utf-8') as handle:
        return handle.read()


def _added_group(package, shape, attribute):
    fresh = load(package.path)
    for group in fresh.shapes.objects(URIRef(shape), SH.property):
        if (group, SH.path, URIRef(attribute)) in fresh.shapes:
            return fresh, group
    raise AssertionError(f'{attribute} not found on {shape}')


def _value_layer(graph, group):
    inner = list(graph.objects(group, SH.property))
    assert len(inner) == 1, 'expected exactly one value layer'
    return inner[0]


# --- what the picker offers ---------------------------------------------------

def test_options_say_why_an_attribute_cannot_be_added(kms):
    options = {o['label']: o for o in attribute_options(kms, FILTER)}
    assert options['hasStrength']['status'] == 'here'
    assert options['hasState']['status'] == 'inherited'
    assert options['hasState']['by'].endswith('MachineShape')


def test_options_say_which_attributes_belong_to_other_types(kms):
    """An attribute the knowledge gives another type is offered, marked: adding
    it gives it to this type too. Sub-attributes and ontology relations are
    never attributes of an entity."""
    options = {o['label']: o for o in attribute_options(kms, WORKPIECE)}
    assert options['hasStrength']['status'] == 'elsewhere'
    assert options['hasStrength']['by'] == 'Filter'
    assert 'hasTrust' not in options, 'a sub-attribute offered on an entity'
    assert 'bindsFirmware' not in options, 'an ontology relation offered'
    # Free first, then the other types' (adding one asks), then the rest.
    rank = {'free': 0, 'elsewhere': 1}
    order = [rank.get(o['status'], 2) for o in attribute_options(kms, WORKPIECE)]
    assert order == sorted(order)


def test_free_options_come_first(kms):
    statuses = [o['status'] for o in attribute_options(kms, CARTRIDGE)]
    assert statuses == sorted(statuses, key=lambda s: s != 'free')
    assert statuses[0] == 'free'


# --- what gets written --------------------------------------------------------

def test_a_property_gets_both_layers(kms):
    made = add_attribute_constraint(kms, CARTRIDGE, 'iffFilterEntities:hasWasteclass')
    assert made['kind'] == 'Property' and made['line']

    fresh, group = _added_group(kms, CARTRIDGE, WASTECLASS)
    graph = fresh.shapes
    assert (group, SH.minCount, Literal(0)) in graph, 'optional by default'
    assert (group, SH.maxCount, Literal(1)) in graph
    assert (group, SH.nodeKind, SH.BlankNode) in graph
    value = _value_layer(graph, group)
    assert (value, SH.path, URIRef(NGSILD + 'hasValue')) in graph
    assert (value, SH.minCount, Literal(1)) in graph


def test_a_vocabulary_value_is_an_iri_of_that_class(kms):
    add_attribute_constraint(kms, CARTRIDGE, WASTECLASS, required=True,
                             value_class='iffFilterKnowledge:Wasteclass')
    fresh, group = _added_group(kms, CARTRIDGE, WASTECLASS)
    value = _value_layer(fresh.shapes, group)
    assert (group, SH.minCount, Literal(1)) in fresh.shapes
    assert (value, SH.nodeKind, SH.IRI) in fresh.shapes
    assert (value, SH['class'], URIRef(BASE + 'filter_knowledge/Wasteclass')) \
        in fresh.shapes


def test_a_relationship_points_at_an_entity_type(kms):
    attribute = BASE + 'base_entities/hasFilter'
    add_attribute_constraint(kms, STATE_ON_CUTTER, attribute,
                             value_class='iffBaseEntities:Filter')
    fresh, group = _added_group(kms, STATE_ON_CUTTER, attribute)
    value = _value_layer(fresh.shapes, group)
    assert (value, SH.path, URIRef(NGSILD + 'hasObject')) in fresh.shapes
    assert (value, SH.nodeKind, SH.IRI) in fresh.shapes
    assert (value, SH['class'], URIRef(BASE + 'base_entities/Filter')) \
        in fresh.shapes


def test_only_the_shapes_own_statement_changes(kms):
    """P2: everything outside the edited statement is byte-identical,
    comments inside it included."""
    before = _shapes_text(kms)
    block = kms.index('shapes').block_for(URIRef(CARTRIDGE))[1]
    add_attribute_constraint(kms, CARTRIDGE, WASTECLASS)
    after = _shapes_text(kms)

    assert after[:block.start] == before[:block.start]
    tail = before[block.end:]
    assert after.endswith(tail)
    inside = before[block.start:block.end - 1]
    assert after[block.start:].startswith(inside.rstrip()), \
        'the shape statement was rewritten rather than extended'
    for line in before.splitlines():
        if line.lstrip().startswith('#'):
            assert line in after


def test_the_statement_still_ends_on_its_own_last_line(kms):
    add_attribute_constraint(kms, CARTRIDGE, WASTECLASS)
    lines = _shapes_text(kms).splitlines()
    assert '.' not in [line.strip() for line in lines], \
        "a lone '.' line was left below the statement"


def test_a_required_attribute_makes_data_without_it_fail(tmp_path):
    """The behavioural check: the constraint is live, not just present."""
    from semforge.cooked.knowledge import add_attribute_term
    from semforge.package.scaffold import create_package
    from semforge.validate import validate_package

    target = tmp_path / 'plant'
    target.mkdir()
    create_package(str(target), name='Plant')
    package = load(str(target))
    before = validate_package(package, strict=False)
    assert not before.violations

    made = add_attribute_term(package, 'hasSpeed', 'Property', 'plantEntities:Machine')
    package = load(str(target))
    shape = next(str(s) for s in package.shapes.subjects(SH.targetClass, None))
    add_attribute_constraint(package, shape, made['iri'], required=True,
                             datatype='xsd:double')

    package = load(str(target))
    after = validate_package(package, strict=False)
    fired = {(v.component, v.attribute) for v in after.violations}
    assert ('MinCountConstraintComponent', 'hasSpeed') in fired, fired


# --- which shape a type's new attribute goes in -------------------------------

def test_a_type_s_own_shape_is_its_structural_one(kms):
    """Filter has FilterShape and two SPARQL shapes of its own; attributes go
    in the one that already carries sh:property groups -- never in an
    inherited MachineShape."""
    from semforge.cooked.constrain import own_shape

    for spelling in ('iffBaseEntities:Filter', BASE + 'base_entities/Filter',
                     'Filter'):
        assert own_shape(kms, spelling) == FILTER, spelling


def test_a_type_with_no_shape_of_its_own_has_none(kms):
    from semforge.cooked.constrain import own_shape

    # Lasercutter is judged by CutterShape and MachineShape, both inherited.
    assert own_shape(kms, 'iffBaseEntities:Lasercutter') is None


# --- which namespace a new attribute is minted in -----------------------------

CARRIER = 'iffBaseEntities:FilterCartridge'
FILTER_ENTITIES = BASE + 'filter_entities/'


def _declare(package, name, **kwargs):
    from semforge.cooked.knowledge import add_attribute_term
    return add_attribute_term(package, name, 'Property', CARRIER, **kwargs)['iri']


def test_the_default_namespace_is_the_carriers(kms):
    assert _declare(kms, 'hasAge') == BASE + 'base_entities/hasAge'


def test_a_prefix_in_the_name_chooses_the_namespace(kms):
    """The kms's own hasWasteclass: carried by a base type, owned by the
    filter extension. Before, the prefix was dropped without a word."""
    assert _declare(kms, 'iffFilterEntities:hasLifetime') == \
        FILTER_ENTITIES + 'hasLifetime'


def test_an_explicit_namespace_wins(kms):
    assert _declare(kms, 'hasMass', namespace='iffFilterEntities') == \
        FILTER_ENTITIES + 'hasMass'
    assert _declare(load(kms.path), 'hasCharge', namespace=FILTER_ENTITIES) == \
        FILTER_ENTITIES + 'hasCharge'


@pytest.mark.parametrize('name, namespace', [
    ('nope:hasX', None), ('hasX', 'nope'), ('hasX', 'https://example.org/no-slash')])
def test_an_unknown_namespace_is_refused_not_dropped(kms, name, namespace):
    before = open(kms.sources['knowledge'], encoding='utf-8').read()
    with pytest.raises(PackageError):
        _declare(kms, name, namespace=namespace)
    assert open(kms.sources['knowledge'], encoding='utf-8').read() == before


def test_the_namespace_choices_put_the_carriers_first(kms):
    from semforge.cooked.knowledge import attribute_namespaces

    spaces = attribute_namespaces(kms, CARRIER)
    assert spaces[0]['prefix'] == 'iffBaseEntities' and spaces[0]['default']
    assert spaces[1]['prefix'] == 'iffFilterEntities', \
        'a namespace already holding attributes comes next'
    prefixes = {s['prefix'] for s in spaces}
    assert not prefixes & {'rdf', 'rdfs', 'owl', 'xsd', 'sh', 'ngsild'}
    assert not prefixes & {'iffBaseShacl', 'iffFilterShacl'}, \
        'a shapes-only namespace is no home for an attribute'


# --- what is refused, and that a refusal writes nothing -----------------------

@pytest.mark.parametrize('shape, attribute, kwargs, says', [
    (FILTER, BASE + 'base_entities/hasStrength', {}, 'already constrains'),
    (FILTER, BASE + 'base_entities/hasState', {}, 'Declare on This Type'),
    (WORKPIECE, BASE + 'base_entities/hasStrength', {}, 'gives hasStrength to'),
    (WORKPIECE, 'iffBaseEntities:hasNothingAtAll', {}, 'not declared'),
    (WORKPIECE, BASE + 'base_entities/hasTrust', {}, 'sub-attribute'),
    (STATE_ON_CUTTER, BASE + 'base_entities/hasFilter',
     {'value_class': 'base:MachineState'}, 'not an entity type'),
    (STATE_ON_CUTTER, BASE + 'base_entities/hasFilter',
     {'datatype': 'xsd:string'}, 'no datatype'),
    (CARTRIDGE, WASTECLASS, {'value_class': 'iffBaseEntities:Filter'},
     'what a Relationship is for'),
    (CARTRIDGE, WASTECLASS, {'datatype': 'xsd:string',
                             'value_class': 'iffFilterKnowledge:Wasteclass'},
     'not both'),
    (CARTRIDGE, WASTECLASS, {'datatype': 'ex:notAType'}, 'not an XML Schema'),
])
def test_a_refusal_says_why_and_writes_nothing(kms, shape, attribute, kwargs, says):
    before = _shapes_text(kms)
    with pytest.raises(PackageError, match=says):
        add_attribute_constraint(kms, shape, attribute, **kwargs)
    assert _shapes_text(kms) == before


# --- the writer underneath ----------------------------------------------------

def test_a_nested_block_renders_and_parses():
    from rdflib import Graph

    from semforge.rdfio import add_property_constraint

    source = ('@prefix ex: <https://example.org/> .\n'
              '@prefix sh: <http://www.w3.org/ns/shacl#> .\n\n'
              'ex:S a sh:NodeShape ;\n    sh:targetClass ex:C .\n')
    updated = add_property_constraint(
        None, 'https://example.org/S', 'ex:a',
        [('sh:minCount', '1'),
         ('sh:property', [('sh:path', 'ex:v'), ('sh:maxCount', '1')])],
        source=source)
    graph = Graph().parse(data=updated, format='turtle')
    outer = graph.value(URIRef('https://example.org/S'), SH.property)
    inner = graph.value(outer, SH.property)
    assert graph.value(inner, SH.path) == URIRef('https://example.org/v')
    assert updated.rstrip().endswith('] ] .')
