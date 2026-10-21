"""Residue (H4/section 7.5) and two-sided coverage (H6)."""

import pytest
from rdflib import Graph

from semforge.expect import coverage, residue_digest, run_tests
from semforge.expect.digest import canonical_lines
from semforge.expect.store import Example
from semforge.package import load
from semforge.validate import validate_package
from semforge.validate.orchestrator import validate_graphs


@pytest.fixture
def report(corpus):
    return validate_package(corpus)


def test_digest_is_stable_across_runs_and_processes(corpus_path):
    """H4: same content, same digest -- or the whole mechanism is worthless."""
    digests = {residue_digest(validate_package(load(corpus_path)).results)
               for _ in range(4)}
    assert len(digests) == 1


def test_digest_is_stable_against_input_statement_order(corpus, tmp_path):
    """Re-serialising the model must not move the digest.

    Blank node labels change between parses; if one reached the digest, every
    run would churn.
    """
    first = residue_digest(validate_package(corpus).results)

    shuffled = tmp_path / 'model.jsonld'
    corpus.model.serialize(destination=str(shuffled), format='json-ld')
    graph = Graph()
    graph.parse(str(shuffled), format='json-ld')
    second = residue_digest(
        validate_graphs(graph, corpus.shapes, corpus.knowledge).results)
    assert first == second


def test_no_blank_node_label_reaches_the_digest(report):
    for line in canonical_lines(report.results):
        assert not any(part.startswith('N') and len(part) == 33
                       for part in line.split('|'))


def test_residue_covers_everything_not_asserted(report):
    """An example asserts a few verdicts; the rest is recorded, not discarded."""
    asserted = {(report.violations[0].resource, 'x')}
    residue = [r for r in report.results if (r.resource, 'x') not in asserted]
    assert len(residue) < len(report.results)
    assert residue_digest(residue) != residue_digest(report.results)


def test_adding_a_constraint_changes_the_residue(corpus, tmp_path):
    """The property that makes a new constraint impossible to hide.

    A constraint added to the package perturbs the residue of every example in
    its target class, so it surfaces as a delta the author must accept.
    """
    before = residue_digest(validate_package(corpus).results)

    shapes = Graph()
    for triple in corpus.shapes:
        shapes.add(triple)
    shapes.parse(data='''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iffBaseEntities: <https://industryfusion.github.io/contexts/example/v0/base_entities/> .
@prefix ex: <https://example.org/> .
ex:NewShape a sh:NodeShape ; sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasStrength ; sh:minCount 1 ] .
''', format='turtle')

    after = residue_digest(
        validate_graphs(corpus.model, shapes, corpus.knowledge).results)
    assert after != before, 'a new constraint must perturb the residue'


def test_residue_change_fails_the_test_until_accepted(corpus):
    example = Example(path='model-instance.jsonld', expect='invalid',
                      residue='sha256:stale')
    outcome = run_tests([(example, validate_package(corpus))])[0]
    assert not outcome.passed
    assert outcome.residue_changed
    assert 'accept' in ' '.join(outcome.failures)


# --- H6: the historical dead-shape bug --------------------------------------

DEAD_SHAPE = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iffBaseEntities: <https://industryfusion.github.io/contexts/example/v0/base_entities/> .
@prefix ex: <https://example.org/> .
ex:DeadShape a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:sparql [ a sh:SPARQLConstraints ;
        sh:message "never fires" ;
        sh:select """
PREFIX iffBaseEntities: <https://industryfusion.github.io/contexts/example/v0/base_entities/>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
SELECT $this WHERE {
    ?pc a iffBaseEntities:Plasmacutter .
    ?pc iffBaseEntities:hasFilter [ ngsild:hasObject $this ] .
    ?pc iffBaseEntities:hasState [ ngsild:hasValue ?v ] .
    FILTER(?v = iffBaseEntities:state_PROCESSING)
}
""" ] .
'''


def _with_dead_shape(corpus):
    shapes = Graph()
    for triple in corpus.shapes:
        shapes.add(triple)
    shapes.parse(data=DEAD_SHAPE, format='turtle')
    return shapes


def test_a_dead_shape_reports_conformant_on_every_example(corpus):
    """This is the gap V1 does NOT close.

    The shape reproduces the pre-2026-08-22 StateOnFilterShape bug: it asks for
    `?pc a Plasmacutter` where the instance is typed Cutter, and compares
    against iffBaseEntities:state_PROCESSING, which does not exist (the real
    state individuals live in base_knowledge). Its WHERE clause binds nothing.

    An empty result set is byte-for-byte what a SATISFIED constraint produces,
    so per-example status calls it conformant -- forever.
    """
    report = validate_graphs(corpus.model, _with_dead_shape(corpus), corpus.knowledge)
    dead = [r for r in report.results if r.shape.endswith('DeadShape')]
    assert dead, 'the dead shape should still be enumerated'
    assert all(r.status.value == 'conformant' for r in dead)


def test_coverage_flags_the_dead_shape_as_never_firing(corpus):
    """What DOES catch it: no example ever proves it can fire.

    Coverage cannot distinguish "unsatisfiable" from "lacks a negative example"
    -- which is exactly why it reports the fact rather than inferring a verdict.
    """
    example = Example(path='model-instance.jsonld')
    report = validate_graphs(corpus.model, _with_dead_shape(corpus), corpus.knowledge)
    entries = {e.constraint: e for e in coverage([(example, report)])}
    dead = [e for name, e in entries.items() if 'DeadShape' in name]
    assert len(dead) == 1
    assert dead[0].status == 'no-firing-example'
    assert not dead[0].has_firing


def test_coverage_reports_each_side_independently():
    """A firing example proves liveness; a conforming one proves no over-firing.

    Neither substitutes for the other, so the three states are distinct. Tested
    on the entry directly rather than through the corpus, whose mix of states
    changes as the model improves -- M3's rule update semantics turned the one
    "only ever violated" constraint into a conforming one.
    """
    from semforge.expect.runner import CoverageEntry

    assert CoverageEntry('c').status == 'no-firing-example'
    assert CoverageEntry('c', conforming_examples=['a']).status == 'no-firing-example'
    assert CoverageEntry('c', firing_examples=['a']).status == 'no-conforming-example'
    assert CoverageEntry('c', firing_examples=['a'],
                         conforming_examples=['b']).status == 'two-sided'


def test_every_corpus_constraint_is_seen_on_at_least_one_side(corpus):
    example = Example(path='model-instance.jsonld')
    entries = coverage([(example, validate_package(corpus))])
    assert entries
    for entry in entries:
        assert entry.has_firing or entry.has_conforming
    assert 'no-firing-example' in {e.status for e in entries}
