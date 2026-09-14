"""The knowledge tree: the hierarchy, the vocabularies, and the joins."""

import os
import shutil

import pytest

from semforge.cooked.knowledge import build_knowledge, flatten
from semforge.package import load


@pytest.fixture(scope='module')
def tree(corpus):
    return build_knowledge(corpus)


def _find(tree, label, kind=None):
    return next(n for _, n in flatten(tree)
                if n.label == label and (kind is None or n.kind == kind))


def _all(tree, kind):
    return [n for _, n in flatten(tree) if n.kind == kind]


# --- the hierarchy ------------------------------------------------------------

def test_the_groups_are_the_three_things_the_knowledge_declares(tree):
    """Types, vocabularies, and the attributes -- which nothing showed."""
    assert [n.label for n in tree] == [
        'Entity types', 'Vocabulary classes', 'Attributes']


def test_entity_types_nest_by_subclass(tree):
    machine = _find(tree, 'iffBaseEntities:Machine', 'class')
    below = {n.label for n in machine.children if n.kind == 'class'}
    assert below == {'iffBaseEntities:Cutter', 'iffBaseEntities:Filter'}

    cutter = _find(tree, 'iffBaseEntities:Cutter', 'class')
    assert {n.label for n in cutter.children if n.kind == 'class'} == \
        {'iffBaseEntities:Lasercutter', 'iffBaseEntities:Plasmacutter'}


def test_a_vocabulary_class_lists_its_members(tree):
    states = _find(tree, 'base:MachineState', 'class')
    members = [n.label for n in states.children if n.kind == 'individual']
    assert 'state_ON' in members and 'state_OFF' in members
    assert '7 member(s)' in states.detail


def test_an_entity_type_is_not_listed_among_the_vocabularies(tree):
    vocabulary = tree[1]
    labels = {n.label for _, n in flatten(vocabulary.children)}
    assert 'iffBaseEntities:Filter' not in labels


# --- the join to the shapes ---------------------------------------------------

def test_a_class_carries_the_shape_that_judges_it(tree):
    node = _find(tree, 'iffBaseEntities:Filter', 'class')
    assert 'iffBaseShacl:FilterShape' in node.detail
    assert node.shape_at and os.path.basename(
        node.shape_at.rsplit(':', 1)[0]) == 'shacl.ttl'


def test_a_subclass_with_no_shape_of_its_own_is_not_called_unchecked(tree):
    """sh:targetClass traverses rdfs:subClassOf*.

    CutterShape judges a Plasmacutter, so flagging it as unchecked would be a
    false alarm -- and the least obvious rule in SHACL is exactly the one an
    author should not have to remember here.
    """
    node = _find(tree, 'iffBaseEntities:Plasmacutter', 'class')
    assert node.severity == ''
    assert 'inherited shape' in node.detail


def test_an_abstract_root_is_not_flagged(tree):
    """Entity and Consumable have subclasses and no instances: nothing is
    missing."""
    for label in ('iffBaseEntities:Entity', 'iffBaseEntities:Consumable'):
        assert _find(tree, label, 'class').severity == ''


def test_a_truly_unchecked_type_is_flagged(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', target / extra)
    with open(target / 'knowledge.ttl', 'a', encoding='utf-8') as handle:
        handle.write('\niffBaseEntities:Conveyor a owl:Class ;\n'
                     '    rdfs:subClassOf iffBaseEntities:Entity .\n')

    node = _find(build_knowledge(load(str(target))),
                 'iffBaseEntities:Conveyor', 'class')
    assert node.severity == 'warning'
    assert 'no shape' in node.detail


# --- the join to the examples -------------------------------------------------

def test_every_row_naming_an_entity_shows_its_path(tree):
    """An id is not an address.

    urn:filter:1 names a different entity in four files, which is how a variant
    is written -- so the row has to say which file, and a basename will not do:
    two of the example files are both called filter-on.jsonld.
    """
    rows = [n for _, n in flatten(tree) if n.kind in ('instance', 'usage')]
    assert rows
    filters = [n for n in rows if n.label == 'urn:filter:1']
    assert len(filters) > 1, 'the id should appear once per file'
    for node in filters:
        assert '/' in node.detail or node.detail.endswith('.jsonld'), node.detail
        assert not os.path.isabs(node.detail.split(' · ')[-1])
    # Distinct paths, so the rows are tellable apart.
    instances = [n.detail for n in filters if n.kind == 'instance']
    assert len(set(instances)) == len(instances)
    assert any('examples/subobjects/' in d for d in instances)


def test_instances_are_counted_across_every_example_file(tree):
    """Counting only model-instance.jsonld would call types uninstantiated
    that the suites instantiate several times over."""
    node = _find(tree, 'iffBaseEntities:Filter', 'class')
    assert 'instance(s)' in node.detail
    instances = [n for n in node.children if n.kind == 'instance']
    assert len(instances) > 1
    assert all(n.defined_at for n in instances)
    assert {os.path.basename(n.file) for n in instances} != \
        {'model-instance.jsonld'}, 'the example suites were not read'


def test_a_term_an_example_uses_is_marked_used_and_says_where(tree):
    used = _find(tree, 'state_ON', 'individual')
    assert 'used in' in used.detail
    assert used.severity == ''
    assert [n.kind for n in used.children] == ['usage'] * len(used.children)
    assert any(n.entity.startswith('urn:') for n in used.children)


def test_a_term_used_only_by_a_bad_example_still_counts_as_used(tree):
    """state_OFF appears in a case under bad/, not in the shipped model.

    Calling it unused would send somebody deleting a term the suite depends on.
    """
    node = _find(tree, 'state_OFF', 'individual')
    assert 'used in' in node.detail and node.severity == ''


def test_an_unexercised_value_of_a_constrained_vocabulary_is_flagged(tree):
    node = _find(tree, 'state_CLEANING', 'individual')
    assert node.severity == 'warning'
    assert 'no case exercises it' in node.messages[0]


def test_terms_of_a_vocabulary_no_shape_draws_from_are_not_flagged(tree):
    """A Binding is not something an NGSI-LD example mentions.

    Flagging those would colour most of the tree and bury the real gap.
    """
    for label in ('carbon', 'heightBinding', '_map1'):
        node = _find(tree, label, 'individual')
        assert node.severity == '', f'{label} should not be flagged'


def test_an_entity_range_is_not_reported_as_having_no_members(tree):
    """sh:class on a relationship means the value is an ENTITY.

    Its instances live in the data, so "no individuals in knowledge.ttl" says
    nothing about whether the constraint can be satisfied.
    """
    for label in ('iffBaseEntities:FilterCartridge', 'iffBaseEntities:Workpiece'):
        node = _find(tree, label, 'class')
        assert 'no members' not in node.detail
        assert node.severity == ''


# --- the locations every row needs --------------------------------------------

def test_every_class_and_member_can_be_opened(tree, corpus):
    rows = _all(tree, 'class') + _all(tree, 'individual')
    # Every one of them, including the base:-prefixed vocabulary whose
    # statements the index used to discard as @base directives.
    assert [n.label for n in rows if not n.defined_at] == []
    for node in rows:
        if node.defined_at:
            path, line = node.defined_at.rsplit(':', 1)
            assert path == corpus.sources['knowledge']
            text = open(path, encoding='utf-8').read().splitlines()
            assert node.label.split(':')[-1] in text[int(line) - 1]


# --- a usage row has to be openable ------------------------------------------

def test_a_usage_row_carries_the_file_and_line_of_the_using_attribute(tree):
    used = _find(tree, 'state_ON', 'individual')
    rows = [n for n in used.children if n.kind == 'usage']
    assert rows
    for row in rows:
        assert row.entity.startswith('urn:')
        assert row.defined_at, f'{row.label} cannot be opened'
        path, line = row.defined_at.rsplit(':', 1)
        assert path.endswith('.jsonld') and int(line) > 0
        text = open(path, encoding='utf-8').read().splitlines()
        # The line is the attribute that gives the term, not the file's top.
        assert row.detail.split(' · ')[0] in text[int(line) - 1]


def test_the_same_term_in_two_files_gets_a_row_for_each(tree):
    """The same entity id legitimately appears in a good case and a bad one.

    One location for both would open the wrong file half the time.
    """
    used = _find(tree, 'state_ON', 'individual')
    files = [n.defined_at.rsplit(':', 1)[0] for n in used.children]
    assert len(set(files)) > 1, files
    assert len(files) == len(set(zip(
        [n.entity for n in used.children],
        [n.detail for n in used.children])))


def test_the_count_and_the_rows_agree(tree):
    for label in ('state_ON', 'WC1', 'EN_1.4301'):
        node = _find(tree, label, 'individual')
        rows = [n for n in node.children if n.kind == 'usage']
        assert f'used in {len(rows)} place(s)' in node.detail, \
            f'{label}: {node.detail} but {len(rows)} rows'


# --- the attribute hierarchy -------------------------------------------------

def _attributes(package):
    from semforge.cooked.knowledge import build_knowledge

    return next((root for root in build_knowledge(package)
                 if root.label == 'Attributes'), None)


def _rows(node):
    from semforge.cooked.knowledge import flatten

    return {row.label: row for _, row in flatten([node])}


def test_the_attributes_are_shown_under_what_carries_them(corpus):
    """The third thing knowledge.ttl declares, and the one nothing showed."""
    group = _attributes(corpus)
    assert group is not None
    carriers = {row.label for row in group.children}
    assert 'iffBaseEntities:Machine' in carriers
    assert 'iffBaseEntities:Workpiece' in carriers

    machine = next(row for row in group.children
                   if row.label == 'iffBaseEntities:Machine')
    assert 'iffBaseEntities:hasState' in {row.label for row in machine.children}


def test_a_sub_attribute_is_shown_under_its_parent_not_at_the_top(corpus):
    group = _attributes(corpus)
    state = _rows(group)['iffBaseEntities:hasState']
    assert [row.label for row in state.children] == \
        ['iffBaseEntities:hasXXXWorkpiece']
    # And it is not repeated as something an entity type carries.
    for carrier in group.children:
        assert 'iffBaseEntities:hasXXXWorkpiece' not in \
            {row.label for row in carrier.children}


def test_each_attribute_reaches_the_shape_that_constrains_it(corpus):
    """The join the view exists for: a row that cannot reach its property
    shape leaves you to find it by hand."""
    rows = _rows(_attributes(corpus))
    state = rows['iffBaseEntities:hasState']
    assert state.shape_name == 'iffBaseShacl:MachineShape'
    assert state.shape_at and ':' in state.shape_at


def test_an_attribute_constrained_inside_sh_or_is_still_found(corpus):
    """`_read_token` closed a `(` at the FIRST `)`, so a collection nested in
    an sh:or ended the token early and the group's sh:path became whatever
    came last -- pointing every such attribute at the wrong shape."""
    rows = _rows(_attributes(corpus))
    assert rows['iffBaseEntities:hasList'].shape_name == \
        'iffBaseShacl:CutterShape'


def test_the_ontology_own_relations_are_judged_apart(corpus):
    """knowledge.ttl also declares relations that are never document keys.

    Reporting `material:contains` as unused and unchecked is true of a document
    and meaningless of an ontology.
    """
    group = _attributes(corpus)
    relations = next(row for row in group.children
                     if row.label == 'Ontology relations')
    labels = {row.label for row in relations.children}
    assert 'material:contains' in labels
    assert 'iffBaseEntities:hasState' not in labels

    contains = next(row for row in relations.children
                    if row.label == 'material:contains')
    assert not contains.severity            # used within the ontology
    assert 'statement(s)' in contains.detail


def test_an_attribute_nothing_carries_is_flagged(corpus):
    """`hasOutWorkpiece` is declared and constrained and used by nothing --
    while `hasOutWorkpiecexx`, two letters away, is what the data carries."""
    rows = _rows(_attributes(corpus))
    unused = rows['iffBaseEntities:hasOutWorkpiece']
    assert unused.severity == 'warning'
    assert 'used by nothing' in unused.detail
    assert any('no constraint about it can fire' in message
               for message in unused.messages)


def test_a_well_formed_attribute_is_not_flagged(corpus):
    rows = _rows(_attributes(corpus))
    assert not rows['iffBaseEntities:hasStrength'].severity
    assert not rows['iffBaseEntities:hasState'].severity
