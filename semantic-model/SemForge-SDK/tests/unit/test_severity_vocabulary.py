"""sh:Severity in the Vocabulary view and on its own page -- where a package
sees SHACL's three levels and extends them.

SHACL declares the class and its levels, not the package, so they are shown
read-only, never "unused"; + Value adds a level in the package's namespace;
a class derived from sh:Severity sits under it and derives further classes
from its page. Run on copies of the kms corpus.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF, SH

from semforge.cooked.knowledge import build_knowledge
from semforge.cooked.severity import add_class
from semforge.cooked.vocabulary import add_value, build_vocabulary_page
from semforge.package import load

KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _severity_node(package):
    group = next(r for r in build_knowledge(package) if r.label == 'Vocabulary classes')
    return group.children[0]


def test_the_vocabulary_view_shows_sh_severity_and_its_levels(kms):
    node = _severity_node(load(str(kms)))
    assert (node.kind, node.label, node.iri) == ('class', 'sh:Severity', str(SH.Severity))
    assert [(c.label, c.detail) for c in node.children] == [
        ('Violation', 'violation · SHACL · the default'),
        ('Warning', 'warning · SHACL'), ('Info', 'info · SHACL')]


def test_a_derived_class_sits_under_it_not_at_the_top(kms):
    add_class(load(str(kms)), 'AlarmLevel')
    package = load(str(kms))
    node = _severity_node(package)
    assert 'AlarmLevel' in [c.label.split(':')[-1] for c in node.children if c.kind == 'class']
    group = next(r for r in build_knowledge(package) if r.label == 'Vocabulary classes')
    assert 'AlarmLevel' not in [c.label.split(':')[-1] for c in group.children[1:]]


def test_its_page_shows_shacl_s_levels_read_only_and_never_unused(kms):
    page = build_vocabulary_page(load(str(kms)), 'sh:Severity')
    assert page['term'] == 'sh:Severity' and page['severity'] and page['builtin']
    assert [(r['term'], r['label'], r['builtin']) for r in page['values']] == [
        ('sh:Violation', 'violation', True), ('sh:Warning', 'warning', True),
        ('sh:Info', 'info', True)]
    assert page['summary']['unused'] == 0, 'not naming one of SHACL\'s levels is no gap'
    assert {d['shapeName'] for d in page['constrainedBy']} == {
        'iffBaseShacl:StateOnCutterShape', 'iffBaseShacl:StateOnFilterShape'}


def test_plus_value_on_it_adds_a_level_in_the_package_s_namespace(kms):
    made = add_value(load(str(kms)), 'sh:Severity', 'severityMajor', 'major')
    assert not made['iri'].startswith(str(SH)), made['iri']
    package = load(str(kms))
    assert (URIRef(made['iri']), RDF.type, SH.Severity) in package.knowledge
    page = build_vocabulary_page(package, 'sh:Severity')
    assert [r['label'] for r in page['values'] if not r.get('builtin')] == ['major']


def test_a_derived_class_s_page_can_derive_further(kms):
    made = add_class(load(str(kms)), 'AlarmLevel')
    page = build_vocabulary_page(load(str(kms)), made['iri'])
    assert page['severity'] is True
    plain = build_vocabulary_page(load(str(kms)), KNOW + 'MachineState')
    assert plain['severity'] is False


# --- the page in the extension ----------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')


def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _open(tmp_path, page, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openVocabularyPage',
        'node': {'raw': {'kind': 'class', 'iri': str(SH.Severity), 'label': 'sh:Severity',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/vocabularyPage': page}}, **scenario))


def test_the_page_renders_shacl_s_levels_without_edits(tmp_path, kms):
    page = dict(build_vocabulary_page(load(str(kms)), 'sh:Severity'), ok=True)
    html = _open(tmp_path, page)['webviews'][0]['html'][-1]
    rows = html.split('<tbody>', 1)[1].split('</tbody>', 1)[0]
    assert rows.count('>SHACL</span>') == 3
    assert 'data-action="label"' not in rows and 'data-action="rowMenu"' not in rows
    assert 'the default of every constraint that names none' in rows
    assert 'class="chip warn"' not in rows, 'no yellow "unused" for SHACL\'s own'


def test_deriving_a_class_from_the_page(tmp_path, kms):
    page = dict(build_vocabulary_page(load(str(kms)), 'sh:Severity'), ok=True)
    seen = _open(tmp_path, page, webviewMessages=[{'command': 'pageMenu', 'row': -1}],
                 picks=['$(type-hierarchy-sub) New severity class derived from Severity…'],
                 inputs=['AlarmLevel'])
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addSeverityClass']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'name': 'AlarmLevel',
                      'parent': 'sh:Severity', 'namespace': None}]
