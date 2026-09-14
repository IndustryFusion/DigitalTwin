"""One name per namespace, across every artifact."""

import json
import shutil

import pytest
from click.testing import CliRunner
from rdflib import Graph
from rdflib.compare import isomorphic

from semforge.cli import cli
from semforge.package import load
from semforge.package.prefixes import (align, canonical_map, check,
                                       context_prefixes, declared_prefixes,
                                       file_prefixes, names_by_namespace)

BASE = 'https://industryfusion.github.io/contexts/example/v0/'


@pytest.fixture
def package(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', target / extra)
    return load(str(target))


def test_the_context_is_read_as_the_source_of_truth(corpus):
    """context.jsonld declares terms with "@prefix": true."""
    found = context_prefixes(corpus.path)
    assert found['iffBaseEntities'] == BASE + 'base_entities/'
    assert found['material'].endswith('/material/')


def test_the_context_name_wins_where_the_package_declares_nothing(corpus):
    """base_knowledge/ is `base`, and semforge.yaml deliberately stays quiet.

    Two names for one namespace do not survive rdflib, and shacl2flink requires
    the survivor to be `base`, so the context's name is the only workable one.
    """
    assert context_prefixes(corpus.path)['base'] == BASE + 'base_knowledge/'
    assert names_by_namespace(corpus.path)[BASE + 'base_knowledge/'] == 'base'
    assert 'iffBaseKnowledge' not in declared_prefixes(corpus.path)


def test_the_package_declaration_still_overrides_where_it_speaks(corpus):
    """The mechanism is intact even though base_knowledge does not use it."""
    declared = declared_prefixes(corpus.path)
    assert declared['iffBaseShacl'] == BASE + 'base_shacl/'
    assert names_by_namespace(corpus.path)[BASE + 'base_shacl/'] == 'iffBaseShacl'


def test_the_corpus_is_fully_aligned(corpus):
    """All three artifacts agree on every namespace, including the model."""
    assert check(corpus) == []


def test_no_ambiguous_or_generated_prefix_survives(corpus):
    """The hazard this removes: one prefix, two meanings.

    ':' denoted base_shacl in shacl.ttl and base_entities in knowledge.ttl, and
    'default1:' denoted filter_shacl and base_knowledge. A term copied between
    the files changed meaning silently.
    """
    seen = {}
    for role in ('shapes', 'knowledge'):
        for name, namespace in file_prefixes(corpus.sources[role])[0].items():
            assert name, 'the empty prefix is ambiguous across files'
            assert not name.startswith('default'), \
                f'{name} is an rdfpipe-generated name, not an agreed one'
            seen.setdefault(name, set()).add(namespace)
    assert all(len(namespaces) == 1 for namespaces in seen.values())


def test_every_namespace_has_exactly_one_name(corpus):
    by_name = {}
    for role in ('shapes', 'knowledge'):
        for name, namespace in file_prefixes(corpus.sources[role])[0].items():
            by_name.setdefault(namespace, set()).add(name)
    for namespace, names in by_name.items():
        assert len(names) == 1, f'{namespace} is called {names}'


# --- the alignment itself ----------------------------------------------------

def test_alignment_never_changes_the_graph(package):
    """A rename is a spelling change. If the graph moves, something is wrong."""
    before = Graph()
    before.parse(package.sources['shapes'], format='turtle')

    align(package)

    after = Graph()
    after.parse(package.sources['shapes'], format='turtle')
    assert isomorphic(before, after)


def test_alignment_is_idempotent(package):
    align(package)
    assert align(load(package.path), dry_run=True) == {}


def test_alignment_leaves_sparql_bodies_alone(tmp_path, corpus):
    """A SPARQL body declares its own prefixes and is a separate scope.

    Rewriting into one would break queries that are currently correct, so the
    aligner steps over string literals. The kms bodies were brought to `base:`
    by a deliberate separate pass, verified by comparing validation results
    before and after -- not by the aligner reaching inside them.
    """
    target = tmp_path / 'pkg'
    target.mkdir()
    shutil.copy(corpus.sources['knowledge'], target / 'knowledge.ttl')
    shutil.copy(corpus.sources['model'], target / 'model-instance.jsonld')
    shutil.copy(f'{corpus.path}/context.jsonld', target / 'context.jsonld')
    shutil.copy(f'{corpus.path}/semforge.yaml', target / 'semforge.yaml')

    # `wrong:` at the Turtle level should be renamed to the agreed name; the
    # SPARQL body names the same namespace differently and must not be touched.
    body = ('PREFIX inner: <https://industryfusion.github.io/contexts/'
            'example/v0/base_knowledge/>\nSELECT $this WHERE '
            '{ $this ?p inner:state_ON }')
    (target / 'shacl.ttl').write_text(
        '@prefix sh: <http://www.w3.org/ns/shacl#> .\n'
        '@prefix wrong: <https://industryfusion.github.io/contexts/example/'
        'v0/base_knowledge/> .\n'
        '@prefix ex: <https://example.org/> .\n'
        'ex:S a sh:NodeShape ; sh:targetClass wrong:MachineState ;\n'
        '    sh:sparql [ a sh:SPARQLConstraints ; sh:select """' + body + '""" ] .\n')

    applied = align(load(str(target)))
    after = (target / 'shacl.ttl').read_text()

    assert applied['shapes'] == {'wrong': 'base'}
    assert 'base:MachineState' in after, 'the Turtle level should be renamed'
    assert 'PREFIX inner:' in after, 'the SPARQL body must be left alone'
    assert 'inner:state_ON' in after


def test_alignment_reports_a_namespace_nobody_named(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('model',
                                                        'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    shutil.copy(f'{corpus.path}/context.jsonld', target / 'context.jsonld')
    # The package's own half of the table comes with it: without semforge.yaml
    # this is not a package missing ONE name, it is a package missing four.
    shutil.copy(f'{corpus.path}/semforge.yaml', target / 'semforge.yaml')
    (target / 'shacl.ttl').write_text(
        '@prefix odd: <https://nobody.example/named/> .\n'
        '@prefix sh: <http://www.w3.org/ns/shacl#> .\n')

    findings = check(load(str(target)))
    unnamed = [f for f in findings if f.code == 'SF-PFX-003']
    assert [f.namespace for f in unnamed] == ['https://nobody.example/named/']
    # Names are package-wide, so inventing one in a file is an error: nothing
    # else in the package knows it.
    assert unnamed[0].severity == 'error'
    assert 'defined once, for the whole package' in unnamed[0].message


def test_an_ambiguous_prefix_is_an_error_not_a_warning(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    shutil.copy(corpus.sources['model'], target / 'model-instance.jsonld')
    shutil.copy(f'{corpus.path}/context.jsonld', target / 'context.jsonld')
    (target / 'knowledge.ttl').write_text(
        '@prefix p: <https://example.org/one/> .\n')
    (target / 'shacl.ttl').write_text(
        '@prefix p: <https://example.org/two/> .\n')

    findings = check(load(str(target)))
    ambiguous = [f for f in findings if f.code == 'SF-PFX-001']
    assert ambiguous and ambiguous[0].severity == 'error'
    assert 'changes meaning' in ambiguous[0].message


def test_canonical_map_merges_both_sources(corpus):
    found = canonical_map(corpus.path)
    assert 'iffBaseShacl' in found          # only in semforge.yaml
    assert 'iffBaseEntities' in found       # only in the context


# --- CLI ---------------------------------------------------------------------

def test_prefixes_command_reports_a_clean_package(corpus_path):
    result = CliRunner().invoke(cli, ['prefixes', corpus_path])
    assert result.exit_code == 0
    assert 'one agreed name' in result.output


def test_prefixes_command_fails_on_an_ambiguous_prefix(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    shutil.copy(corpus.sources['model'], target / 'model-instance.jsonld')
    (target / 'knowledge.ttl').write_text('@prefix p: <https://a/> .\n')
    (target / 'shacl.ttl').write_text('@prefix p: <https://b/> .\n')
    result = CliRunner().invoke(cli, ['prefixes', str(target)])
    assert result.exit_code == 1
    assert 'SF-PFX-001' in result.output


def test_prefixes_fix_rewrites_and_then_reports_clean(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    shutil.copy(f'{corpus.path}/context.jsonld', target / 'context.jsonld')
    shutil.copy(f'{corpus.path}/semforge.yaml', target / 'semforge.yaml')

    source = (target / 'knowledge.ttl').read_text()
    (target / 'knowledge.ttl').write_text(
        source.replace('@prefix iffFilterKnowledge:', '@prefix default9:')
              .replace('iffFilterKnowledge:', 'default9:'))

    result = CliRunner().invoke(cli, ['prefixes', str(target), '--fix'])
    assert 'default9: -> iffFilterKnowledge:' in result.output
    assert result.exit_code == 0


# --- the third artifact ------------------------------------------------------

def test_the_model_instance_is_checked_too(corpus):
    """Two Turtle files can agree with each other while the data differs."""
    from semforge.package.prefixes import model_prefixes

    used = model_prefixes(corpus.sources['model'])
    assert used['iffBaseEntities'] > 0
    assert 'base' in used, 'the fixture should still exercise the pending rename'


def test_the_model_agrees_with_the_shapes_now(corpus):
    """The rename that was pending is done -- in the other direction.

    shacl.ttl moved to `base:` rather than the model moving to
    iffBaseKnowledge:, because rdflib cannot carry two names for one namespace
    and shacl2flink requires this one to be `base`.
    """
    from semforge.package.prefixes import model_prefixes

    assert [f for f in check(corpus) if f.code == 'SF-PFX-004'] == []
    assert 'base' in model_prefixes(corpus.sources['model'])


def test_a_prefix_the_context_does_not_declare_is_an_error(tmp_path, corpus):
    import json

    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl')):
        shutil.copy(corpus.sources[role], target / name)
    shutil.copy(f'{corpus.path}/context.jsonld', target / 'context.jsonld')
    shutil.copy(f'{corpus.path}/semforge.yaml', target / 'semforge.yaml')
    with open(corpus.sources['model']) as handle:
        model = json.load(handle)
    model[0]['nosuchprefix:attr'] = {'type': 'Property', 'value': 1}
    (target / 'model-instance.jsonld').write_text(json.dumps(model))

    findings = check(load(str(target)))
    undeclared = [f for f in findings if f.code == 'SF-PFX-005']
    assert undeclared and undeclared[0].severity == 'error'
    assert 'will not expand' in undeclared[0].message


def test_two_names_for_one_namespace_do_not_survive_rdflib(corpus):
    """Why the context still calls base_knowledge `base` and nothing else.

    Adding iffBaseKnowledge alongside base looked additive -- two names, one
    namespace, legal JSON-LD, nothing written against `base` breaks. It is not
    additive in practice: rdflib binds ONE prefix per namespace, so the second
    name evicts the first. And shacl2flink reads the context through rdflib and
    requires the surviving name to be literally `base`
    (create_sql_checks_from_shacl.py: "No prefix 'base:' is found").

    So publishing that addition would have stopped the compiler for everyone.
    This pins the mechanism, so the next person to try it finds out here.
    """
    import rdflib

    graph = rdflib.Graph()
    graph.parse(f'{corpus.path}/context.jsonld', format='json-ld')
    bound = {prefix: str(namespace) for prefix, namespace in graph.namespaces()}
    assert bound.get('base') == BASE + 'base_knowledge/', \
        'shacl2flink requires the context to bind base_knowledge as "base"'

    with_both = rdflib.Graph()
    with_both.parse(data=json.dumps({'@context': [{
        'base': {'@id': BASE + 'base_knowledge/', '@prefix': True},
        'iffBaseKnowledge': {'@id': BASE + 'base_knowledge/', '@prefix': True},
    }]}), format='json-ld')
    names = [p for p, n in with_both.namespaces() if str(n) == BASE + 'base_knowledge/']
    assert len(names) == 1, 'rdflib kept both names; the eviction may be fixed'


def test_the_context_matches_what_is_published(corpus):
    """The vendored copy is a snapshot; divergence is the reproducibility bug."""
    found = context_prefixes(corpus.path)
    assert 'base' in found
    assert 'iffBaseKnowledge' not in found


# --- the names nobody should have to declare ---------------------------------

def test_the_standard_names_are_known_without_being_declared(tmp_path, corpus):
    """A shapes file binds `sh:`. No package should have to say so.

    Raising "used but not defined" to an error made every scaffolded project
    report its own shacl.ttl as having invented "sh:".
    """
    from semforge.package.prefixes import STANDARD, canonical_map

    target = tmp_path / 'bare'
    target.mkdir()
    (target / 'knowledge.ttl').write_text('')
    (target / 'shacl.ttl').write_text(
        '@prefix sh: <http://www.w3.org/ns/shacl#> .\n'
        '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n')
    (target / 'model-instance.jsonld').write_text('{"@graph": []}')

    known = canonical_map(str(target))
    assert {'rdf', 'rdfs', 'owl', 'xsd', 'sh', 'ngsild'} <= set(known)
    assert known['sh'] == STANDARD['sh']

    findings = check(load(str(target)))
    assert not [f for f in findings if f.code == 'SF-PFX-003'], \
        [f.message for f in findings]


def test_a_package_may_still_call_one_of_them_something_else(tmp_path, corpus):
    """Lowest precedence: what the package declares wins."""
    from semforge.package.prefixes import canonical_map

    target = tmp_path / 'own'
    target.mkdir()
    (target / 'knowledge.ttl').write_text('')
    (target / 'shacl.ttl').write_text('')
    (target / 'model-instance.jsonld').write_text('{"@graph": []}')
    (target / 'semforge.yaml').write_text(
        'namespaces:\n  shacl: http://www.w3.org/ns/shacl#\n')

    by_namespace = canonical_map(str(target))
    assert by_namespace['shacl'] == 'http://www.w3.org/ns/shacl#'


def test_a_standard_name_cannot_be_redefined_by_accident(tmp_path, corpus):
    from semforge.package.prefixes import add_namespace
    from semforge.errors import PackageError

    target = tmp_path / 'bare'
    target.mkdir()
    (target / 'knowledge.ttl').write_text('')
    (target / 'shacl.ttl').write_text('')
    (target / 'model-instance.jsonld').write_text('{"@graph": []}')

    with pytest.raises(PackageError) as raised:
        add_namespace(str(target), 'sh', 'https://example.org/mine/')
    assert 'a standard name the SDK knows' in str(raised.value)


def test_a_new_project_does_not_carry_them_as_boilerplate(tmp_path):
    from semforge.package.scaffold import create_package

    target = tmp_path / 'fresh'
    target.mkdir()
    create_package(str(target), name='fresh',
                   namespace='https://example.org/fresh/')
    declared = (target / 'semforge.yaml').read_text()
    assert 'ngsild: https://uri.etsi.org/ngsi-ld/' not in declared
    assert check(load(str(target))) == []
