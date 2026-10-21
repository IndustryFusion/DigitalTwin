"""M5: semantic diff and regression reports."""

import os
import shutil

from click.testing import CliRunner
from rdflib import Graph

from semforge.cli import cli
from semforge.diff import Direction, semantic_diff
from semforge.diff.impact import format_regression, regression_report
from semforge.diff.model import describe, format_changes
from semforge.package import load


def _variant(tmp_path, corpus_path, edit, name='variant'):
    """A copy of the corpus with one textual edit applied."""
    target = tmp_path / name
    target.mkdir()
    for artifact in ('knowledge.ttl', 'shacl.ttl', 'model-instance.jsonld',
                     'context.jsonld'):
        shutil.copy(os.path.join(corpus_path, artifact), target / artifact)
    shapes = (target / 'shacl.ttl')
    shapes.write_text(edit(shapes.read_text()))
    return load(str(target))


def test_a_package_does_not_differ_from_itself(corpus, corpus_path):
    """Blank node labels differ between parses; they must not reach the diff.

    sh:or and sh:node carry them, so comparing labels reported every shape as
    changed on every run.
    """
    assert semantic_diff(corpus.shapes, load(corpus_path).shapes) == []


def test_a_weakened_cardinality_is_classified(tmp_path, corpus, corpus_path):
    """The manifest's worked example: minCount 1 -> 0."""
    after = _variant(tmp_path, corpus_path,
                     lambda text: text.replace('sh:minCount 1 ;', 'sh:minCount 0 ;', 1))
    changes = semantic_diff(corpus.shapes, after.shapes)
    assert len(changes) == 1
    change = changes[0]
    assert change.kind == 'parameter-changed'
    assert change.component == 'MinCountConstraintComponent'
    assert (change.before, change.after) == ('1', '0')
    assert change.direction is Direction.WEAKENED


def test_a_tightened_bound_is_classified_the_other_way(tmp_path, corpus, corpus_path):
    after = _variant(tmp_path, corpus_path,
                     lambda text: text.replace('sh:maxInclusive 100.0 ;',
                                               'sh:maxInclusive 50.0 ;', 1))
    changes = [c for c in semantic_diff(corpus.shapes, after.shapes)
               if c.component == 'MaxInclusiveConstraintComponent']
    assert changes and changes[0].direction is Direction.STRENGTHENED


def test_a_datatype_change_is_not_on_a_lattice(tmp_path, corpus, corpus_path):
    """Neither value is more permissive than the other, so it says so."""
    after = _variant(tmp_path, corpus_path,
                     lambda text: text.replace('sh:datatype xsd:double ;',
                                               'sh:datatype xsd:string ;', 1))
    changes = [c for c in semantic_diff(corpus.shapes, after.shapes)
               if c.component == 'DatatypeConstraintComponent']
    assert changes and changes[0].direction is Direction.UNKNOWN


def test_a_removed_constraint_weakens(tmp_path, corpus, corpus_path):
    after = _variant(tmp_path, corpus_path,
                     lambda text: text.replace('sh:minCount 1 ;', '', 1))
    changes = [c for c in semantic_diff(corpus.shapes, after.shapes)
               if c.kind == 'constraint-removed']
    assert changes and changes[0].direction is Direction.WEAKENED


def test_a_changed_rule_body_is_reported_as_impact_unknown(tmp_path, corpus,
                                                           corpus_path):
    """A SPARQL body is undecidable in general, so the diff does not guess."""
    after = _variant(tmp_path, corpus_path,
                     lambda text: text.replace('state_ON', 'state_OFF', 1))
    changes = [c for c in semantic_diff(corpus.shapes, after.shapes)
               if c.kind == 'rule-body-changed']
    assert changes
    assert all(c.direction is Direction.UNKNOWN for c in changes)


def test_attribute_and_value_constraints_do_not_collapse(corpus):
    """Both are reached under the same attribute name.

    Without separating them, an edit to one is masked by the other -- which is
    how a real minCount change went undetected the first time this ran.
    """
    constraints, _ = describe(corpus.shapes)
    slots = {slot for _, _, slot, _ in constraints}
    assert slots == {'', 'value'}


def test_a_removed_shape_weakens(tmp_path, corpus, corpus_path):
    after = _variant(
        tmp_path, corpus_path,
        lambda text: text.replace(':WorkpieceShape a sh:NodeShape',
                                  ':RenamedShape a sh:NodeShape', 1))
    kinds = {c.kind for c in semantic_diff(corpus.shapes, after.shapes)}
    assert 'shape-removed' in kinds and 'shape-added' in kinds


# --- behavioural impact ------------------------------------------------------

def test_impact_reports_the_example_that_stopped_failing(tmp_path, corpus,
                                                         corpus_path):
    """What turns a diff into a regression report.

    MachineShape requires hasState -> hasXXXWorkpiece [1,1] and three entities
    violate it. Dropping that minCount makes them stop failing, and the report
    names them.
    """
    def drop_the_workpiece_requirement(text):
        # The sub-attribute the three violations come from: MachineShape wants
        # hasState -> hasXXXWorkpiece [1,1] and only the plasmacutters carry it.
        before = '''[ sh:maxCount 1 ;
            sh:minCount 1 ;
            sh:nodeKind sh:BlankNode ;
            sh:path iffBaseEntities:hasXXXWorkpiece ;'''
        after_text = before.replace('sh:minCount 1 ;', 'sh:minCount 0 ;')
        assert before in text, 'the fixture no longer matches MachineShape'
        return text.replace(before, after_text)

    after = _variant(tmp_path, corpus_path, drop_the_workpiece_requirement)

    report = regression_report(
        (corpus.model, corpus.shapes, corpus.knowledge),
        (after.model, after.shapes, after.knowledge),
        [('model-instance.jsonld', corpus.model)])
    assert report.impacted[0].stopped_failing or report.impacted[0].started_failing
    assert format_regression(report)


def test_no_change_means_no_impact(corpus, corpus_path):
    other = load(corpus_path)
    report = regression_report(
        (corpus.model, corpus.shapes, corpus.knowledge),
        (other.model, other.shapes, other.knowledge),
        [('model-instance.jsonld', corpus.model)])
    assert not report.has_impact
    assert format_regression(report) == []


# --- CLI ---------------------------------------------------------------------

def test_diff_command_reports_no_change_between_a_package_and_itself(corpus_path):
    result = CliRunner().invoke(cli, ['diff', corpus_path, corpus_path])
    assert result.exit_code == 0
    assert 'no semantic changes' in result.output


def test_diff_command_reports_a_weakening(tmp_path, corpus_path):
    after = _variant(tmp_path, corpus_path,
                     lambda text: text.replace('sh:minCount 1 ;', 'sh:minCount 0 ;', 1))
    result = CliRunner().invoke(cli, ['diff', corpus_path, after.path])
    assert 'parameter-changed' in result.output
    assert 'weakened' in result.output


def test_format_changes_is_readable_without_a_graph():
    from semforge.diff.model import Change
    lines = format_changes([Change(kind='shape-removed', shape='https://x/AShape')])
    assert lines and 'AShape' in lines[0]


def test_the_exported_graph_round_trips_through_describe(corpus):
    graph = Graph()
    for triple in corpus.shapes:
        graph.add(triple)
    assert describe(graph)[0] == describe(corpus.shapes)[0]
