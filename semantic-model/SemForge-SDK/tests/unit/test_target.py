"""M4: profile capability check, deterministic export, SQLite cross-check."""

import filecmp
import json
import os

import pytest
from rdflib import Graph

from semforge.errors import PackageError
from semforge.package import load
from semforge.target import EmissionMode, builtin_profile, check_package, export
from semforge.target.crosscheck import available, cross_check, parse_event

SHAPE_PREFIX = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix ex: <https://example.org/> .
'''


def _package_with_shapes(tmp_path, corpus, turtle):
    import shutil
    package = tmp_path / 'pkg'
    package.mkdir()
    shutil.copy(corpus.sources['knowledge'], package / 'knowledge.ttl')
    shutil.copy(corpus.sources['model'], package / 'model-instance.jsonld')
    (package / 'shacl.ttl').write_text(SHAPE_PREFIX + turtle)
    return load(str(package))


# --- capability check --------------------------------------------------------

def test_the_corpus_compiles_under_the_shacl2flink_profile(corpus):
    assert check_package(corpus, builtin_profile()) == []


def test_the_profile_mirrors_the_compilers_own_limit():
    """MAX_SUBPROPERTY_DEPTH is 2 in shacl2flink/lib/utils.py: three levels."""
    profile = builtin_profile()
    assert profile.max_subproperty_depth == 2
    assert profile.max_levels == 3


def test_a_path_deeper_than_the_profile_is_reported_with_a_line(tmp_path, corpus):
    """C1: a capability problem is a diagnostic an author can act on."""
    deep = _package_with_shapes(tmp_path, corpus, '''
ex:DeepShape a sh:NodeShape ; sh:targetClass ex:C ;
    sh:property [ sh:path ex:a ; sh:minCount 1 ;
        sh:property [ sh:path ex:b ; sh:minCount 1 ;
            sh:property [ sh:path ex:c ; sh:minCount 1 ;
                sh:property [ sh:path ex:d ; sh:minCount 1 ] ] ] ] .
''')
    found = check_package(deep, builtin_profile())
    codes = [d.code for d in found]
    assert 'SF-CAP-001' in codes
    depth_error = next(d for d in found if d.code == 'SF-CAP-001')
    file_part, _, line = depth_error.locator.rpartition(':')
    assert file_part.endswith('shacl.ttl') and line.isdigit()
    assert 'levels deep' in depth_error.message


def test_a_value_path_does_not_count_as_a_level(tmp_path, corpus):
    """ngsild:hasValue says how to read a value; it is not a sub-attribute."""
    shallow = _package_with_shapes(tmp_path, corpus, '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
    sh:property [ sh:path ex:a ; sh:minCount 1 ;
        sh:property [ sh:path ngsild:hasValue ; sh:datatype ex:t ] ] .
''')
    assert [d for d in check_package(shallow, builtin_profile())
            if d.code == 'SF-CAP-001'] == []


def test_a_property_shape_with_no_constraint_is_rejected(tmp_path, corpus):
    """It would compile to nothing, and nothing looks exactly like conformance."""
    empty = _package_with_shapes(tmp_path, corpus, '''
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
    sh:property [ sh:path ex:a ; sh:order 1 ] .
''')
    assert 'SF-CAP-004' in [d.code for d in check_package(empty, builtin_profile())]


def test_the_mixed_view_case_is_refused(tmp_path, corpus):
    """Cardinality assertion 7, deferred here from M1.

    The target picks a data view per VARIABLE; a single-graph evaluation
    cannot, so an aggregating query that also reads other attributes is refused
    rather than evaluated against whichever graph is loaded.
    """
    mixed = _package_with_shapes(tmp_path, corpus, '''
@prefix semforge: <https://industryfusion.github.io/semforge/v0/> .
ex:Mixed a sh:NodeShape ; sh:targetClass ex:C ; semforge:dataView "history" ;
    sh:sparql [ a sh:SPARQLConstraints ; sh:select """
SELECT $this (COUNT(?v) AS ?n) WHERE {
  $this ex:reading [ ngsild:hasValue ?v ] .
  $this ex:state [ ngsild:hasValue ?s ]
} GROUP BY $this
""" ] .
''')
    found = [d for d in check_package(mixed, builtin_profile())
             if d.code == 'SF-CAP-005']
    assert found
    assert 'per VARIABLE' in found[0].message


# --- export ------------------------------------------------------------------

def test_h5_export_is_byte_identical_across_runs(corpus, tmp_path):
    first, second = str(tmp_path / 'a'), str(tmp_path / 'b')
    export(corpus, first)
    export(corpus, second)
    for name in ('knowledge.ttl', 'shacl.ttl', 'model-instance.jsonld'):
        assert filecmp.cmp(os.path.join(first, name), os.path.join(second, name),
                           shallow=False), f'{name} differs between exports'


def test_export_preserves_the_source_text_and_its_comments(corpus, tmp_path):
    """Not reserialised: rdflib would reorder statements and drop comments."""
    out = str(tmp_path / 'out')
    export(corpus, out)
    assert filecmp.cmp(corpus.sources['shapes'],
                       os.path.join(out, 'shacl.ttl'), shallow=False)


def test_compile_mode_keeps_the_observation_stream(corpus, tmp_path):
    out = str(tmp_path / 'out')
    export(corpus, out, EmissionMode.COMPILE)
    entities = json.load(open(os.path.join(out, 'model-instance.jsonld')))
    strengths = [e for e in entities if e.get('id') == 'urn:filter:1'][0]
    key = [k for k in strengths if k.endswith('hasStrength')][0]
    assert len(strengths[key]) == 4


def test_broker_mode_collapses_to_the_latest_observation(corpus, tmp_path):
    """NGSI-LD 4.5.5.1: one default instance per attribute in any request."""
    out = str(tmp_path / 'out')
    written = export(corpus, out, EmissionMode.BROKER)
    entities = json.load(open(os.path.join(out, 'model-instance.jsonld')))
    filter1 = [e for e in entities if e.get('id') == 'urn:filter:1'][0]
    key = [k for k in filter1 if k.endswith('hasStrength')][0]
    assert len(filter1[key]) == 1
    assert filter1[key][0]['value'] == 0.6
    assert written['collapsed'] == 3


def test_export_emits_a_local_context(corpus, tmp_path):
    """A build must not depend on fetching a remote @context."""
    out = str(tmp_path / 'out')
    written = export(corpus, out)
    assert 'context' in written and os.path.exists(written['context'])


def test_exported_turtle_still_parses(corpus, tmp_path):
    out = str(tmp_path / 'out')
    export(corpus, out)
    for name in ('knowledge.ttl', 'shacl.ttl'):
        Graph().parse(os.path.join(out, name), format='turtle')


# --- cross-check -------------------------------------------------------------

def test_parse_event_names_the_last_path_segment():
    """The compiler names a count alert after the whole path; the segment that
    identifies the constraint is the last one."""
    component, name = parse_event(
        'CountConstraintComponent(https://x/hasState[0] ==> https://x/hasWorkpiece)')
    assert component == 'CountConstraintComponent'
    assert name == 'hasWorkpiece'


def test_parse_event_handles_a_sparql_shape_name():
    assert parse_event('SPARQLConstraintComponent(StateOnCutterShape)') == \
        ('SPARQLConstraintComponent', 'StateOnCutterShape')


def test_parse_event_passes_through_something_it_does_not_understand():
    assert parse_event('nonsense') == ('nonsense', '')


def test_availability_is_reported_not_assumed():
    ok, reason = available('/nonexistent/shacl2flink')
    assert ok is False and 'not found' in reason


def test_an_unavailable_cross_check_never_reads_as_a_pass(corpus):
    """Same rule as the consistency checker: degrade to 'not run', never to
    'ran and agreed'."""
    found = cross_check(corpus, None, '/nonexistent/shacl2flink')
    assert len(found) == 1
    assert found[0].code == 'SF-XCHK-000'
    assert 'not run' in found[0].message


def test_cross_check_reports_honestly_against_the_real_compiler(corpus):
    """Whatever happens, it reports rather than crashing or claiming success.

    Which shacl2flink checkout is on disk decides the outcome, so the assertion
    is on the CONTRACT: every finding is a divergence-category diagnostic, and
    a compiler that cannot build the package is reported as such rather than
    silently treated as agreement.
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.abspath(corpus.path)))
    candidate = os.path.join(os.path.dirname(os.path.dirname(here)), 'shacl2flink')
    from semforge.validate import validate_package

    found = cross_check(corpus, validate_package(corpus), candidate,
                        python_exe=sys.executable)
    assert all(d.category == 'divergence' for d in found)
    for diagnostic in found:
        assert diagnostic.code.startswith('SF-XCHK')


def test_export_refuses_an_unloadable_package(tmp_path):
    with pytest.raises(PackageError):
        load(str(tmp_path))
