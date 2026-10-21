"""NGSI-LD in SPARQL: the two steps an attribute takes, what Flink compiles,
and the help the editor gives -- on the corpus's real terms and shapes.

The rewrites are checked by applying them: a quick fix must take its
warning away and leave a query that parses; and on real data, the form a
fix produces must find what the form it replaced found.
"""

import base64
import json

import pytest
from lsprotocol import types
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF, SH

from semforge.ngsild import kinds
from semforge.sparql.check import check
from semforge.sparql.complete import complete, hover
from semforge.sparql.terms import Term, terms_for

ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
HEAD = (f'PREFIX iffBaseEntities: <{ENT}>\n'
        'PREFIX base: <https://industryfusion.github.io/contexts/example/v0/base_knowledge/>\n'
        'PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>\n'
        'PREFIX iffFilterKnowledge: '
        '<https://industryfusion.github.io/contexts/example/v0/filter_knowledge/>\n')
NGSI = {'skipped-layer', 'constant-object', 'explicit-node', 'variable-node', 'path',
        'plain-bracket', 'not-compiled', 'wrong-layer'}


@pytest.fixture(scope='module')
def terms(corpus):
    return terms_for(corpus)


def _ngsi(text, terms, kind='constraint'):
    return [f for f in check(text, terms, kind=kind) if f.code in NGSI]


# --- one table of kinds ---------------------------------------------------------------------

def test_every_kind_has_its_key_and_payload():
    assert kinds.PAYLOAD_KEY == {
        'Property': 'value', 'GeoProperty': 'value', 'Relationship': 'object',
        'JsonProperty': 'json', 'ListProperty': 'valueList', 'ListRelationship': 'objectList',
        'LanguageProperty': 'languageMap', 'VocabProperty': 'vocab'}
    assert kinds.PAYLOAD_NAME['LanguageProperty'] == 'hasLanguageMap'
    assert kinds.PAYLOAD_NAME['VocabProperty'] == 'hasVocab'
    assert kinds.PAYLOAD_NAME['ListRelationship'] == 'hasObjectList'
    assert kinds.KINDS_OF_PAYLOAD['hasValue'] == ['Property', 'GeoProperty']


def test_the_sdk_reads_the_new_kinds_everywhere():
    from semforge.cooked.choices import PAYLOAD_PATHS, RANGE_KIND
    from semforge.cooked.constrain import PAYLOAD_PATH
    from semforge.ngsild.build import KINDS
    from semforge.validate.applicable import NGSILD_VALUE_PATHS

    for kind in ('LanguageProperty', 'VocabProperty', 'ListRelationship'):
        assert RANGE_KIND[kinds.NGSILD + kind] == kind
        assert kind in KINDS and kind in PAYLOAD_PATH
    for name in ('hasLanguageMap', 'hasVocab', 'hasObjectList'):
        assert kinds.NGSILD + name in PAYLOAD_PATHS and kinds.NGSILD + name in NGSILD_VALUE_PATHS


def test_an_empty_object_list_is_normalised_like_an_empty_value_list():
    from semforge.ngsild.views import normalise_empty_lists

    graph = Graph()
    for name in ('hasValueList', 'hasObjectList'):
        graph.add((BNode(), URIRef(kinds.NGSILD + name), RDF.nil))
    assert normalise_empty_lists(graph) == 2
    assert (None, None, RDF.nil) not in graph


# --- what the editor flags ------------------------------------------------------------------------

def test_the_corpus_reads_every_attribute_the_right_way(corpus, terms):
    for predicate, kind in ((SH.select, 'constraint'), (SH.construct, 'rule')):
        for query in corpus.shapes.objects(None, predicate):
            assert _ngsi(str(query), terms, kind) == [], str(query)[:120]


CASES = [
    ('skipped-layer', 'SELECT $this WHERE { $this iffBaseEntities:hasStrength ?s . FILTER(?s > 1) }',
     '?s', '[ ngsild:hasValue ?s ]'),
    ('skipped-layer', 'SELECT $this WHERE { $this iffBaseEntities:hasState ?s . ?s a ?t }',
     '?s', '[ ngsild:hasValue ?s ]'),
    ('constant-object', 'SELECT $this WHERE { $this iffBaseEntities:hasState base:state_ON }',
     'base:state_ON', '[ ngsild:hasValue base:state_ON ]'),
    ('constant-object', 'SELECT $this WHERE { $this iffBaseEntities:hasFilter <urn:filter:1> }',
     '<urn:filter:1>', '[ ngsild:hasObject <urn:filter:1> ]'),
    ('explicit-node', 'SELECT $this WHERE { $this iffBaseEntities:hasStrength ?a .\n'
     '  ?a ngsild:hasValue ?s .\n  FILTER(?s > 1) }', '?a', '[ ngsild:hasValue ?s ]'),
    ('variable-node', 'SELECT $this WHERE { $this iffBaseEntities:hasStrength ?a }', '?a',
     '[ ngsild:hasValue ?a ]'),
    ('variable-node', 'SELECT $this WHERE { $this iffBaseEntities:hasFilter ?filter . }',
     '?filter', '[ ngsild:hasObject ?filter ]'),
    ('path', 'SELECT $this WHERE { $this iffBaseEntities:hasStrength/ngsild:hasValue ?s . '
     'FILTER(?s > 1) }', 'iffBaseEntities:hasStrength/ngsild:hasValue ?s',
     'iffBaseEntities:hasStrength [ ngsild:hasValue ?s ]'),
    ('plain-bracket', 'SELECT $this WHERE { ?m iffFilterKnowledge:hasWasteclass '
     '[ ngsild:hasValue ?w ] }', '[ ngsild:hasValue ?w ]', '?w'),
    ('wrong-layer', 'SELECT $this WHERE { $this iffBaseEntities:hasFilter '
     '[ ngsild:hasValue ?f ] }', 'ngsild:hasValue', 'ngsild:hasObject'),
]


@pytest.mark.parametrize('code, body, at, replace', CASES)
def test_each_misreading_is_flagged_where_it_is(terms, code, body, at, replace):
    text = HEAD + body
    (found,) = _ngsi(text, terms)
    assert found.code == code and text[found.start:found.end] == at
    assert found.severity == 'warning', 'a warning: validation still reads it'
    assert found.data['replace'] == replace


@pytest.mark.parametrize('body', [
    'SELECT $this WHERE { $this iffBaseEntities:hasStrength [ ngsild:hasValue ?s ] }',
    'SELECT $this WHERE { $this iffBaseEntities:hasStrength [ ] }',
    'SELECT $this WHERE { $this iffBaseEntities:hasState [ ngsild:hasValue ?s ; '
    'ngsild:observedAt ?t ] }',
    'SELECT $this WHERE { ?m iffFilterKnowledge:hasWasteclass ?w . FILTER(?w != base:x) }',
    'SELECT $this WHERE { OPTIONAL { $this iffBaseEntities:hasState [ ngsild:hasValue ?s ] } }',
])
def test_the_right_forms_are_left_alone(terms, body):
    assert _ngsi(HEAD + body, terms) == []


def test_a_rule_s_template_is_read_too(terms):
    body = 'CONSTRUCT { $this iffBaseEntities:hasState ?v } WHERE { $this a ?t . BIND(1 AS ?v) }'
    assert [f.code for f in _ngsi(HEAD + body, terms, 'rule')] == ['variable-node']


def test_an_attribute_flink_does_not_know_is_said_once(terms):
    text = HEAD + ('SELECT $this WHERE { $this iffBaseEntities:hasJSON [ ngsild:hasJSON ?a ] .\n'
                   '  ?x iffBaseEntities:hasJSON [ ngsild:hasJSON ?b ] }')
    (found,) = _ngsi(text, terms)
    assert found.code == 'not-compiled' and text[found.start:found.end] == 'iffBaseEntities:hasJSON'
    assert found.data == {'attribute': ENT + 'hasJSON', 'kind': 'JsonProperty',
                          'domain': ENT + 'Cutter'}


# --- the quick fixes, applied ---------------------------------------------------------------------

def _uri(corpus_path):
    shape = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'
    ref = {'p': f'file://{corpus_path}/shacl.ttl', 's': shape, 'h': 0, 'k': 'constraint'}
    return 'semforge-sparql:/X.rq?' + base64.urlsafe_b64encode(
        json.dumps(ref).encode()).decode().rstrip('=')


def _apply(text, edits):
    from semforge.sparql.lexer import offset_of

    spans = sorted(((offset_of(text, e.range.start.line, e.range.start.character),
                     offset_of(text, e.range.end.line, e.range.end.character), e.new_text)
                    for e in edits), reverse=True)
    for start, end, new in spans:
        text = text[:start] + new + text[end:]
    return text


@pytest.mark.parametrize('code, body, at, replace', CASES)
def test_each_fix_takes_its_warning_away(corpus_path, terms, code, body, at, replace):
    from semforge.editor import server
    from semforge.editor.sparqldocs import code_actions, context, diagnostics

    uri = _uri(corpus_path)
    ctx = context(uri, server._package_for, server.package_root, server._uri_to_path)
    text = HEAD + body
    found = [d for d in diagnostics(text, ctx) if d.code == code]
    params = types.CodeActionParams(
        text_document=types.TextDocumentIdentifier(uri=uri), range=found[0].range,
        context=types.CodeActionContext(diagnostics=found))
    fix = next(a for a in code_actions(uri, text, ctx, params) if a.diagnostics)
    fixed = _apply(text, fix.edit.changes[uri])
    assert replace in fixed
    assert [d for d in diagnostics(fixed, ctx) if d.code in NGSI] == [], fixed
    assert not [d for d in diagnostics(fixed, ctx) if d.code == 'syntax'], fixed


def test_the_explicit_form_s_fix_folds_the_instance_in(corpus_path, terms):
    from semforge.editor import server
    from semforge.editor.sparqldocs import code_actions, context, diagnostics

    uri = _uri(corpus_path)
    ctx = context(uri, server._package_for, server.package_root, server._uri_to_path)
    text = HEAD + ('SELECT $this WHERE {\n    $this iffBaseEntities:hasStrength ?a .\n'
                   '    ?a ngsild:hasValue ?s .\n    FILTER(?s > 1)\n}\n')
    found = [d for d in diagnostics(text, ctx) if d.code == 'explicit-node']
    params = types.CodeActionParams(
        text_document=types.TextDocumentIdentifier(uri=uri), range=found[0].range,
        context=types.CodeActionContext(diagnostics=found))
    (fix,) = [a for a in code_actions(uri, text, ctx, params) if a.diagnostics]
    assert fix.title == 'Write the instance as [ ngsild:hasValue ?s ]'
    assert _apply(text, fix.edit.changes[uri]).split('{\n', 1)[1] == (
        '    $this iffBaseEntities:hasStrength [ ngsild:hasValue ?s ] .\n'
        '    FILTER(?s > 1)\n}\n')


def test_not_compiled_offers_the_shape_as_a_command(corpus_path):
    from semforge.editor import server
    from semforge.editor.sparqldocs import code_actions, context, diagnostics

    uri = _uri(corpus_path)
    ctx = context(uri, server._package_for, server.package_root, server._uri_to_path)
    text = HEAD + 'SELECT $this WHERE { $this iffBaseEntities:hasJSON [ ngsild:hasJSON ?j ] }'
    found = [d for d in diagnostics(text, ctx) if d.code == 'not-compiled']
    params = types.CodeActionParams(
        text_document=types.TextDocumentIdentifier(uri=uri), range=found[0].range,
        context=types.CodeActionContext(diagnostics=found))
    (fix,) = [a for a in code_actions(uri, text, ctx, params) if a.diagnostics]
    assert fix.command.command == 'semforge.nestForFlink'
    assert fix.command.arguments == [{'packageUri': f'file://{corpus_path}/shacl.ttl',
                                      'attribute': ENT + 'hasJSON', 'kind': 'JsonProperty',
                                      'entityType': ENT + 'Cutter'}]


def test_the_forms_find_the_same_on_real_data(corpus):
    """The explicit form validation accepts, and the [ … ] form the fix writes,
    agree on what violates -- in the case where the constraint fires."""
    from semforge.cooked import sparqlbench as sb

    cutter = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'
    case = 'test_StateOnCutterShape/bad/filter-off.jsonld'
    saved = sb.holders(corpus, cutter)[0]['query']
    explicit = saved.replace('$this iffBaseEntities:hasState [ ngsild:hasValue ?v1 ]',
                             '$this iffBaseEntities:hasState ?s1 . ?s1 ngsild:hasValue ?v1')
    assert explicit != saved
    assert [f.code for f in _ngsi(explicit, terms_for(corpus))] == ['explicit-node']
    assert sb.run_query(corpus, cutter, 0, case, explicit)['violating'] == \
        sb.run_query(corpus, cutter, 0, case, saved)['violating'] == ['urn:plasmacutter:1']


# --- completion inside [ … ] -----------------------------------------------------------------------

def _labels(text, terms):
    return [i['label'] for i in complete(text, len(text), terms)]


def test_inside_a_property_the_value_comes_first(terms):
    labels = _labels(HEAD + 'SELECT $this WHERE { $this iffBaseEntities:hasState [ ', terms)
    assert labels[:4] == ['ngsild:hasValue ?state', 'ngsild:observedAt ?observedAt',
                          'ngsild:datasetId ?datasetId', 'ngsild:unitCode ?unit']
    assert 'iffBaseEntities:hasXXXWorkpiece [ ngsild:hasObject ?xXXWorkpiece ]' in labels


def test_inside_a_relationship_the_target_comes_first(terms):
    text = HEAD + 'SELECT $this WHERE { $this iffBaseEntities:hasFilter [ '
    items = complete(text, len(text), terms)
    labels = [i['label'] for i in items]
    assert labels[0] == 'ngsild:hasObject ?filter' and 'ngsild:unitCode ?unit' not in labels
    assert items[0]['insert'] == 'ngsild:hasObject ${1:?filter}'
    assert any(label.startswith('iffBaseEntities:hasTrust [') for label in labels)


def test_after_a_semicolon_inside_and_with_ngsild_undeclared(terms):
    text = (f'PREFIX iffBaseEntities: <{ENT}>\n'
            'SELECT $this WHERE { $this iffBaseEntities:hasState [ ngsild:hasValue ?s ; ')
    items = complete(text, len(text), terms)
    assert items[0]['label'] == 'ngsild:hasValue ?state'
    assert items[0]['edits'][0][2] == 'PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>\n'


def test_the_new_kinds_complete_their_own_payload(terms):
    lang = Term(ENT + 'hasLabel', 'hasLabel', 'attribute', 'LanguageProperty', '',
                'LanguageProperty', ENT + 'Machine')
    vocab = Term(ENT + 'hasColour', 'hasColour', 'attribute', 'VocabProperty', '',
                 'VocabProperty', ENT + 'Machine')
    listed = Term(ENT + 'hasParts', 'hasParts', 'attribute', 'ListRelationship', '',
                  'ListRelationship', ENT + 'Machine')
    for term, payload in ((lang, 'hasLanguageMap'), (vocab, 'hasVocab'),
                          (listed, 'hasObjectList')):
        terms.terms[term.iri] = term
        try:
            labels = _labels(HEAD + f'SELECT $this WHERE {{ $this iffBaseEntities:{term.local} [ ',
                             terms)
            assert labels[0].startswith(f'ngsild:{payload} ?'), labels[:3]
            wrong = _ngsi(HEAD + f'SELECT $this WHERE {{ $this iffBaseEntities:{term.local} '
                          '[ ngsild:hasValue ?x ] }', terms)
            assert ('wrong-layer', {'replace': f'ngsild:{payload}'}) in \
                [(f.code, f.data) for f in wrong]
        finally:
            del terms.terms[term.iri]


# --- hover, and attribute instances shown by what they hold ----------------------------------------

def test_hover_says_the_form_and_what_flink_knows(terms):
    text = HEAD + ('SELECT * { ?x iffBaseEntities:hasState ?a . ?m iffFilterKnowledge:hasWasteclass ?w .'
                   ' ?x iffBaseEntities:hasJSON ?j }')
    state = hover(text, text.index('hasState') + 2, terms)
    assert 'hasState [ ngsild:hasValue ?state ]' in state
    assert 'Sub-attributes: `hasXXXWorkpiece`' in state and 'shacl2flink' not in state
    assert 'A plain property' in hover(text, text.index('hasWasteclass') + 2, terms)
    assert 'shacl2flink would read it as a plain triple' in \
        hover(text, text.index('hasJSON') + 2, terms)


def test_inspect_shows_an_instance_by_what_it_holds(corpus):
    from semforge.cooked import sparqlbench as sb

    cutter = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'
    result = sb.inspect(corpus, cutter, 0, sb.MAIN, HEAD + 'SELECT $this ?a WHERE { '
                        '$this iffBaseEntities:hasState ?a }')
    values = {row['values']['a'] for f in result['focus'] for row in f['rows']}
    assert values == {'[hasValue base:state_PROCESSING]'}


# --- the server keeps open queries current ------------------------------------------------------------

def test_a_package_change_rechecks_open_queries(corpus_path):
    from unittest import mock

    from semforge.editor import server

    uri = _uri(corpus_path)
    ls = mock.MagicMock()
    ls.workspace.text_documents = {uri: None, 'file:///x.ttl': None}
    with mock.patch.object(server, '_publish_query') as publish:
        server._republish_queries(ls)
    assert publish.call_args_list == [mock.call(ls, uri)]


def test_a_lone_instance_variable_is_read_first_and_tested_second(corpus_path):
    """`$this ex:hasFilter ?filter .` -- read as the target, the variable kept;
    `[ ]` (only "it is there") is the second fix."""
    from semforge.editor import server
    from semforge.editor.sparqldocs import code_actions, context, diagnostics

    uri = _uri(corpus_path)
    ctx = context(uri, server._package_for, server.package_root, server._uri_to_path)
    text = HEAD + 'SELECT $this WHERE {\n    $this iffBaseEntities:hasFilter ?filter .\n}\n'
    found = [d for d in diagnostics(text, ctx) if d.code == 'variable-node']
    assert 'to read its target: iffBaseEntities:hasFilter [ ngsild:hasObject ?filter ]' in \
        found[0].message
    params = types.CodeActionParams(
        text_document=types.TextDocumentIdentifier(uri=uri), range=found[0].range,
        context=types.CodeActionContext(diagnostics=found))
    first, second = [a for a in code_actions(uri, text, ctx, params) if a.diagnostics]
    assert first.title == 'Read the instance: [ ngsild:hasObject ?filter ]' and first.is_preferred
    assert second.title == 'Only test that it is there: [ ]' and not second.is_preferred
    assert 'hasFilter [ ngsild:hasObject ?filter ] .' in _apply(text, first.edit.changes[uri])
