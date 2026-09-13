"""A role is one file or a directory of them.

A model outgrows one file long before it outgrows one package, and splitting it
should not mean inventing a second package or a build step that concatenates.
The graph is the union either way -- what changes is where an edit lands, which
is the whole risk: writing a constraint into the role's FIRST file because that
is what `sources[role]` used to mean would put it in the wrong document.

So these compare a split package against the single-file one it was made from,
and check that every write goes to the file that holds the subject.
"""

import hashlib
import json
import os
import shutil

import pytest
from rdflib.compare import to_isomorphic

from semforge.errors import PackageError
from semforge.package import load
from semforge.rdfio import index_file
from semforge.validate import validate_package


def _split(source, target):
    """The corpus, cut into `shacl/` and `model-instance/` directories."""
    shutil.copytree(source, target, symlinks=False)

    shapes = os.path.join(target, 'shacl.ttl')
    text = open(shapes, encoding='utf-8').read()
    index = index_file(shapes)
    header = text[:index.blocks[0].start]
    half = len(index.blocks) // 2
    os.remove(shapes)
    os.makedirs(os.path.join(target, 'shacl'))
    for name, chunk in (
            ('a-core.ttl',
             header + text[index.blocks[0].start:index.blocks[half].start]),
            ('b-rest.ttl', header + text[index.blocks[half].start:])):
        with open(os.path.join(target, 'shacl', name), 'w',
                  encoding='utf-8') as handle:
            handle.write(chunk)

    model = os.path.join(target, 'model-instance.jsonld')
    entities = json.load(open(model, encoding='utf-8'))
    os.remove(model)
    os.makedirs(os.path.join(target, 'model-instance'))
    for position, entity in enumerate(entities):
        name = str(entity.get('id', f'e{position}')).replace(':', '_') + '.jsonld'
        with open(os.path.join(target, 'model-instance', name), 'w',
                  encoding='utf-8') as handle:
            json.dump([entity], handle, indent=2)
    return target


@pytest.fixture
def split(tmp_path, corpus):
    return load(_split(corpus.path, str(tmp_path / 'pkg')))


def _digest(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


# --- loading -------------------------------------------------------------------

def test_a_directory_loads_to_the_same_graphs(split, corpus):
    assert len(split.files('shapes')) == 2
    assert len(split.files('model')) > 1
    assert len(split.files('knowledge')) == 1, 'knowledge was left as one file'

    for role in ('shapes', 'knowledge', 'model'):
        assert to_isomorphic(getattr(split, role)) == \
            to_isomorphic(getattr(corpus, role)), role


def test_the_same_package_validates_the_same(split, corpus):
    def verdicts(package):
        report = validate_package(package, strict=False)
        return sorted((r.shape, r.component, r.resource)
                      for r in report.violations)

    assert verdicts(split) == verdicts(corpus)
    assert verdicts(split), 'the corpus should still violate something'


def test_an_empty_role_directory_says_so(tmp_path, corpus):
    target = _split(corpus.path, str(tmp_path / 'pkg'))
    for name in os.listdir(os.path.join(target, 'shacl')):
        os.remove(os.path.join(target, 'shacl', name))

    with pytest.raises(PackageError) as raised:
        load(target)
    assert 'holds no .ttl file' in str(raised.value)


def test_a_missing_role_offers_the_directory(tmp_path):
    (tmp_path / 'empty').mkdir()
    with pytest.raises(PackageError) as raised:
        load(str(tmp_path / 'empty'))
    message = str(raised.value)
    assert 'shacl.ttl' in message and 'a directory named shacl' in message


def test_a_file_wins_over_a_directory_of_the_same_role(tmp_path, corpus):
    """Both present is ambiguous; the file is the older, explicit answer."""
    target = _split(corpus.path, str(tmp_path / 'pkg'))
    shutil.copy(os.path.join(target, 'shacl', 'a-core.ttl'),
                os.path.join(target, 'shacl.ttl'))
    package = load(target)
    assert package.files('shapes') == [os.path.join(target, 'shacl.ttl')]


# --- where an edit lands -------------------------------------------------------

def test_a_constraint_edit_lands_in_the_file_holding_the_shape(split):
    from semforge.cooked import build_tree
    from semforge.cooked.tree import apply_edit, flatten

    second = split.files('shapes')[1]
    in_second = {block.subject
                 for block in split.index('shapes').indexes[second].blocks}
    before = {path: _digest(path) for path in split.files('shapes')}

    node = next(n for _, n in flatten(build_tree(split))
                if n.shape in in_second and n.parameter and n.editable)
    path, _ = apply_edit(split, node.shape, list(node.path_chain),
                         node.parameter, '3')
    assert path == second, 'the edit went to the wrong document'
    assert _digest(split.files('shapes')[0]) == before[split.files('shapes')[0]]


def test_adding_a_property_shape_lands_where_the_shape_is(split):
    from semforge.cooked.shapelink import ensure_property_shape

    found, how = ensure_property_shape(split, 'iffBaseEntities:Filter',
                                       'iffBaseEntities:hasNewThing')
    assert how == 'created'
    assert found['file'] in split.files('shapes')
    holder = open(found['file'], encoding='utf-8').read()
    assert 'hasNewThing' in holder
    others = [p for p in split.files('shapes') if p != found['file']]
    assert all('hasNewThing' not in open(p, encoding='utf-8').read()
               for p in others)


def test_a_value_edit_lands_in_its_own_model_document(split):
    from semforge.cooked.examples import build_suite, flatten, set_value

    before = {path: _digest(path) for path in split.files('model')}
    # From the model directory specifically: the same entity appears in the
    # example cases too, and each row edits ITS OWN file.
    row = next(n for _, n in flatten(build_suite(split))
               if n.kind == 'attribute' and n.editable
               and n.entity == 'urn:filter:1' and n.label == 'hasStrength'
               and n.file in split.files('model'))
    where, _, new = set_value(split, row.entity, row.path, '0.55',
                              file=row.file)
    assert where in split.files('model')
    assert new == '0.55'
    changed = [p for p in before if _digest(p) != before[p]]
    assert changed == [where], changed


# --- what the views say --------------------------------------------------------

def test_the_shape_jump_names_the_file_it_is_in(split):
    from semforge.cooked.shapelink import find_property_shape

    found = find_property_shape(split, 'iffBaseEntities:Filter', 'hasStrength')
    assert found['file'] in split.files('shapes')
    assert os.path.dirname(found['file']).endswith('shacl')
    line = open(found['file'], encoding='utf-8').read().splitlines()[
        found['line'] - 1]
    assert 'sh:property' in line


def test_every_model_document_is_its_own_scratchpad_root(split):
    from semforge.cooked.examples import build_suite

    roots = [n for n in build_suite(split) if 'scratchpad' in n.detail]
    assert len(roots) == len(split.files('model'))
    assert all(n.label.startswith('model-instance/') for n in roots)
    # And the declared examples are still there beside them.
    assert [n for n in build_suite(split) if n.kind == 'suite']


def test_a_finding_lands_on_the_file_that_declares_the_shape(split):
    from semforge.editor.analysis import analyse

    findings, _ = analyse(split.path)
    shapes = {os.path.abspath(p) for p in split.files('shapes')}
    assert shapes <= set(findings), 'a shapes file got no entry at all'
    index = split.index('shapes')
    for path, items in findings.items():
        for finding in items:
            if finding.kind in ('identity',) or not finding.subject:
                continue
            holder = index.file_for(finding.subject)
            if holder:
                assert os.path.abspath(holder) == path, \
                    f'{finding.subject} reported against the wrong file'


def test_export_merges_the_documents_into_one_artifact(split, tmp_path):
    """What a package looks like is the author's business; what a compiler is
    handed is the target's."""
    from semforge.target.export import export

    out = tmp_path / 'out'
    written = export(split, str(out))
    assert written.get('merged', {}).get('shapes') == 2
    shapes = open(written['shapes'], encoding='utf-8').read()
    for path in split.files('shapes'):
        body = open(path, encoding='utf-8').read()
        statement = [line for line in body.splitlines()
                     if line and not line.startswith(('@', '#'))][0]
        assert statement in shapes

    model = json.load(open(written['model'], encoding='utf-8'))
    total = sum(len(json.load(open(p, encoding='utf-8')))
                for p in split.files('model'))
    assert len(model) == total


def test_prefixes_and_identity_see_every_document(split):
    from semforge.expect.identity import example_files
    from semforge.package.prefixes import check

    files = example_files(split)
    assert all(document in files for document in split.files('model'))
    assert check(split) == check(split), 'the check is not deterministic'


# --- being found at all --------------------------------------------------------

def test_a_directory_package_is_recognised_by_the_server(split):
    from semforge.editor.analysis import package_root

    for document in split.files('shapes') + split.files('model'):
        assert package_root(document) == os.path.abspath(split.path)
    assert package_root(os.path.join(split.path, 'shacl')) == \
        os.path.abspath(split.path)


def test_a_directory_package_is_recognised_by_the_extension(split, tmp_path):
    """Otherwise the trees sit empty over a package the server reads fine."""
    import json
    import shutil
    import subprocess

    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')

    sdk = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    scenario = tmp_path / 'locate.json'
    scenario.write_text(json.dumps({'mode': 'locate'}))
    result = subprocess.run(
        [node, os.path.join(sdk, 'tests', 'harness', 'drive.js'),
         split.path, os.path.join(sdk, 'vscode', 'src', 'locate.js'),
         str(scenario)],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-800:]
    found = json.loads(result.stdout.strip().splitlines()[-1])['locate']['uri']
    assert found, 'the extension would show "no package found"'
    assert package_of(found) == os.path.abspath(split.path)


def package_of(uri):
    from semforge.editor.analysis import package_root

    return package_root(uri[len('file://'):])
