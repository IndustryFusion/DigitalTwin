"""Provenance and tiers: why a constraint exists."""

from click.testing import CliRunner

from semforge.cli import cli
from semforge.provenance import Origin, Provenance, Tier, build_provenance


def test_every_corpus_shape_has_an_origin_with_a_locator(corpus):
    """M3 acceptance: why() on an imported constraint reports origin, file and line."""
    from semforge.validate.shapes import node_shapes

    provenance = build_provenance(corpus)
    for shape in node_shapes(corpus.shapes):
        origin = provenance.of(shape)
        assert origin is not None, f'{shape} has no provenance'
        assert origin.kind == 'imported-shacl'
        assert origin.tier == Tier.DECLARED.value
        assert ':' in origin.locator and origin.locator.rsplit(':', 1)[1].isdigit()


def test_ontology_elements_are_distinguished_from_shapes(corpus):
    provenance = build_provenance(corpus)
    kinds = {origin.kind for origin in provenance.origins.values()}
    assert kinds == {'imported-shacl', 'imported-ontology'}


def test_provenance_round_trips_through_the_sidecar(corpus, tmp_path):
    """Stored out of band, never as triples in knowledge.ttl or shacl.ttl.

    Those files feed shacl2flink, closure computation and Fuseki, all of which
    would read tooling triples as domain knowledge.
    """
    provenance = build_provenance(corpus)
    path = str(tmp_path / '.semforge' / 'provenance.jsonl')
    provenance.save(path)

    reloaded = Provenance.load(path)
    assert len(reloaded) == len(provenance)
    for subject, origin in provenance.origins.items():
        assert reloaded.of(subject).locator == origin.locator


def test_loading_absent_provenance_is_empty_not_an_error(tmp_path):
    assert len(Provenance.load(str(tmp_path / 'nothing.jsonl'))) == 0


def test_tiers_exist_and_declared_is_the_only_one_that_compiles():
    assert {t.value for t in Tier} == {'observed', 'proposed', 'declared'}
    assert Origin(subject='x', kind='derived-proposal',
                  tier=Tier.PROPOSED.value).tier != Tier.DECLARED.value


def test_explain_reports_declaration_site_and_evidence(corpus_path):
    result = CliRunner().invoke(cli, ['explain', corpus_path, 'StateOnFilterShape'])
    assert 'imported-shacl' in result.output
    assert 'shacl.ttl:' in result.output
    assert 'tier: declared' in result.output


def test_explain_warns_when_nothing_proves_a_constraint_can_fire(corpus_path):
    """The H6 warning, surfaced where an author will actually read it."""
    result = CliRunner().invoke(cli, ['explain', corpus_path, 'StateOnFilterShape'])
    assert 'no example proves this can fire' in result.output


def test_explain_on_an_unknown_subject_says_so(corpus_path):
    result = CliRunner().invoke(cli, ['explain', corpus_path, 'NoSuchShape'])
    assert result.exit_code == 1
    assert 'nothing known' in result.output
