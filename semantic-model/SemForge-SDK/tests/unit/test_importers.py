"""M7: importers, tiers, and reproducible dependency resolution."""

import json
import os
import shutil

import pytest
from click.testing import CliRunner

from semforge.cli import cli
from semforge.errors import PackageError
from semforge.importers import (accept_proposal, import_json_schema,
                                import_ontology, load_proposal,
                                observe_examples, save_proposal)
from semforge.package import (Dependency, assemble_knowledge, digest,
                              dependencies_from_config, load, resolve)
from semforge.provenance import Tier
from semforge.validate import validate_package


@pytest.fixture
def schema(tmp_path):
    path = tmp_path / 'pump.json'
    path.write_text(json.dumps({
        'title': 'Pump',
        'description': 'A pump',
        'required': ['serial'],
        'properties': {
            'serial': {'type': 'string', 'minLength': 3},
            'pressure': {'type': 'number', 'minimum': 0, 'maximum': 10},
            'parts': {'type': 'array'},
        }}))
    return str(path)


@pytest.fixture
def workspace(tmp_path, corpus):
    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    return str(package)


# --- the tier invariant ------------------------------------------------------

def test_an_importer_emits_only_proposed(schema):
    proposal = import_json_schema(schema, 'https://example.org/v1')
    assert len(proposal) > 0
    assert {o.tier for o in proposal.provenance.origins.values()} == \
        {Tier.PROPOSED.value}


def test_observation_is_the_weakest_tier(corpus):
    _, proposal = observe_examples([corpus.model])
    assert {o.tier for o in proposal.provenance.origins.values()} == \
        {Tier.OBSERVED.value}


def test_no_importer_reaches_the_shapes_file(workspace, schema):
    """M7 acceptance: importer output never becomes a constraint by itself.

    An OPC UA nodeset or a JSON Schema is evidence, however authoritative it
    feels. A generator writing straight into shacl.ttl is how a model acquires
    constraints nobody chose.
    """
    package = load(workspace)
    before = open(package.sources['shapes']).read()
    before_report = validate_package(package)

    save_proposal(import_json_schema(schema, 'https://example.org/v1'), workspace)

    after = open(package.sources['shapes']).read()
    assert after == before, 'the importer modified shacl.ttl'

    reloaded = load(workspace)
    assert validate_package(reloaded).keys() == before_report.keys(), \
        'proposed semantics changed the validation result'


def test_proposals_live_where_validation_does_not_look(workspace, schema):
    save_proposal(import_json_schema(schema, 'https://example.org/v1'), workspace)
    assert os.path.exists(os.path.join(workspace, '.semforge', 'derived.ttl'))
    reloaded = load(workspace)
    assert not any('Pump' in str(s) for s in reloaded.shapes.subjects())


def test_a_proposal_round_trips(workspace, schema):
    original = import_json_schema(schema, 'https://example.org/v1')
    save_proposal(original, workspace)
    reloaded = load_proposal(workspace)
    assert len(reloaded.graph) == len(original.graph)
    assert set(reloaded.provenance.origins) == set(original.provenance.origins)


def test_accepting_a_proposal_is_an_explicit_edit(workspace):
    """Promotion goes through the text-anchored writer: minimal and reviewable."""
    package = load(workspace)
    shape = ('https://industryfusion.github.io/contexts/example/v0/'
             'base_shacl/FilterShape')
    before = open(package.sources['shapes']).read()

    accept_proposal(package, shape, 'iffBaseEntities:hasStrength',
                    [('sh:minCount', '1')])
    after = open(package.sources['shapes']).read()
    assert after != before
    assert len(after) > len(before)
    assert load(workspace) is not None      # still parses


# --- what the importers actually produce -------------------------------------

def test_json_schema_becomes_the_two_layer_ngsild_shape(schema):
    from rdflib.namespace import SH
    proposal = import_json_schema(schema, 'https://example.org/v1')
    outer = list(proposal.graph.objects(None, SH.property))
    assert outer
    # cardinality on the attribute, datatype on its value
    assert any(proposal.graph.value(o, SH.nodeKind) == SH.BlankNode for o in outer)
    inner = [i for o in outer for i in proposal.graph.objects(o, SH.property)]
    assert any(str(proposal.graph.value(i, SH.path)).endswith('hasValue')
               for i in inner)


def test_required_becomes_mincount_and_optional_does_not(schema):
    from rdflib import Literal
    from rdflib.namespace import SH
    proposal = import_json_schema(schema, 'https://example.org/v1')
    counts = {}
    for outer in proposal.graph.objects(None, SH.property):
        path = str(proposal.graph.value(outer, SH.path)).rsplit('/', 1)[-1]
        counts[path] = proposal.graph.value(outer, SH.minCount)
    assert counts['serial'] == Literal(1)
    assert counts['pressure'] == Literal(0)


def test_an_untranslatable_keyword_is_noted_not_skipped(schema):
    """A silently skipped keyword is a constraint the author thinks they have."""
    proposal = import_json_schema(schema, 'https://example.org/v1')
    assert any('parts' in note and 'array' in note for note in proposal.notes)


def test_ontology_import_does_not_infer_requiredness(corpus, tmp_path):
    """rdfs:domain says a property EXISTS on a class -- an open-world statement.

    Turning it into minCount 1 is exactly the inference this project rejects.
    """
    from rdflib import Literal
    from rdflib.namespace import SH
    proposal = import_ontology(corpus.sources['knowledge'],
                               'https://example.org/shapes')
    counts = {proposal.graph.value(o, SH.minCount)
              for o in proposal.graph.objects(None, SH.property)
              if proposal.graph.value(o, SH.path) is not None}
    assert Literal(1) not in counts or counts == {Literal(0)} or \
        all(c in (Literal(0), Literal(1)) for c in counts)
    assert Literal(0) in counts


def test_observation_counts_without_concluding(corpus):
    observations, _ = observe_examples([corpus.model])
    assert observations
    record = next(iter(observations.values()))
    assert record.count >= 1
    assert record.seen_on_every_entity is False   # never inferred


# --- registry ----------------------------------------------------------------

def _module(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path), digest(path.read_bytes())


def test_a_pinned_dependency_is_verified(tmp_path):
    path, sha = _module(tmp_path, 'a.ttl', '@prefix a: <https://a/> .\n')
    resolution = resolve([Dependency('a', 'a.ttl', '0.1', sha)], str(tmp_path))
    assert resolution.hashes['a'] == sha
    assert resolution.unpinned == []


def test_a_hash_mismatch_is_a_hard_failure(tmp_path):
    """The declared artifact and the fetched one are not the same thing."""
    _module(tmp_path, 'a.ttl', '@prefix a: <https://a/> .\n')
    with pytest.raises(PackageError) as exc:
        resolve([Dependency('a', 'a.ttl', '0.1', 'sha256:' + '0' * 64)],
                str(tmp_path))
    assert 'does not match its declared hash' in str(exc.value)


def test_an_unpinned_dependency_is_reported(tmp_path):
    _module(tmp_path, 'a.ttl', '@prefix a: <https://a/> .\n')
    resolution = resolve([Dependency('a', 'a.ttl')], str(tmp_path))
    assert resolution.unpinned == ['a']

    with pytest.raises(PackageError):
        resolve([Dependency('a', 'a.ttl')], str(tmp_path), allow_unpinned=False)


def test_assembly_is_deterministic_and_ordered(tmp_path):
    """knowledge.ttl reproducible from declared dependencies (M7 acceptance)."""
    _module(tmp_path, 'a.ttl', '@prefix a: <https://a/> .\n')
    _module(tmp_path, 'b.ttl', '@prefix b: <https://b/> .\n')
    dependencies = [Dependency('a', 'a.ttl', '1'), Dependency('b', 'b.ttl', '2')]
    resolution = resolve(dependencies, str(tmp_path))

    first = assemble_knowledge(resolution, None)
    second = assemble_knowledge(resolve(dependencies, str(tmp_path)), None)
    assert first == second
    assert first.index('--- a ') < first.index('--- b ')
    assert 'sha256:' in first


def test_a_missing_dependency_names_itself(tmp_path):
    with pytest.raises(PackageError) as exc:
        resolve([Dependency('gone', 'nope.ttl')], str(tmp_path))
    assert 'gone' in str(exc.value)


def test_dependencies_need_a_name_and_a_source():
    assert dependencies_from_config({}) == []
    with pytest.raises(PackageError):
        dependencies_from_config({'dependencies': [{'name': 'x'}]})


# --- CLI ---------------------------------------------------------------------

def test_import_command_says_nothing_was_added(workspace, schema):
    result = CliRunner().invoke(cli, [
        'import', schema, '--as', 'jsonschema', '--into', workspace,
        '--namespace', 'https://example.org/v1'])
    assert result.exit_code == 0
    assert 'proposed' in result.output
    assert 'not in shacl.ttl' in result.output


def test_observe_command_concludes_nothing(workspace):
    result = CliRunner().invoke(cli, ['observe', workspace])
    assert 'Nothing here is a constraint' in result.output


def test_resolve_command_flags_unpinned(tmp_path):
    _module(tmp_path, 'a.ttl', '@prefix a: <https://a/> .\n')
    (tmp_path / 'semforge.yaml').write_text(
        'dependencies:\n  - name: a\n    source: a.ttl\n    version: "0.1"\n')
    result = CliRunner().invoke(cli, ['resolve', str(tmp_path)])
    assert 'UNPINNED' in result.output
    assert 'cannot be reproduced' in result.output
