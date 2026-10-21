"""M6: find-references, the other half of cross-artifact navigation.

The acceptance criterion is the one in implementation-plan.md: from the
owl:ObjectProperty in knowledge.ttl to every corpus example exercising it. The
examples are found here by an independent scan of the files on disk rather than
by asking the package which ones it has, so a case the package forgets to list
fails the test instead of silently shrinking the answer.
"""

import json
import os
import shutil

import pytest

from semforge.editor import references_at
from semforge.editor.references import iris_named, references_to
from semforge.rdfio import terms

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
STRENGTH = BASE + 'base_entities/hasStrength'


def _relative(corpus_path, references):
    return [(os.path.relpath(r.path, corpus_path), r.line) for r in references]


def _files_carrying(corpus_path, text):
    """Every .jsonld under the corpus whose text contains the quoted term."""
    found = set()
    for directory, _, names in os.walk(corpus_path, followlinks=True):
        if '.semforge' in directory.split(os.sep):
            continue
        for name in names:
            if name.endswith('.jsonld') and name != 'context.jsonld':
                path = os.path.join(directory, name)
                with open(path, encoding='utf-8') as handle:
                    if json.dumps(text) in handle.read():
                        found.add(os.path.relpath(path, corpus_path))
    return found


# --- the acceptance criterion -------------------------------------------------

def test_from_the_ontology_to_every_example_exercising_it(corpus, corpus_path):
    knowledge = os.path.join(corpus_path, 'knowledge.ttl')
    found = references_at(corpus, 'iffBaseEntities:hasStrength', knowledge)
    files = {os.path.relpath(r.path, corpus_path) for r in found}

    assert 'shacl.ttl' in files, 'the sh:path that constrains it'
    data = {f for f in files if f.endswith('.jsonld')}
    expected = _files_carrying(corpus_path, 'iffBaseEntities:hasStrength')
    assert expected, 'the corpus no longer exercises hasStrength'
    assert data == expected


def test_the_declaration_is_marked_and_can_be_left_out(corpus, corpus_path):
    knowledge = os.path.join(corpus_path, 'knowledge.ttl')
    every = references_at(corpus, 'iffBaseEntities:hasStrength', knowledge)
    declared = [r for r in every if r.declaration]
    assert [os.path.basename(r.path) for r in declared] == ['knowledge.ttl']

    uses = references_at(corpus, 'iffBaseEntities:hasStrength', knowledge,
                         include_declaration=False)
    assert len(uses) == len(every) - 1
    assert not any(r.declaration for r in uses)


def test_a_sparql_body_is_a_use(corpus, corpus_path):
    """The SELECT that reads an attribute is where a rename most often misses."""
    found = references_to(corpus, {STRENGTH})
    in_shapes = [r for r in found if r.path.endswith('shacl.ttl')]
    with open(os.path.join(corpus_path, 'shacl.ttl'), encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    kinds = {'sh:path' in lines[r.line - 1] for r in in_shapes}
    assert kinds == {True, False}, 'expected both the sh:path and a query use'


def test_a_reference_points_at_the_term_itself(corpus):
    """line/column/length highlight exactly the term, in every file kind."""
    for reference in references_to(corpus, {STRENGTH}):
        with open(reference.path, encoding='utf-8') as handle:
            line = handle.read().split('\n')[reference.line - 1]
        text = line[reference.column:reference.column + reference.length]
        assert text == 'iffBaseEntities:hasStrength', (reference, line)


def test_an_iri_valued_json_ld_value_is_a_use(corpus, corpus_path):
    """{"@id": "base:state_PROCESSING"} names a term exactly as a key does.

    rdflib's Context.expand runs `@id` itself through @vocab, and before that
    was special-cased every vocabulary value in the data was invisible.
    """
    iri = BASE + 'base_knowledge/state_PROCESSING'
    data = {f for f, _ in _relative(corpus_path, references_to(corpus, {iri}))
            if f.endswith('.jsonld')}
    assert data == _files_carrying(corpus_path, 'base:state_PROCESSING')


def test_an_entity_type_reaches_the_entities_of_that_type(corpus, corpus_path):
    iri = BASE + 'base_entities/Plasmacutter'
    data = {f for f, _ in _relative(corpus_path, references_to(corpus, {iri}))
            if f.endswith('.jsonld')}
    assert data == _files_carrying(corpus_path, 'iffBaseEntities:Plasmacutter')


# --- which term the cursor means ----------------------------------------------

def test_the_prefix_decides_between_two_shapes_with_one_name(corpus, corpus_path):
    """The corpus has two CartridgeShapes; the written prefix picks one."""
    shacl = os.path.join(corpus_path, 'shacl.ttl')
    assert iris_named(corpus, 'iffBaseShacl:CartridgeShape', shacl) == {
        BASE + 'base_shacl/CartridgeShape'}
    assert iris_named(corpus, 'iffFilterShacl:CartridgeShape', shacl) == {
        BASE + 'filter_shacl/CartridgeShape'}
    assert len(iris_named(corpus, 'CartridgeShape')) == 2, \
        'a bare name falls back to every term with that local name'


def test_an_expansion_is_trusted_over_a_shared_local_name(corpus):
    """iffBaseEntities:hasObject is not ngsild:hasObject.

    Before, an expansion nothing declared fell back to local-name matching and
    answered with every NGSI-LD relationship in the corpus.
    """
    assert iris_named(corpus, 'iffBaseEntities:hasObject') == {
        BASE + 'base_entities/hasObject'}
    assert references_to(corpus, iris_named(corpus, 'iffBaseEntities:hasObject')) == []


def test_a_json_ld_token_expands_by_that_documents_context(corpus, corpus_path):
    model = os.path.join(corpus_path, 'model-instance.jsonld')
    assert iris_named(corpus, 'iffBaseEntities:hasState', model) == {
        BASE + 'base_entities/hasState'}
    # `object` is the NGSI-LD alias, not a term of this package.
    assert iris_named(corpus, 'object', model) == {
        'https://uri.etsi.org/ngsi-ld/hasObject'}


def test_nothing_under_the_cursor_is_no_references(corpus):
    assert references_at(corpus, '') == []
    assert references_at(corpus, 'NoSuchThingAnywhere') == []


# --- the Turtle term scanner ---------------------------------------------------

def test_terms_skip_comments_but_read_strings():
    source = (
        '@prefix ex: <http://ex.org/> .\n'
        '# ex:commented is not a use\n'
        'ex:a ex:p ex:b .\n'
        'ex:c ex:q """PREFIX q: <http://q.org/> SELECT ?x WHERE { ?x q:r ex:b }""" .\n')
    found = [(t.raw, t.iri, t.line, t.quoted) for t in terms(source)
             if not t.raw.startswith('<')]
    assert ('ex:commented', 'http://ex.org/commented', 2, False) not in found
    assert ('ex:a', 'http://ex.org/a', 3, False) in found
    assert ('q:r', 'http://q.org/r', 4, True) in found, \
        "a query's own PREFIX wins inside it"
    assert ('ex:b', 'http://ex.org/b', 4, True) in found


def test_a_terminating_dot_is_not_part_of_a_name():
    found = [t.raw for t in terms('@prefix ex: <http://ex.org/> .\nex:a ex:p ex:b.c .\n')]
    assert 'ex:b.c' in found
    found = [t.raw for t in terms('@prefix ex: <http://ex.org/> .\nex:a ex:p ex:b.\n')]
    assert 'ex:b' in found


def test_a_url_in_prose_is_not_a_prefixed_name():
    source = '@prefix ex: <http://ex.org/> .\nex:a ex:note "see https://x.org/y" .\n'
    assert all(t.iri != 'https//x.org/y' for t in terms(source))
    assert [t.raw for t in terms(source) if t.quoted] == []


def test_columns_are_zero_based_and_exact():
    source = '@prefix ex: <http://ex.org/> .\n    ex:a ex:p ex:b .\n'
    term = [t for t in terms(source) if t.raw == 'ex:p'][0]
    assert (term.line, term.column) == (2, 9)


# --- a model that is a directory ----------------------------------------------

def test_a_model_directory_is_searched(tmp_path):
    """The model role may be a directory; its documents are data like any other.

    The example lister read the role's source path, which for a directory is
    the directory itself -- opening it failed and was swallowed, so every
    document in it was missing from references and from the Knowledge view.
    """
    from semforge.cooked.knowledge import example_files
    from semforge.package import load
    from semforge.package.scaffold import create_package

    target = tmp_path / 'plant'
    target.mkdir()
    create_package(str(target), name='Plant')
    main = next(p for p in target.rglob('main.jsonld'))
    folder = main.with_suffix('')
    folder.mkdir()
    shutil.move(str(main), str(folder / 'line-a.jsonld'))

    package = load(str(target))
    assert os.path.abspath(str(folder / 'line-a.jsonld')) in \
        [os.path.abspath(p) for p in example_files(package)]


@pytest.mark.parametrize('token', ['iffBaseEntities:hasStrength', 'hasStrength'])
def test_both_spellings_find_the_same_uses(corpus, corpus_path, token):
    shacl = os.path.join(corpus_path, 'shacl.ttl')
    found = references_at(corpus, token, shacl)
    assert len(found) == len(references_to(corpus, {STRENGTH}))
