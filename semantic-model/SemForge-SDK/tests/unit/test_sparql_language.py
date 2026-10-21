"""The SPARQL editor's language features: tokens, formatting, diagnostics,
completion, hover, quick fixes -- on the corpus's real queries and terms.

The formatter's promise is checked hardest: on every query of the corpus it
must keep every code token (keywords compared without case) and every
comment, and formatting twice must change nothing.
"""

import base64
import json

import pytest
from rdflib.namespace import SH

from semforge.sparql import lexer
from semforge.sparql.check import check
from semforge.sparql.complete import complete, hover
from semforge.sparql.format import FormatError, _check, format_query
from semforge.sparql.terms import terms_for

ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
NGSILD = 'https://uri.etsi.org/ngsi-ld/'
HEAD = (f'PREFIX iffBaseEntities: <{ENT}>\nPREFIX base: <{KNOW}>\n'
        f'PREFIX ngsild: <{NGSILD}>\n')


@pytest.fixture(scope='module')
def terms(corpus):
    return terms_for(corpus)


@pytest.fixture(scope='module')
def queries(corpus):
    return [str(o) for p in (SH.select, SH.construct) for o in corpus.shapes.objects(None, p)]


# --- tokens ----------------------------------------------------------------------------------

def test_tokens_give_the_text_back_exactly(queries):
    for query in queries:
        found = lexer.tokens(query)
        assert ''.join(t.text for t in found) == query
        assert not [t for t in found if t.kind == 'error']


@pytest.mark.parametrize('text, kinds', [
    ('?x $this', ['var', 'var']),
    ('ex:a.b ex:c.', ['pname', 'pname', 'op']),
    ('"a\\"b" """x\ny""" \'c\'', ['string', 'string', 'string']),
    ('<urn:x> ?a<?b', ['iri', 'var', 'op', 'var']),
    ('"5"^^xsd:int "x"@en-GB', ['string', 'op', 'pname', 'string', 'lang']),
    ('1.5 .5 2e3 7', ['number', 'number', 'number', 'number']),
])
def test_what_each_piece_is(text, kinds):
    assert [t.kind for t in lexer.code_tokens(text)] == kinds


def test_prefixes_and_where_a_new_one_goes():
    text = '# about\nPREFIX a: <urn:a/>\nPREFIX b: <urn:b/>\nSELECT * {}'
    assert lexer.declared_prefixes(text) == {'a': 'urn:a/', 'b': 'urn:b/'}
    assert text[lexer.prologue_end(text):].startswith('SELECT')
    assert lexer.prologue_end('# c\nSELECT * {}') == len('# c\n')


# --- formatting --------------------------------------------------------------------------------

def test_every_corpus_query_formats_to_a_fixed_point(queries):
    for query in queries:
        once = format_query(query)
        assert format_query(once) == once


def test_the_layout_depends_on_the_query_not_on_its_spacing(queries):
    """Squash every space and line break (the comments, which end at a line
    break, are taken out first): the layout must come out the same -- but for
    the blank lines an author left between statements, which are kept."""
    def lines(text):
        return [line for line in format_query(text).splitlines() if line.strip()]

    for query in queries:
        plain = ''.join(t.text for t in lexer.tokens(query) if t.kind != 'comment')
        squashed = ''.join(' ' if t.kind == 'space' else t.text for t in lexer.tokens(plain))
        assert lines(squashed) == lines(plain), query[:80]


def test_the_layout(queries):
    stated = next(q for q in queries if 'base:state_PROCESSING && ?v2' in q)
    assert format_query(stated).splitlines()[-7:] == [
        'SELECT $this ?v1 ?f ?v2',
        'WHERE {',
        '    $this iffBaseEntities:hasState [ ngsild:hasValue ?v1 ] .',
        '    $this iffBaseEntities:hasFilter [ ngsild:hasObject ?f ] .',
        '    ?f iffBaseEntities:hasState [ ngsild:hasValue ?v2 ] .',
        '    FILTER(?v1 = base:state_PROCESSING && ?v2 != base:state_ON)',
        '}']


def test_a_squashed_query_is_laid_out(queries):
    squashed = (HEAD + 'select $this where{$this iffBaseEntities:hasState [ngsild:hasValue ?v];'
                'iffBaseEntities:hasFilter ?f.optional{?f a ?t}filter(?v!=base:state_ON)}')
    assert format_query(squashed).split('\n', 3)[3] == (
        '\nSELECT $this\n'
        'WHERE {\n'
        '    $this iffBaseEntities:hasState [ ngsild:hasValue ?v ] ;\n'
        '        iffBaseEntities:hasFilter ?f .\n'
        '    OPTIONAL {\n'
        '        ?f a ?t\n'
        '    }\n'
        '    FILTER(?v != base:state_ON)\n'
        '}\n')


def test_comments_stay_where_they_were():
    text = HEAD + '# why\nSELECT $this WHERE {\n  $this ?p ?o . # each\n\n  # then\n  ?o ?q ?r .\n}'
    out = format_query(text)
    assert '# why\nSELECT' in out
    assert '    $this ?p ?o .  # each' in out
    assert '\n\n    # then\n    ?o ?q ?r .' in out


def test_the_check_refuses_a_layout_that_changes_a_token():
    with pytest.raises(FormatError, match='would change the query'):
        _check('SELECT ?a WHERE { ?a ?b ?c }', 'SELECT ?a WHERE { ?a ?b ?d }')
    with pytest.raises(FormatError, match='lose a comment'):
        _check('SELECT * {} # x', 'SELECT * {}')


# --- diagnostics ------------------------------------------------------------------------------

def _findings(text, terms, **kw):
    return [(f.code, text[f.start:f.end], f.message, f.data) for f in check(text, terms, **kw)]


def test_the_corpus_constraints_are_clean(corpus, terms):
    for query in [str(o) for o in corpus.shapes.objects(None, SH.select)]:
        assert check(query, terms) == []


def test_a_typo_in_a_term_says_what_was_meant(terms):
    (found,) = _findings(HEAD + 'SELECT $this WHERE { $this iffBaseEntities:hasStat ?x }', terms)
    assert found[:2] == ('undeclared-term', 'iffBaseEntities:hasStat')
    assert 'did you mean iffBaseEntities:hasState?' in found[2]
    assert found[3] == {'replace': 'iffBaseEntities:hasState'}


def test_an_undeclared_prefix_offers_its_namespace(terms):
    (found,) = _findings('SELECT $this WHERE { $this base:x ?y }', terms)
    assert found[:2] == ('undeclared-prefix', 'base:')
    assert found[3] == {'prefix': 'base', 'namespace': KNOW}
    (unknown,) = _findings('SELECT $this WHERE { $this nope:x ?y }', terms)
    assert 'knows no namespace by that name' in unknown[2]


def test_the_wrong_ngsild_layer_is_caught(terms):
    found = _findings(HEAD + 'SELECT $this WHERE { $this iffBaseEntities:hasCartridge '
                      '[ ngsild:hasValue ?c ] . $this iffBaseEntities:hasState '
                      '[ ngsild:hasObject ?s ] }', terms)
    assert [(f[0], f[1], f[3]) for f in found] == [
        ('wrong-layer', 'ngsild:hasValue', {'replace': 'ngsild:hasObject'}),
        ('wrong-layer', 'ngsild:hasObject', {'replace': 'ngsild:hasValue'})]
    assert 'hasCartridge is a Relationship' in found[0][2]


@pytest.mark.parametrize('body, code, at', [
    ('SELECT $this WHERE { $this ?p ?o MINUS { $this a ?t } }', 'not-allowed', 'MINUS'),
    ('SELECT (1 AS ?this) WHERE { }', 'not-allowed', 'AS ?this'),
    ('SELECT ?x WHERE { ?x ?p ?o }', 'no-this', 'SELECT'),
    ('SELECT $this (COUNT(?o) AS ?n) WHERE { $this ?p ?o } GROUP BY $this',
     'aggregate-current', 'COUNT'),
])
def test_what_shacl_refuses_or_reads_differently(terms, body, code, at):
    found = _findings(body, terms)
    assert (code, at) in [(f[0], f[1]) for f in found], found


def test_a_rule_must_construct(terms):
    found = _findings('SELECT $this WHERE { $this ?p ?o }', terms, kind='rule')
    assert ('query-form', 'SELECT') in [(f[0], f[1]) for f in found]


@pytest.mark.parametrize('body, at, says', [
    ('SELECT $this WHERE { $this ?p ?o FILTER((?o = 1) }', '}', 'does not close "("'),
    ('SELECT $this WHERE { $this ?p ?o ', '{', 'never closed'),
    ('SELECT $this WHERE { $this ?p ?o ] }', ']', 'does not close "{"'),
])
def test_a_bracket_out_of_place_is_pointed_at(terms, body, at, says):
    (found,) = [f for f in _findings(body, terms) if f[0] == 'syntax']
    assert found[1] == at and says in found[2]


def test_a_syntax_error_is_where_the_parser_says(terms):
    text = 'SELECT $this WHERE { $this ?p ?o . FILTER(?o = = 1) }'
    (found,) = [f for f in check(text, terms) if f.code == 'syntax']
    # rdflib stops at the start of the clause it could not read: the FILTER.
    assert found.start >= text.index('FILTER')
    assert 'cannot be read from "FILTER" on' in found.message


# --- completion -----------------------------------------------------------------------------------

def _labels(text, terms, offset=None):
    return [i['label'] for i in complete(text, len(text) if offset is None else offset, terms)]


def test_after_prefix_the_namespaces(terms):
    labels = _labels('PREFIX ', terms)
    assert 'iffBaseEntities:' in labels and 'ngsild:' in labels
    item = next(i for i in complete('PREFIX ', 7, terms) if i['label'] == 'base:')
    assert item['insert'] == f'base: <{KNOW}>'


def test_a_namespace_offers_its_terms_and_declares_itself(terms):
    text = f'PREFIX ngsild: <{NGSILD}>\nSELECT $this WHERE {{\n  $this iffBaseEntities:has'
    items = complete(text, len(text), terms)
    state = next(i for i in items if i['label'] == 'iffBaseEntities:hasState')
    assert state['detail'] == 'Property · on iffBaseEntities:Machine'
    assert state['edits'] == [(len(f'PREFIX ngsild: <{NGSILD}>\n'),) * 2 +
                              (f'PREFIX iffBaseEntities: <{ENT}>\n',)]
    step = next(i for i in items if i['label'].startswith('iffBaseEntities:hasCartridge ['))
    assert step['insert'] == 'iffBaseEntities:hasCartridge [ ngsild:hasObject ${1:?cartridge} ]'
    assert step['snippet'] and step['filter'] == 'iffBaseEntities:hasCartridge'


def test_the_ngsild_step_is_offered_only_where_a_predicate_goes(terms):
    text = HEAD + 'SELECT $this WHERE { ?x a iffBaseEntities:Cut'
    assert not any(' [' in label for label in _labels(text, terms))
    assert 'iffBaseEntities:Cutter' in _labels(text, terms)


def test_variables_and_keywords(terms):
    text = 'SELECT $this ?value WHERE { $this ?p ?value FILTER(?'
    assert _labels(text, terms) == ['?p', '?this', '?value']
    assert 'FILTER' in _labels('SELECT * WHERE { FIL', terms)
    func = next(i for i in complete('SELECT * { FILTER(STRST', 23, terms)
                if i['label'] == 'STRSTARTS()')
    assert func['insert'] == 'STRSTARTS($1)' and func['snippet']


def test_a_bare_word_offers_prefixes_that_declare_themselves(terms):
    item = next(i for i in complete('SELECT * { ?x iffBase', 21, terms)
                if i['label'] == 'iffBaseEntities:')
    assert item['retrigger'] and item['edits'][0][2] == f'PREFIX iffBaseEntities: <{ENT}>\n'


# --- hover ------------------------------------------------------------------------------------------

def test_hover_says_what_a_name_is(terms):
    text = HEAD + 'SELECT * { ?f iffBaseEntities:hasCartridge ?c . ?f ?p base:state_ON . ?x ?y <urn:z> }'
    said = hover(text, text.index('hasCartridge') + 2, terms)
    assert said.startswith('**hasCartridge** · Relationship · on iffBaseEntities:Filter')
    assert f'`<{ENT}hasCartridge>`' in said and 'ngsild:hasObject' in said
    assert 'an individual of MachineState' in hover(text, text.index('state_ON') + 2, terms)
    assert 'outside this package' in hover(text, text.index('urn:z') + 1, terms)
    assert hover('SELECT $this {}', 9, terms).startswith('**$this**')


# --- the LSP side: document references, ranges, quick fixes --------------------------------------

def _uri(package_path, shape, holder=0, kind='constraint'):
    ref = {'p': f'file://{package_path}/shacl.ttl', 's': shape, 'h': holder, 'k': kind}
    return 'semforge-sparql:/X.rq?' + base64.urlsafe_b64encode(
        json.dumps(ref).encode()).decode().rstrip('=')


def test_a_query_document_names_its_query(corpus_path):
    from semforge.editor.sparqldocs import is_query, reference

    uri = _uri(corpus_path, ENT + 'x', 2, 'rule')
    assert is_query(uri) and not is_query('file:///x.ttl')
    assert reference(uri) == {'package': f'file://{corpus_path}/shacl.ttl', 'shape': ENT + 'x',
                              'holder': 2, 'kind': 'rule'}


def _context(corpus_path):
    from semforge.editor import server
    from semforge.editor.sparqldocs import context

    shape = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'
    uri = _uri(corpus_path, shape)
    return uri, context(uri, server._package_for, server.package_root, server._uri_to_path)


def test_diagnostics_carry_their_range_and_fix(corpus_path):
    from semforge.editor.sparqldocs import diagnostics

    _, ctx = _context(corpus_path)
    text = 'SELECT $this\nWHERE { $this base:x ?y }'
    (found,) = diagnostics(text, ctx)
    assert (found.range.start.line, found.range.start.character) == (1, 14)
    assert (found.range.end.line, found.range.end.character) == (1, 19)
    assert found.data['code'] == 'undeclared-prefix' and found.data['namespace'] == KNOW


def test_quick_fixes_add_the_prefix_and_correct_the_term(corpus_path):
    from lsprotocol import types

    from semforge.editor.sparqldocs import code_actions, diagnostics

    uri, ctx = _context(corpus_path)
    text = 'SELECT $this\nWHERE { $this base:x ?y }'
    found = diagnostics(text, ctx)
    params = types.CodeActionParams(
        text_document=types.TextDocumentIdentifier(uri=uri), range=found[0].range,
        context=types.CodeActionContext(diagnostics=found))
    actions = code_actions(uri, text, ctx, params)
    add = actions[0]
    assert add.title == f'Add PREFIX base: <{KNOW}>'
    assert add.edit.changes[uri][0].new_text == f'PREFIX base: <{KNOW}>\n'
    written = [a for a in actions if a.title.startswith('Write out as')]
    assert written and written[0].edit.changes[uri][0].new_text == f'<{KNOW}x>'


def test_an_iri_can_be_shortened_and_its_prefix_declared(corpus_path):
    from lsprotocol import types

    from semforge.editor.sparqldocs import code_actions

    uri, ctx = _context(corpus_path)
    text = f'SELECT $this WHERE {{ $this <{ENT}hasState> ?y }}'
    at = text.index('<') + 3
    params = types.CodeActionParams(
        text_document=types.TextDocumentIdentifier(uri=uri),
        range=types.Range(types.Position(0, at), types.Position(0, at)),
        context=types.CodeActionContext(diagnostics=[]))
    (action,) = code_actions(uri, text, ctx, params)
    assert action.title == 'Shorten to iffBaseEntities:hasState'
    edits = action.edit.changes[uri]
    assert [e.new_text for e in edits] == [f'PREFIX iffBaseEntities: <{ENT}>\n',
                                           'iffBaseEntities:hasState']


def test_completion_and_formatting_as_lsp(corpus_path):
    from lsprotocol import types

    from semforge.editor.sparqldocs import completion, formatting

    _, ctx = _context(corpus_path)
    text = f'PREFIX ngsild: <{NGSILD}>\nSELECT $this WHERE {{ $this iffBaseEntities:hasSt'
    found = completion(text, len(text), ctx)
    item = next(i for i in found.items if i.label == 'iffBaseEntities:hasState')
    assert item.kind == types.CompletionItemKind.Property
    assert item.text_edit.new_text == 'iffBaseEntities:hasState'
    assert item.additional_text_edits[0].new_text.startswith('PREFIX iffBaseEntities:')
    edits = formatting('select $this where{$this ?p ?o}')
    assert edits[0].new_text == 'SELECT $this\nWHERE {\n    $this ?p ?o\n}\n'
    assert formatting(edits[0].new_text) == []
