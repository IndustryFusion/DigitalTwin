"""Deleting an attribute, and everything that would dangle without it.

Each removal is checked as text (what changed is exactly the dependents, the
rest is byte-identical), as a graph (the term is gone from every artifact), and
as behaviour (the package still validates to the same verdicts). The refusals
are checked to write nothing at all.
"""

import json
import os
import shutil

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from semforge.cooked.remove_attribute import (plan_attribute_removal,
                                              remove_attribute, remove_declaration)
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
WIDTH = BASE + 'base_entities/hasWidth'
TRUST = BASE + 'base_entities/hasTrust'
FILTER_REL = BASE + 'base_entities/hasFilter'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return load(str(target))


def _snapshot(package):
    """{relative path: text} of every file in the package."""
    out = {}
    for directory, _, names in os.walk(package.path):
        for name in names:
            path = os.path.join(directory, name)
            with open(path, encoding='utf-8') as handle:
                out[os.path.relpath(path, package.path)] = handle.read()
    return out


def _mentions(package, iri):
    """Files whose graph or JSON still mention the IRI anywhere."""
    found = []
    fresh = load(package.path)
    for role, graph in (('knowledge', fresh.knowledge), ('shapes', fresh.shapes)):
        if any(URIRef(iri) in triple for triple in graph):
            found.append(role)
    from semforge.editor.references import references_to
    found += [r.path for r in references_to(fresh, {iri})]
    return found


# --- the plan -----------------------------------------------------------------

def test_a_plan_lists_every_kind_of_dependent(kms):
    plan = plan_attribute_removal(kms, 'iffBaseEntities:hasWidth')
    kinds = {d.kind for d in plan.dependents}
    assert {'declaration', 'constraint', 'data'} <= kinds
    assert plan.in_use and not plan.blocking
    data = [d for d in plan.dependents if d.kind == 'data']
    for dependent in data:
        with open(dependent.file, encoding='utf-8') as handle:
            line = handle.read().split('\n')[dependent.line - 1]
        assert 'hasWidth' in line, 'a data dependent must point at the key'


def test_a_sparql_use_blocks_and_says_where(kms):
    plan = plan_attribute_removal(kms, 'iffBaseEntities:hasStrength')
    blocking = plan.blocking
    assert blocking and all(d.kind == 'sparql' for d in blocking)
    assert 'FilterStrengthShape' in blocking[0].detail


def test_a_use_outside_a_property_shape_blocks_too(kms):
    """CartridgeShape names hasCartridge inside a two-hop inverse path: not a
    property group of its own, so not something to cut out mechanically."""
    plan = plan_attribute_removal(kms, 'iffBaseEntities:hasCartridge')
    assert any(d.kind == 'shapes' and 'CartridgeShape' in d.detail
               for d in plan.blocking)
    assert any(d.kind == 'expectation' for d in plan.dependents)


def test_a_nested_attribute_is_found_inside_its_parent(kms):
    plan = plan_attribute_removal(kms, TRUST)
    constraint = [d for d in plan.dependents if d.kind == 'constraint']
    assert len(constraint) == 1 and 'inside iffBaseEntities:hasFilter' in \
        constraint[0].detail


# --- the removal --------------------------------------------------------------

def test_removing_takes_every_dependent_and_nothing_else(kms):
    before = _snapshot(kms)
    remove_attribute(kms, WIDTH, force=True)
    after = _snapshot(kms)

    assert _mentions(kms, WIDTH) == []
    changed = {path for path in before if before[path] != after[path]}
    plan_files = {'shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld',
                  'examples/subobjects/workpiece-steel.jsonld',
                  'examples/test_WorkpieceShape/bad/too-high.jsonld',
                  'examples/test_WorkpieceShape/good/at-the-limits.jsonld'}
    assert changed == plan_files

    # The neighbour in the same `sh:property [A], [B]` list survives intact.
    graph = Graph().parse(data=after['shacl.ttl'], format='turtle')
    paths = {str(p) for p in graph.objects(None, SH.path)}
    assert BASE + 'base_entities/hasHeight' in paths
    assert BASE + 'base_entities/hasLength' in paths
    # Every comment line of the shapes file survives.
    for line in before['shacl.ttl'].splitlines():
        if line.lstrip().startswith('#'):
            assert line in after['shacl.ttl']


def test_the_package_still_validates_to_the_same_verdicts(kms):
    from semforge.validate import validate_package

    def verdicts(package):
        report = validate_package(package, strict=False)
        return {(v.resource, v.component, v.attribute) for v in report.violations}

    before = verdicts(kms)
    remove_attribute(kms, WIDTH, force=True)
    assert verdicts(load(kms.path)) == before


def test_a_nested_attribute_leaves_its_parent_whole(kms):
    remove_attribute(kms, TRUST, force=True)
    fresh = load(kms.path)
    assert _mentions(kms, TRUST) == []
    # hasFilter is still constrained, and its value layer still says Filter.
    groups = [g for g in fresh.shapes.subjects(SH.path, URIRef(FILTER_REL))]
    assert groups
    values = [v for g in groups for v in fresh.shapes.objects(g, SH.property)]
    assert any((v, SH['class'], URIRef(BASE + 'base_entities/Filter')) in fresh.shapes
               for v in values)


def test_a_declared_then_deleted_attribute_leaves_no_trace(kms):
    """The round trip: declare, delete, and the knowledge is byte-identical."""
    from semforge.cooked.knowledge import add_attribute_term

    with open(kms.sources['knowledge'], encoding='utf-8') as handle:
        original = handle.read()
    made = add_attribute_term(kms, 'hasNothingYet', 'Property',
                              'iffBaseEntities:Workpiece')
    package = load(kms.path)
    plan = plan_attribute_removal(package, made['iri'])
    assert not plan.in_use, 'declared and used nowhere'
    remove_attribute(package, made['iri'])              # no force needed
    with open(kms.sources['knowledge'], encoding='utf-8') as handle:
        assert handle.read() == original


def test_expectation_asserts_go_and_an_emptied_bad_case_is_flagged(kms):
    source = os.path.join(kms.path, 'examples', 'test_WorkpieceShape', 'bad',
                          'expectations.yaml')
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    text = text.replace('WorkpieceShape/hasHeight/MaxInclusiveConstraintComponent',
                        'WorkpieceShape/hasWidth/MaxInclusiveConstraintComponent')
    text = '# kept: a comment the round trip must not drop\n' + text
    with open(source, 'w', encoding='utf-8') as handle:
        handle.write(text)

    plan = plan_attribute_removal(load(kms.path), WIDTH)
    assert any(d.kind == 'expectation' for d in plan.dependents)
    _, notes = remove_attribute(load(kms.path), WIDTH, force=True)

    with open(source, encoding='utf-8') as handle:
        after = handle.read()
    assert 'hasWidth' not in after
    assert '# kept: a comment the round trip must not drop' in after
    assert any('too-high.jsonld' in n and 'no longer asserts' in n for n in notes)


# --- refusals write nothing ---------------------------------------------------

def test_a_blocked_removal_writes_nothing(kms):
    before = _snapshot(kms)
    with pytest.raises(PackageError, match='SPARQL'):
        remove_attribute(kms, 'iffBaseEntities:hasStrength', force=True)
    assert _snapshot(kms) == before


def test_an_attribute_in_use_needs_the_authors_yes(kms):
    before = _snapshot(kms)
    with pytest.raises(PackageError, match='in use'):
        remove_attribute(kms, WIDTH)
    assert _snapshot(kms) == before


def test_an_unresolvable_term_is_refused(kms):
    with pytest.raises(PackageError):
        plan_attribute_removal(kms, 'nope:hasNothing')


def test_data_keeps_its_layout(kms):
    path = os.path.join(kms.path, 'examples', 'subobjects', 'workpiece-steel.jsonld')
    with open(path, encoding='utf-8') as handle:
        before = handle.read()
    remove_attribute(kms, WIDTH, force=True)
    with open(path, encoding='utf-8') as handle:
        after = handle.read()
    json.loads(after)
    removed = [line for line in before.splitlines() if line not in after.splitlines()]
    assert any('hasWidth' in line for line in removed)
    assert len(removed) <= 4, f'more than the key was rewritten: {removed}'


# --- the declaration alone ----------------------------------------------------

def test_the_declaration_alone_goes_and_every_use_stays(kms):
    before = _snapshot(kms)
    _, notes = remove_declaration(kms, WIDTH, force=True)
    after = _snapshot(kms)
    changed = {path for path in before if before[path] != after[path]}
    assert changed == {'knowledge.ttl'}
    fresh = load(kms.path)
    assert (URIRef(WIDTH), None, None) not in fresh.knowledge
    assert (None, SH.path, URIRef(WIDTH)) in fresh.shapes, 'the shape stays'
    assert notes and 'undeclared' in notes[0]


def test_what_is_left_is_reported_not_silent(kms):
    """The leftovers surface as vocabulary errors in the editor."""
    from semforge.editor import analyse

    remove_declaration(kms, WIDTH, force=True)
    findings, _ = analyse(kms.path)
    flagged = [f for items in findings.values() for f in items
               if f.kind == 'vocabulary' and 'hasWidth' in f.message]
    assert flagged, 'a use of an undeclared attribute went unreported'


def test_the_declaration_goes_even_where_sparql_blocks_the_full_delete(kms):
    shapes_before = _snapshot(kms)['shacl.ttl']
    remove_declaration(kms, 'iffBaseEntities:hasStrength', force=True)
    assert _snapshot(kms)['shacl.ttl'] == shapes_before
    assert (URIRef(BASE + 'base_entities/hasStrength'), None, None) \
        not in load(kms.path).knowledge


def test_declaration_only_still_needs_the_authors_yes_when_in_use(kms):
    before = _snapshot(kms)
    with pytest.raises(PackageError, match='in use'):
        remove_declaration(kms, WIDTH)
    assert _snapshot(kms) == before


def test_an_undeclared_term_has_no_declaration_to_remove(kms):
    remove_declaration(kms, WIDTH, force=True)
    with pytest.raises(PackageError, match='not declared'):
        remove_declaration(load(kms.path), WIDTH, force=True)
