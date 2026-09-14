"""An attribute must be declared before it is used.

The same rule as an entity's type, one level down and for the same reason. A
type decides which shapes judge an entity; an attribute's NAME decides which
`sh:path` matches it. So a name the knowledge has never heard of does not
produce an error -- it produces silence: no property shape selects it, the
constraint that should have judged the value never fires, and the document
reads as validated.
"""

import os
import shutil

import pytest

from semforge.cooked.choices import attribute_terms, attributes_for
from semforge.cooked.examples import add_attribute
from semforge.cooked.knowledge import add_attribute_term
from semforge.errors import PackageError
from semforge.expect.vocabulary import undeclared_attributes
from semforge.package import load


@pytest.fixture
def package(tmp_path, corpus_path):
    copy = tmp_path / 'pkg'
    shutil.copytree(corpus_path, copy)
    return load(str(copy))


# --- what the knowledge declares ---------------------------------------------

def test_an_attribute_carries_its_kind_and_its_carrier(package):
    by_term = {entry.term: entry for entry in attribute_terms(package)}
    state = by_term['iffBaseEntities:hasState']
    assert state.kind == 'Property'
    assert state.domain == 'iffBaseEntities:Machine'
    assert state.constrained
    assert state.defined_at.endswith(('knowledge.ttl:62', 'knowledge.ttl:63'))

    relation = by_term['iffBaseEntities:hasFilter']
    assert relation.kind == 'Relationship'


def test_every_ngsi_ld_kind_is_recognised(package):
    """Property and Relationship are not the only two: the kms uses four."""
    kinds = {entry.kind for entry in attribute_terms(package)}
    assert {'Property', 'Relationship', 'JsonProperty', 'ListProperty'} <= kinds


def test_the_domain_is_inherited_down_the_hierarchy(package):
    """A Plasmacutter carries what a Cutter carries and what a Machine does."""
    mine, _ = attributes_for(package, 'iffBaseEntities:Plasmacutter')
    terms = {entry.term for entry in mine}
    assert 'iffBaseEntities:hasFilter' in terms       # declared on Cutter
    assert 'iffBaseEntities:hasState' in terms        # declared on Machine
    assert 'iffBaseEntities:hasHeight' not in terms   # a Workpiece's


def test_an_attribute_with_no_domain_is_offered_separately(package):
    """A package may simply not have said which type carries it.

    Hiding it would be wrong; mixing it in with the ones that name this type
    would claim a carrier nobody declared. (A SUB-attribute is a different
    case and is not offered here at all -- see below.)
    """
    mine, open_ended = attributes_for(package, 'iffBaseEntities:Filter')
    assert open_ended, 'the corpus has attributes with no rdfs:domain'
    assert not [entry for entry in open_ended if entry.domain]
    assert all(entry.domain for entry in mine)


# --- what the documents use --------------------------------------------------

def test_the_corpus_typo_is_reported(package):
    """`hasOutWorkpiecexx` is two letters from a real attribute.

    It has been in the shipped model instance all along: no shape constrains
    it, no knowledge file declares it, and nothing ever said so.
    """
    found = {entry.term: entry for entry in undeclared_attributes(package)}
    assert 'iffBaseEntities:hasOutWorkpiecexx' in found
    typo = found['iffBaseEntities:hasOutWorkpiecexx']
    assert not typo.constrained
    assert all(place.endswith('model-instance.jsonld')
               for place, _ in typo.places)
    assert all(line > 1 for _, line in typo.places)


def test_the_scratchpad_is_reported_but_does_not_fail(package):
    """The same rule the Model view draws: Main cannot fail, Tests can."""
    found = {entry.term: entry for entry in undeclared_attributes(package)}
    assert found['iffBaseEntities:hasOutWorkpiecexx'].severity == 'info'


def test_a_case_using_an_undeclared_attribute_is_an_error(package, tmp_path):
    case = os.path.join(package.path, 'examples', 'test_FilterShape', 'bad',
                        'without-cartridge.jsonld')
    text = open(case, encoding='utf-8').read()
    open(case, 'w', encoding='utf-8').write(
        text.replace('"iffBaseEntities:hasState"',
                     '"iffBaseEntities:hasStatex"', 1))

    found = {entry.term: entry for entry in undeclared_attributes(load(package.path))}
    assert 'iffBaseEntities:hasStatex' in found
    assert found['iffBaseEntities:hasStatex'].severity == 'error'


def test_the_encoding_keys_are_not_attributes(package):
    """`value`, `object`, `observedAt` are the encoding, not the vocabulary."""
    terms = {entry.term for entry in undeclared_attributes(package)}
    for reserved in ('value', 'object', 'type', 'id', 'observedAt', 'datasetId'):
        assert reserved not in terms


# --- writing -----------------------------------------------------------------

def test_an_undeclared_attribute_cannot_be_written(package):
    with pytest.raises(PackageError) as raised:
        add_attribute(package, 'urn:filter:1', 'iffBaseEntities:hasPressure',
                      value='1.0')
    assert 'not an attribute this package declares' in str(raised.value)


def test_declaring_it_first_makes_it_usable(package):
    add_attribute_term(package, 'hasPressure', 'Property',
                       'iffBaseEntities:Filter', label='bar, at the inlet')
    again = load(package.path)
    source, kind = add_attribute(again, 'urn:filter:1',
                                 'iffBaseEntities:hasPressure', value='1.0')
    assert kind == 'Property'
    assert 'hasPressure' in open(source, encoding='utf-8').read()


def test_a_new_attribute_records_its_carrier_and_its_kind(package):
    made = add_attribute_term(package, 'hasPressure', 'Relationship',
                              'iffBaseEntities:Filter')
    text = open(made['file'], encoding='utf-8').read()
    assert 'rdfs:domain iffBaseEntities:Filter' in text
    assert 'ngsi-ld/Relationship' in text
    entry = next(e for e in attribute_terms(load(package.path))
                 if e.label == 'hasPressure')
    assert entry.kind == 'Relationship'


def test_a_sub_attribute_is_declared_without_a_carrier(package):
    made = add_attribute_term(package, 'hasConfidence', 'Property', '')
    assert made['domain'] == ''
    text = open(made['file'], encoding='utf-8').read()
    assert 'hasConfidence a owl:DatatypeProperty ;\n    rdfs:range' in text


def test_a_carrier_that_carries_nothing_is_refused(package):
    """A vocabulary class is neither an entity type nor an attribute."""
    with pytest.raises(PackageError) as raised:
        add_attribute_term(package, 'hasThing', 'Property',
                           'iffBaseKnowledge:MachineState')
    assert 'neither an entity type nor an attribute' in str(raised.value)


def test_a_kind_that_is_not_ngsi_ld_is_refused(package):
    with pytest.raises(PackageError) as raised:
        add_attribute_term(package, 'hasThing', 'Thing',
                           'iffBaseEntities:Filter')
    assert 'not an NGSI-LD attribute kind' in str(raised.value)


def test_a_duplicate_attribute_is_refused(package):
    with pytest.raises(PackageError) as raised:
        add_attribute_term(package, 'hasState', 'Property',
                           'iffBaseEntities:Machine')
    assert 'already declared' in str(raised.value)


# --- nested attributes -------------------------------------------------------

def test_a_sub_attribute_gets_its_parent_from_the_shapes(package):
    """Which SPECIFIC attribute it nests inside is only the shapes' to say.

    `rdfs:domain` says which KIND of node carries it (see below), which is a
    real statement but a weaker one: it permits every Relationship, not this
    one attribute. Naming the attribute in a domain would be punning --
    `rdfs:domain hasFilter` makes hasFilter a class as well as a property.
    """
    from semforge.cooked.choices import nesting

    inside = nesting(package)
    trust = 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasTrust'
    assert inside[trust] == [
        'https://industryfusion.github.io/contexts/example/v0/base_entities/hasFilter']


def test_the_value_layer_is_not_a_sub_attribute(package):
    """The encoding is two-layer: the inner sh:property on ngsild:hasValue is
    the VALUE, not an attribute of the attribute."""
    from semforge.cooked.choices import nesting

    assert not [child for child in nesting(package)
                if 'ngsi-ld/has' in child]


def test_a_sub_attribute_is_not_offered_as_an_entity_attribute(package):
    """Offering `hasTrust` on a Filter would put it where no shape looks."""
    mine, open_ended = attributes_for(package, 'iffBaseEntities:Filter')
    offered = {entry.term for entry in mine} | {entry.term for entry in open_ended}
    assert 'iffBaseEntities:hasTrust' not in offered
    assert 'iffBaseEntities:hasXXXWorkpiece' not in offered


def test_the_sub_attributes_of_an_attribute_can_be_asked_for(package):
    """Which is the question a nested picker asks.

    Two answers, in order: what a shape has PLACED inside this attribute, then
    what the knowledge ALLOWS inside anything of its kind.
    """
    from semforge.cooked.choices import sub_attributes_for

    found = sub_attributes_for(package, 'iffBaseEntities:hasFilter')
    assert found[0].term == 'iffBaseEntities:hasTrust'
    assert found[0].kind == 'Property'
    assert found[0].parents == ('iffBaseEntities:hasFilter',)
    # hasFilter is a Relationship, so only things declared to hang off one.
    assert all(entry.carrier_kind in ('Relationship', '') for entry in found)

    on_state = sub_attributes_for(package, 'iffBaseEntities:hasState')
    assert 'iffBaseEntities:hasXXXWorkpiece' in {e.term for e in on_state}
    # A Property's sub-attributes are not offered on a Relationship.
    assert 'iffBaseEntities:hasXXXWorkpiece' not in {e.term for e in found}


def test_an_attribute_nobody_nests_has_no_parents(package):
    by_term = {entry.term: entry for entry in attribute_terms(package)}
    assert by_term['iffBaseEntities:hasState'].parents == ()


def test_the_domain_of_a_sub_attribute_is_the_attribute_node_class(package):
    """The encoding types the attribute node, so domain IS an ordinary class.

    `hasFilter` expands to a node `a ngsild:Relationship` carrying
    `ngsild:hasObject`; `hasTrust` hangs off that node. So
    `rdfs:domain ngsild:Relationship` is literally true -- nothing invented and
    no punning. The shipped kms already does this for `base:boundBy`.
    """
    by_term = {entry.term: entry for entry in attribute_terms(package)}
    assert by_term['iffBaseEntities:hasTrust'].carrier_kind == 'Relationship'
    assert by_term['iffBaseEntities:hasXXXWorkpiece'].carrier_kind == 'Property'
    assert by_term['iffBaseEntities:hasState'].carrier_kind == ''


def test_the_declaration_alone_is_enough_to_know_it_nests(package):
    """A sub-attribute declared but not yet placed in a shape is still one.

    Reading it only from the shapes made an unplaced sub-attribute
    indistinguishable from an attribute nobody had given a domain.
    """
    from semforge.cooked.knowledge import add_attribute_term

    add_attribute_term(package, 'hasConfidence', 'Property',
                       'iffBaseEntities:hasFilter')
    again = load(package.path)
    entry = next(e for e in attribute_terms(again) if e.label == 'hasConfidence')
    assert entry.carrier_kind == 'Relationship'
    assert entry.parents == ()          # no shape places it yet

    mine, open_ended = attributes_for(again, 'iffBaseEntities:Filter')
    offered = {e.term for e in mine} | {e.term for e in open_ended}
    assert 'iffBaseEntities:hasConfidence' not in offered


def test_a_carrier_attribute_writes_the_node_class_as_the_domain(package):
    from semforge.cooked.knowledge import add_attribute_term

    made = add_attribute_term(package, 'hasConfidence', 'Property',
                              'iffBaseEntities:hasFilter')
    assert made['domain'] == 'iffBaseEntities:hasFilter'
    text = open(made['file'], encoding='utf-8').read()
    assert 'rdfs:domain <https://uri.etsi.org/ngsi-ld/Relationship>' in text


def test_a_carrier_that_is_neither_a_type_nor_an_attribute_is_refused(package):
    from semforge.cooked.knowledge import add_attribute_term

    with pytest.raises(PackageError) as raised:
        add_attribute_term(package, 'hasThing', 'Property', 'iffBaseEntities:Nope')
    assert 'neither an entity type nor an attribute' in str(raised.value)


def test_placed_sub_attributes_come_before_merely_allowed_ones(package):
    """A shape that nests it names one parent; a domain permits a whole kind."""
    from semforge.cooked.choices import sub_attributes_for

    found = sub_attributes_for(package, 'iffBaseEntities:hasState')
    assert found[0].term == 'iffBaseEntities:hasXXXWorkpiece'
    assert found[0].parents == ('iffBaseEntities:hasState',)
    assert any(entry.parents == () and entry.carrier_kind == 'Property'
               for entry in found[1:]), [e.term for e in found]
