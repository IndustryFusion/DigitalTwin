"""Which namespace a new vocabulary term goes in -- chosen, not assumed.

Every vocabulary "New …" (class, value, severity level, severity class) takes a
namespace: a prefix or IRI given explicitly, or `prefix:Name` typed as the
name. Without one the term goes where it always did. A namespace the file does
not speak yet gets its `@prefix` line, so a term in a namespace just defined
reads `alerts:Leak`, not `<https://…/Leak>`. Standard vocabularies are never a
place to mint in. Run on copies of the kms corpus.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SH

from semforge.cooked.knowledge import bind_namespace
from semforge.cooked.severity import add_class, add_level
from semforge.cooked.vocabulary import (add_value, add_vocabulary_class,
                                        build_vocabulary_page, vocabulary_namespaces)
from semforge.errors import PackageError
from semforge.package import load
from semforge.package.prefixes import STANDARD, add_namespace

KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
ALERTS = 'https://example.org/alerts/'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


@pytest.fixture
def alerts(kms):
    add_namespace(str(kms), 'alerts', ALERTS)
    return kms


def _text(kms):
    return (kms / 'knowledge.ttl').read_text()


# --- where a term may go ----------------------------------------------------------------

def test_the_usual_place_comes_first_and_no_standard_is_offered(kms):
    spaces = vocabulary_namespaces(load(str(kms)), KNOW + 'MachineState')
    assert spaces[0]['default'] and spaces[0]['namespace'] == KNOW
    assert sum(s['default'] for s in spaces) == 1
    offered = {s['namespace'] for s in spaces}
    assert not offered & set(STANDARD.values())
    held = [s['terms'] for s in spaces[1:]]
    assert held == sorted(held, reverse=True)


def test_a_namespace_just_defined_is_offered(alerts):
    spaces = vocabulary_namespaces(load(str(alerts)))
    assert {'prefix': 'alerts', 'namespace': ALERTS, 'terms': 0,
            'default': False} in spaces


def test_a_level_of_sh_severity_is_never_offered_shacl_s_namespace(kms):
    spaces = vocabulary_namespaces(load(str(kms)), 'sh:Severity')
    assert spaces[0]['default'] and spaces[0]['namespace'] != str(SH)


# --- writing into the chosen one --------------------------------------------------------

def test_a_class_in_a_new_namespace_gets_its_prefix_line(alerts):
    made = add_vocabulary_class(load(str(alerts)), 'Leak', namespace='alerts')
    assert made['iri'] == ALERTS + 'Leak'
    text = _text(alerts)
    assert text.count(f'@prefix alerts: <{ALERTS}> .') == 1
    assert '\nalerts:Leak a owl:Class' in text
    assert '<https://example.org/alerts/Leak>' not in text
    graph = Graph().parse(data=text, format='turtle')
    assert (URIRef(ALERTS + 'Leak'), RDF.type, OWL.Class) in graph
    # The prefix line sits with the others, before the first statement.
    first_statement = text.index('\n', text.rindex('@prefix')) + 1
    assert text.index('@prefix alerts:') < first_statement


def test_prefix_colon_name_chooses_the_namespace_and_the_line_is_added_once(alerts):
    add_vocabulary_class(load(str(alerts)), 'alerts:Leak')
    made = add_value(load(str(alerts)), ALERTS + 'Leak', 'alerts:smallLeak', 'small')
    assert made['iri'] == ALERTS + 'smallLeak'
    text = _text(alerts)
    assert text.count('@prefix alerts:') == 1
    assert 'alerts:smallLeak a owl:NamedIndividual,\n        alerts:Leak' in text


def test_a_value_may_live_outside_its_class_s_namespace(alerts):
    made = add_value(load(str(alerts)), KNOW + 'MachineState', 'state_LEAK',
                     namespace='alerts')
    assert made['iri'] == ALERTS + 'state_LEAK'
    package = load(str(alerts))
    assert (URIRef(made['iri']), RDF.type, URIRef(KNOW + 'MachineState')) in package.knowledge
    page = build_vocabulary_page(package, KNOW + 'MachineState')
    assert ALERTS + 'state_LEAK' in [r['iri'] for r in page['values']]


def test_without_a_namespace_nothing_changes(kms):
    made = add_value(load(str(kms)), KNOW + 'MachineState', 'state_IDLE')
    assert made['iri'] == KNOW + 'state_IDLE'


def test_severity_levels_and_classes_take_one_too(alerts):
    level = add_level(load(str(alerts)), 'sh:Severity', 'severityMajor', 'major',
                      namespace='alerts')
    assert level['iri'] == ALERTS + 'severityMajor'
    cls = add_class(load(str(alerts)), 'alerts:AlarmLevel')
    assert cls['iri'] == ALERTS + 'AlarmLevel'
    via_value = add_value(load(str(alerts)), 'sh:Severity', 'alerts:severityMinor', 'minor')
    assert via_value['iri'] == ALERTS + 'severityMinor'
    package = load(str(alerts))
    assert (URIRef(ALERTS + 'AlarmLevel'), None, SH.Severity) in package.knowledge


@pytest.mark.parametrize('namespace', ['sh', 'owl', str(SH)])
def test_a_standard_vocabulary_is_no_place_to_mint(kms, namespace):
    with pytest.raises(PackageError, match='standard vocabulary'):
        add_value(load(str(kms)), 'sh:Severity', 'severityMajor', namespace=namespace)
    with pytest.raises(PackageError, match='standard vocabulary'):
        add_vocabulary_class(load(str(kms)), 'Leak', namespace=namespace)


def test_an_unknown_prefix_says_where_to_define_it(kms):
    before = _text(kms)
    with pytest.raises(PackageError, match='not a namespace this package knows'):
        add_vocabulary_class(load(str(kms)), 'nowhere:Leak')
    assert _text(kms) == before


def test_a_file_using_the_name_for_something_else_keeps_the_full_iri(alerts):
    path = alerts / 'knowledge.ttl'
    path.write_text('@prefix alerts: <https://elsewhere.org/> .\n' + path.read_text())
    before = path.read_text()
    bind_namespace(load(str(alerts)), str(path), URIRef(ALERTS + 'Leak'))
    assert path.read_text() == before
    made = add_vocabulary_class(load(str(alerts)), 'Leak', namespace='alerts')
    assert f'<{ALERTS}Leak> a owl:Class' in path.read_text()
    assert made['iri'] == ALERTS + 'Leak'


# --- the picker in the extension --------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
SPACES = {'namespaces': [
    {'prefix': 'base', 'namespace': KNOW, 'terms': 17, 'default': True},
    {'prefix': 'material', 'namespace': 'https://x/material/', 'terms': 37, 'default': False},
    {'prefix': 'eclass', 'namespace': 'https://x/eclass#', 'terms': 0, 'default': False}]}


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


def _plus_value(tmp_path, page, **scenario):
    replies = {'semforge/vocabularyPage': page, 'semforge/vocabularyNamespaces': SPACES,
               'semforge/addVocabularyValue': {'ok': True, 'iri': KNOW + 'x'},
               'semforge/addNamespace': {'ok': True, 'prefix': 'alerts',
                                         'namespace': ALERTS, 'file': 'semforge.yaml',
                                         'line': 3}}
    replies.update(scenario.pop('replies', {}))
    return _drive(tmp_path, dict({
        'command': 'semforge.openVocabularyPage',
        'node': {'raw': {'kind': 'class', 'iri': KNOW + 'MachineState',
                         'label': 'MachineState', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'addValue', 'row': -1}],
        'replies': replies}, **scenario))


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


@pytest.fixture
def state_page(kms):
    return dict(build_vocabulary_page(load(str(kms)), KNOW + 'MachineState'), ok=True)


def test_plus_value_offers_the_usual_place_first_and_new_namespace_last(tmp_path, state_page):
    seen = _plus_value(tmp_path, state_page, inputs=['state_LEAK', 'LEAK'], picks=[0])
    pick = next(p for p in seen['quickPicks'] if p['placeHolder'] == 'Enter keeps the usual place')
    labels = [i['label'] for i in pick['items'] if i['label']]
    assert labels[:2] == ['The usual place', 'base:state_LEAK']
    assert labels[-1] == '$(add) New namespace…'
    assert 'eclass:state_LEAK' in labels
    assert _asked(seen, 'semforge/vocabularyNamespaces') == [
        {'uri': 'file:///pkg/shacl.ttl', 'near': KNOW + 'MachineState'}]


def test_enter_keeps_the_usual_place(tmp_path, state_page):
    seen = _plus_value(tmp_path, state_page, inputs=['state_LEAK', 'LEAK'],
                       picks=['base:state_LEAK'])
    assert _asked(seen, 'semforge/addVocabularyValue')[0]['namespace'] is None


def test_another_namespace_is_sent_by_its_prefix(tmp_path, state_page):
    seen = _plus_value(tmp_path, state_page, inputs=['state_LEAK', 'LEAK'],
                       picks=['material:state_LEAK'])
    assert _asked(seen, 'semforge/addVocabularyValue')[0]['namespace'] == 'material'


def test_new_namespace_defines_it_and_goes_on_with_it(tmp_path, state_page):
    seen = _plus_value(tmp_path, state_page,
                       inputs=['state_LEAK', 'alerts', ALERTS, 'LEAK'],
                       picks=['$(add) New namespace…'])
    assert _asked(seen, 'semforge/addNamespace') == [
        {'uri': 'file:///pkg/shacl.ttl', 'prefix': 'alerts', 'namespace': ALERTS}]
    assert _asked(seen, 'semforge/addVocabularyValue') == [
        {'uri': 'file:///pkg/shacl.ttl', 'cls': KNOW + 'MachineState', 'name': 'state_LEAK',
         'label': 'LEAK', 'namespace': 'alerts'}]
    assert 'semforge.refreshProject' in [e['command'] for e in seen['executed']]


def test_a_cancelled_namespace_writes_nothing(tmp_path, state_page):
    seen = _plus_value(tmp_path, state_page, inputs=['state_LEAK', 'LEAK'], picks=[])
    assert not _asked(seen, 'semforge/addVocabularyValue')


def test_a_prefixed_name_is_not_asked_about(tmp_path, state_page):
    seen = _plus_value(tmp_path, state_page, inputs=['material:state_LEAK', 'LEAK'])
    assert not _asked(seen, 'semforge/vocabularyNamespaces')
    assert _asked(seen, 'semforge/addVocabularyValue')[0]['name'] == 'material:state_LEAK'


def test_deriving_a_severity_class_asks_too(tmp_path, kms):
    page = dict(build_vocabulary_page(load(str(kms)), 'sh:Severity'), ok=True)
    seen = _drive(tmp_path, {
        'command': 'semforge.openVocabularyPage',
        'node': {'raw': {'kind': 'class', 'iri': str(SH.Severity), 'label': 'sh:Severity',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu', 'row': -1}],
        'picks': ['$(type-hierarchy-sub) New severity class derived from Severity…',
                  'material:AlarmLevel'],
        'inputs': ['AlarmLevel'],
        'replies': {'semforge/vocabularyPage': page, 'semforge/vocabularyNamespaces': SPACES}})
    assert _asked(seen, 'semforge/vocabularyNamespaces')[0]['near'] == str(SH.Severity)
    assert _asked(seen, 'semforge/addSeverityClass') == [
        {'uri': 'file:///pkg/shacl.ttl', 'name': 'AlarmLevel', 'parent': 'sh:Severity',
         'namespace': 'material'}]
