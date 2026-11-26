#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""What validates and cannot be deployed is said while it is written, by the
compiler itself."""

import os
import shutil
import sys

import pytest
from click.testing import CliRunner
from lsprotocol import types

from semforge.cli.main import cli
from semforge.editor.sparqldocs import Context, diagnostics
from semforge.package import load
from semforge.sparql.terms import terms_for
from semforge.target import builtin_profile, check_package
from semforge.target import deploy

CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'
HEAD = ('PREFIX iffBaseEntities: <https://industryfusion.github.io/contexts/example/v0/base_entities/>\n'
        'PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>\n')
REFUSED = '$this ?attribute ?value .'
QUERY = (HEAD + 'SELECT $this WHERE {\n    $this iffBaseEntities:hasState [ ngsild:hasValue ?s ] .\n'
         '    ' + REFUSED + '\n}')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


@pytest.fixture
def broken(kms):
    path = os.path.join(kms, 'shacl.ttl')
    with open(path) as handle:
        text = handle.read()
    with open(path, 'w') as handle:
        handle.write(text + f'''
<https://example.org/BrokenShape> a sh:NodeShape ; sh:targetClass iffBaseEntities:Cutter ;
    sh:sparql [ a sh:SPARQLConstraint ; sh:message "broken one" ; sh:select """
{QUERY}
""" ] .
''')
    return kms


RULE = (HEAD + 'CONSTRUCT { $this iffBaseEntities:hasState [ ngsild:hasValue ?value ] } WHERE {\n'
        '    ' + REFUSED + '\n}')


@pytest.fixture
def broken_rule(kms):
    path = os.path.join(kms, 'shacl.ttl')
    with open(path) as handle:
        text = handle.read()
    with open(path, 'w') as handle:
        handle.write(text + f'''
<https://example.org/BrokenRuleShape> a sh:NodeShape ; sh:targetClass iffBaseEntities:Cutter ;
    sh:rule [ a sh:SPARQLRule ; sh:construct """
{RULE}
""" ] .
''')
    return kms


def _context(package, kind='constraint'):
    return Context(package, CUTTER, kind, 'current', [], terms_for(package))


def _said(package, text, kind='constraint'):
    return [d for d in diagnostics(text, _context(package, kind)) if d.code == 'not-deployable']


def test_every_query_of_the_corpus_can_be_deployed(corpus):
    assert deploy.compiler(corpus.path) is not None
    assert deploy.problems(corpus) == []
    assert not [d for d in check_package(corpus, builtin_profile()) if d.code == 'SF-CAP-006']
    assert 'not-deployable' not in CliRunner().invoke(cli, ['check', corpus.path]).output


def test_it_is_said_at_the_line_that_is_the_reason(corpus):
    (found,) = _said(corpus, QUERY)
    assert found.severity == types.DiagnosticSeverity.Error
    assert 'variable as predicate' in found.message and 'cannot be deployed' in found.message
    assert QUERY.split('\n')[found.range.start.line].strip() == REFUSED


@pytest.mark.parametrize('where', [
    '$this ?attribute [ ngsild:hasValue ?v ] . FILTER(?v > 5)',
    '$this iffBaseEntities:hasState ?a . ?a ngsild:hasValue ?v',
    '$this iffBaseEntities:hasState/ngsild:hasValue ?v'])
def test_what_can_be_deployed_is_left_alone(corpus, where):
    assert _said(corpus, HEAD + f'SELECT $this WHERE {{ {where} }}') == []


@pytest.mark.parametrize('where, why', [
    ('{ $this iffBaseEntities:hasState [ ngsild:hasValue ?v ] } UNION { $this a ?t }', 'UNION'),
    ('$this iffBaseEntities:hasState [ ngsild:unitCode ?v ]', 'unitCode'),
    ('$this iffBaseEntities:hasState [ ngsild:hasValue ?v ] . FILTER(regex(?v, "a"))', 'REGEX')])
def test_the_reason_is_said(corpus, where, why):
    (found,) = _said(corpus, HEAD + f'SELECT $this WHERE {{ {where} }}')
    assert why.lower() in found.message.lower()


def test_a_query_that_does_not_parse_has_one_error_not_two(corpus):
    found = diagnostics(HEAD + 'SELECT $this WHERE { $this a ', _context(corpus))
    assert found and not [d for d in found if d.code == 'not-deployable']


def test_the_problems_panel_and_the_terminal_name_the_constraint(broken):
    found = [d for d in check_package(load(broken), builtin_profile()) if d.code == 'SF-CAP-006']
    assert len(found) == 1 and 'BrokenShape' in found[0].message and 'broken one' in found[0].message
    done = CliRunner().invoke(cli, ['check', broken])
    line = next(row for row in done.output.split('\n') if 'not-deployable' in row)
    assert done.exit_code == 1 and line.startswith('shacl.ttl:') and 'broken one' in line
    with open(os.path.join(broken, 'shacl.ttl')) as handle:
        rows = handle.read().split('\n')
    assert rows[int(line.split(':')[1].split()[0]) - 1].startswith('PREFIX iffBaseEntities')


def test_without_a_compiler_nothing_is_said(broken, monkeypatch):
    monkeypatch.setenv('SEMFORGE_SHACL2FLINK', '/nowhere')
    package = load(broken)
    assert deploy.compiler(package.path) is None and deploy.problems(package) == []
    assert _said(package, QUERY) == []
    assert not [d for d in check_package(package, builtin_profile()) if d.code == 'SF-CAP-006']
    assert 'not-deployable' not in CliRunner().invoke(cli, ['check', broken]).output


def test_a_compiler_that_cannot_be_loaded_is_none(tmp_path, monkeypatch):
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'lib' / 'query_check.py').write_text('import nothing_by_this_name')
    monkeypatch.setenv('SEMFORGE_SHACL2FLINK', str(tmp_path))
    assert deploy.compiler() is None
    assert 'lib' not in sys.modules and str(tmp_path) not in sys.path


def test_the_compiler_does_not_fail_the_editor(corpus, monkeypatch):
    def fail(*args):
        raise ValueError('x')
    monkeypatch.setattr(deploy, 'query_problem', fail)
    assert _said(corpus, QUERY) == []
    # The query's other marks are still given.
    text = HEAD + 'SELECT $this WHERE { $this iffBaseEntities:hasState ?a }'
    assert [d.code for d in diagnostics(text, _context(corpus))] == ['variable-node']


def test_a_rule_is_checked_as_a_rule(corpus):
    (found,) = _said(corpus, RULE, 'rule')
    assert 'variable as predicate' in found.message and 'cannot be deployed' in found.message
    assert RULE.split('\n')[found.range.start.line].strip() == REFUSED


def test_a_rule_in_the_problems_panel_is_called_a_rule(broken_rule):
    found = [d for d in check_package(load(broken_rule), builtin_profile()) if d.code == 'SF-CAP-006']
    assert len(found) == 1 and 'BrokenRuleShape' in found[0].message
    assert 'the SPARQL rule cannot be deployed' in found[0].message and 'variable as predicate' in found[0].message
    done = CliRunner().invoke(cli, ['check', broken_rule])
    (line,) = [row for row in done.output.split('\n') if 'not-deployable' in row]
    assert 'BrokenRuleShape: the SPARQL rule cannot be compiled' in line and "''" not in line


class _Refusing:
    """A check that refuses a query for one target class only."""

    def __init__(self, refused):
        self.refused, self.asked = refused, []

    def check(self, graph, files=(), draft=None):
        self.asked.append(str(draft['target']))
        if str(draft['target']) == self.refused:
            return [type('Problem', (), {'reason': f'refused for {self.refused}', 'pattern': ''})()]
        return []


@pytest.mark.parametrize('refused', ['https://example.org/A', 'https://example.org/Z'])
def test_each_target_class_is_asked(corpus, monkeypatch, refused):
    from rdflib import Graph, URIRef
    from rdflib.namespace import SH

    shape = 'https://example.org/TwoTargetsShape'
    shapes = Graph()
    for target in ('https://example.org/A', 'https://example.org/Z'):
        shapes.add((URIRef(shape), SH.targetClass, URIRef(target)))
    package = type('Package', (), {'path': corpus.path, 'shapes': shapes})()
    fake = _Refusing(refused)
    monkeypatch.setattr(deploy, 'compiler', lambda path='': fake)
    found = deploy.query_problem(package, shape, 'constraint', QUERY)
    assert found is not None and found.reason == f'refused for {refused}'


def test_two_target_classes_in_the_editor(kms, monkeypatch):
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write(f'\n<{CUTTER}> sh:targetClass <https://example.org/Other> .\n')
    package = load(kms)
    fake = _Refusing('https://example.org/Other')
    monkeypatch.setattr(deploy, 'compiler', lambda path='': fake)
    (found,) = _said(package, QUERY)
    assert 'refused for https://example.org/Other' in found.message


def test_export_refuses_what_cannot_be_deployed(broken, tmp_path):
    out = tmp_path / 'out'
    done = CliRunner(mix_stderr=False).invoke(cli, ['export', broken, '-o', str(out)])
    assert done.exit_code == 2 and 'SF-CAP-006' in done.stderr and 'broken one' in done.stderr
    assert not out.exists() or not any(out.iterdir())


def test_the_named_checkout_is_used(monkeypatch):
    here = os.path.dirname(os.path.abspath(deploy.__file__))
    real = os.path.normpath(os.path.join(here, '..', '..', '..', 'shacl2flink'))
    monkeypatch.setenv('SEMFORGE_SHACL2FLINK', real)
    assert deploy.shacl2flink_dir('/somewhere/else') == real
    assert deploy.compiler('/somewhere/else') is not None


def _fake_checkout(where, body):
    (where / 'lib').mkdir(parents=True)
    (where / 'lib' / '__init__.py').write_text('')
    (where / 'lib' / 'query_check.py').write_text(
        'class Problem:\n'
        '    def __init__(self, reason):\n'
        "        self.shape, self.kind, self.query, self.reason = 'urn:s', 'sh:select', 'q', reason\n"
        '\n\n'
        'def check(graph, files=(), draft=None):\n'
        f'    {body}\n')


def test_a_checkout_beside_the_package_is_used(kms, tmp_path, monkeypatch):
    monkeypatch.delenv('SEMFORGE_SHACL2FLINK', raising=False)
    _fake_checkout(tmp_path / 'shacl2flink', "return [Problem('from beside the package')]")
    assert deploy.shacl2flink_dir(kms) == str(tmp_path / 'shacl2flink')
    assert [p.reason for p in deploy.problems(load(kms))] == ['from beside the package']
    assert 'lib' not in sys.modules and str(tmp_path / 'shacl2flink') not in sys.path


def test_else_the_checkout_beside_semforge_is_used(tmp_path, monkeypatch):
    monkeypatch.delenv('SEMFORGE_SHACL2FLINK', raising=False)
    found = deploy.shacl2flink_dir(str(tmp_path))
    assert found.endswith(os.path.join('semantic-model', 'shacl2flink'))
    assert os.path.isfile(os.path.join(found, 'lib', 'query_check.py'))


def test_a_problem_refused_alike_for_several_classes_is_named_once(kms, tmp_path, monkeypatch):
    monkeypatch.delenv('SEMFORGE_SHACL2FLINK', raising=False)
    _fake_checkout(tmp_path / 'shacl2flink', "return [Problem('same'), Problem('same'), Problem('other')]")
    assert [p.reason for p in deploy.problems(load(kms))] == ['same', 'other']


def test_a_package_check_that_fails_says_nothing(kms, tmp_path, monkeypatch):
    monkeypatch.delenv('SEMFORGE_SHACL2FLINK', raising=False)
    _fake_checkout(tmp_path / 'shacl2flink', "raise UnicodeDecodeError('utf-8', b'', 0, 1, 'unreadable')")
    package = load(kms)
    assert deploy.problems(package) == []
    assert not [d for d in check_package(package, builtin_profile()) if d.code == 'SF-CAP-006']
    done = CliRunner().invoke(cli, ['check', kms])
    assert done.exception is None or isinstance(done.exception, SystemExit)
    assert 'not-deployable' not in done.output


def test_a_named_directory_without_the_check_is_none(tmp_path, monkeypatch):
    (tmp_path / 'lib').mkdir()
    monkeypatch.setenv('SEMFORGE_SHACL2FLINK', str(tmp_path))
    assert deploy.shacl2flink_dir() == '' and deploy.compiler() is None


def _line_of(package, text, kind='constraint'):
    (found,) = _said(package, HEAD + text, kind)
    return (HEAD + text).split('\n')[found.range.start.line].strip()


def test_a_projection_that_repeats_the_pattern_is_not_the_mark(corpus):
    text = ('SELECT $this ?attribute ?value WHERE {\n'
            '  $this iffBaseEntities:hasState [ ngsild:hasValue ?s ] .\n  $this ?attribute ?value .\n}')
    assert _line_of(corpus, text) == '$this ?attribute ?value .'


def test_a_template_that_repeats_the_pattern_is_not_the_mark(corpus):
    text = ('CONSTRUCT { $this iffBaseEntities:hasState [ ngsild:hasValue ?v ] } WHERE {\n'
            '  $this iffBaseEntities:hasStrength [ ngsild:hasValue ?s ] .\n'
            '  $this iffBaseEntities:hasState ?v .\n}')
    assert _line_of(corpus, text, 'rule') == '$this iffBaseEntities:hasState ?v .'


def test_a_function_is_found_in_any_case(corpus):
    text = ('SELECT $this ?v WHERE {\n  $this iffBaseEntities:hasState [ ngsild:hasValue ?v ] .\n'
            '  FILTER(regex(?v, "a"))\n}')
    assert _line_of(corpus, text) == 'FILTER(regex(?v, "a"))'


def test_an_iri_counts_as_a_name(corpus):
    iri = '<https://industryfusion.github.io/contexts/example/v0/base_entities/hasState>'
    text = ('SELECT $this WHERE {\n  $this iffBaseEntities:hasState [ ngsild:hasValue ?v ] .\n'
            f'  $this {iri} ?x .\n}}')
    assert _line_of(corpus, text) == f'$this {iri} ?x .'
