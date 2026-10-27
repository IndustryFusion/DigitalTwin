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

"""Incremental revalidation gives what a full one gives, and does less.

Each test validates a copy of the kms, makes one edit, and validates again the
incremental way -- then checks the result against validating everything from
scratch, and that the plan did only what the edit calls for.
"""

import os
import shutil

import pytest

from semforge.editor.incremental import Session, _digests, _keys, plan
from semforge.editor.verdicts import compute
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'


@pytest.fixture
def root(tmp_path, corpus_path):
    copy = tmp_path / 'pkg'
    shutil.copytree(corpus_path, copy, ignore=shutil.ignore_patterns('.semforge'))
    return str(copy)


def _replace(root, relative, old, new):
    path = os.path.join(root, relative)
    text = open(path, encoding='utf-8').read()
    assert text.count(old) == 1, (relative, old)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace(old, new))


def _append(root, relative, text):
    with open(os.path.join(root, relative), 'a', encoding='utf-8') as handle:
        handle.write(text)


def _edit_and_compare(root, edit):
    """(plan, verdicts before, incremental verdicts) -- asserting they equal a full run."""
    session = Session(load)
    before = session.run(root, 'v1')
    old = session._last[root]
    edit()
    package = load(root)
    the_plan = plan(old, package, _digests(root, {os.path.abspath(p) for p in
                                                  package.files('knowledge')})[0])
    after = session.run(root, 'v2')
    assert _keys(after) == _keys(compute(load(root), 'v2')), 'incremental differs from full'
    return the_plan, before, after


def test_a_constraint_edit_reevaluates_its_shape_only(root):
    the_plan, before, after = _edit_and_compare(root, lambda: _replace(
        root, 'shacl.ttl', 'sh:maxInclusive 5.0 ;', 'sh:maxInclusive 60.0 ;'))
    assert not the_plan.full and not the_plan.model and not the_plan.cases
    assert BASE + 'WorkpieceShape' in the_plan.shapes
    assert BASE + 'FilterShape' not in the_plan.shapes
    case = 'test_WorkpieceShape/bad/too-high.jsonld'
    assert _keys(before)[1][case] != _keys(after)[1][case], 'the edit shows'


def test_a_new_shape_is_evaluated(root):
    the_plan, _, after = _edit_and_compare(root, lambda: _append(root, 'shacl.ttl', '''
iffBaseShacl:ExtraShape a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasNothingLikeThis ; sh:minCount 1 ] .
'''))
    assert the_plan.shapes == {BASE + 'ExtraShape'}
    assert any(r.shape == BASE + 'ExtraShape' for r in after.model.violations)


def test_a_removed_shape_leaves_nothing_behind(root):
    def remove():
        path = os.path.join(root, 'shacl.ttl')
        text = open(path, encoding='utf-8').read()
        start = text.index('iffBaseShacl:WorkpieceShape a sh:NodeShape')
        end = text.index(' .\n\n', start) + 3
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text[:start] + text[end:])
    the_plan, _, after = _edit_and_compare(root, remove)
    assert BASE + 'WorkpieceShape' in the_plan.shapes
    assert not any(r.shape == BASE + 'WorkpieceShape' for r in after.model.results)


def test_a_comment_in_the_shapes_reevaluates_nothing(root):
    the_plan, _, _ = _edit_and_compare(root, lambda: _append(root, 'shacl.ttl', '\n# a note\n'))
    assert not the_plan.full and not the_plan.shapes


def test_a_case_edit_reevaluates_that_case(root):
    case = 'test_WorkpieceShape/bad/too-high.jsonld'
    the_plan, _, _ = _edit_and_compare(root, lambda: _replace(
        root, 'examples/' + case, '"value": 50', '"value": 3'))
    assert the_plan.cases == {case} and not the_plan.shapes and not the_plan.model


def test_an_include_edit_reevaluates_the_cases_that_include_it(root):
    from semforge.expect.store import load_expectations

    including = {e.path for e in load_expectations(root).examples
                 if any(i.endswith('workpiece-steel.jsonld') for i in e.include)}
    assert including, 'the corpus has a case that includes it'
    the_plan, _, _ = _edit_and_compare(root, lambda: _append(
        root, 'examples/subobjects/workpiece-steel.jsonld', '\n'))
    assert the_plan.cases == including


def test_an_assert_edit_reevaluates_nothing(root):
    the_plan, _, _ = _edit_and_compare(root, lambda: _replace(
        root, 'examples/test_WorkpieceShape/bad/expectations.yaml',
        'A height of 50 against a maximum of 5.0.', 'Too high.'))
    assert not the_plan.full and not the_plan.cases and not the_plan.shapes


def test_a_model_edit_reevaluates_the_model(root):
    the_plan, _, _ = _edit_and_compare(root, lambda: _replace(
        root, 'model-instance.jsonld', '"value": 0.9,', '"value": 0.95,'))
    assert the_plan.model and not the_plan.full and not the_plan.cases


def test_knowledge_no_constraint_reads_reevaluates_nothing(root):
    from rdflib import RDFS

    from semforge.validate.readset import read_set
    if RDFS.label in read_set(load(root).shapes):
        pytest.skip('a constraint of this corpus reads rdfs:label')
    the_plan, _, _ = _edit_and_compare(root, lambda: _replace(
        root, 'knowledge.ttl', 'rdfs:label "critical"', 'rdfs:label "kritisch"'))
    assert not the_plan.full and not the_plan.shapes


def test_knowledge_a_constraint_reads_reevaluates_everything(root):
    the_plan, _, _ = _edit_and_compare(root, lambda: _replace(
        root, 'knowledge.ttl', 'base:isValidFor iffBaseEntities:Filter .',
        'base:isValidFor iffBaseEntities:Cutter .'))
    assert the_plan.full


def test_the_package_settings_reevaluate_everything(root):
    the_plan, _, _ = _edit_and_compare(root, lambda: _append(root, 'semforge.yaml', '\n# a note\n'))
    assert the_plan.full


def test_a_readme_reevaluates_nothing(root):
    the_plan, _, _ = _edit_and_compare(root, lambda: _append(root, 'examples/README.md', '\nmore\n'))
    assert not the_plan.full and not the_plan.cases and not the_plan.shapes and not the_plan.model


def test_a_referenced_shape_reevaluates_who_refers_to_it(tmp_path):
    """sh:node: the shape that uses another is affected by a change to it."""
    from semforge.editor.incremental import changed_shapes
    from rdflib import Graph

    head = '@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix ex: <https://example.org/> .\n'
    old = Graph().parse(data=head + '''
ex:Outer a sh:NodeShape ; sh:targetClass ex:C ;
    sh:property [ sh:path ex:p ; sh:node ex:Inner ] .
ex:Inner a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:minCount 1 ] .
ex:Other a sh:NodeShape ; sh:targetClass ex:D ; sh:property [ sh:path ex:r ; sh:minCount 1 ] .
''', format='turtle')
    new = Graph().parse(data=head + '''
ex:Outer a sh:NodeShape ; sh:targetClass ex:C ;
    sh:property [ sh:path ex:p ; sh:node ex:Inner ] .
ex:Inner a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:minCount 2 ] .
ex:Other a sh:NodeShape ; sh:targetClass ex:D ; sh:property [ sh:path ex:r ; sh:minCount 1 ] .
''', format='turtle')
    affected = changed_shapes(old, new)
    assert {'https://example.org/Inner', 'https://example.org/Outer'} <= affected
    assert 'https://example.org/Other' not in affected


def test_a_rule_change_means_everything():
    from rdflib import Graph

    from semforge.editor.incremental import changed_shapes

    head = '@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix ex: <https://example.org/> .\n'
    rule = 'ex:R a sh:NodeShape ; sh:targetClass ex:C ; sh:rule [ a sh:SPARQLRule ; sh:construct "{}" ] .\n'
    old = Graph().parse(data=head + rule, format='turtle')
    new = Graph().parse(data=head + rule.replace('"{}"', '"{ }"'), format='turtle')
    assert changed_shapes(old, new) is None


def test_verify_mode_agrees(root, monkeypatch, capsys):
    monkeypatch.setenv('SEMFORGE_VERIFY_INCREMENTAL', '1')
    _edit_and_compare(root, lambda: _replace(
        root, 'shacl.ttl', 'sh:maxInclusive 5.0 ;', 'sh:maxInclusive 60.0 ;'))
    assert 'differ' not in capsys.readouterr().err


# --- what changed in the knowledge, statement by statement ----------------------------

HEAD = ('@prefix ex: <https://example.org/> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n')
SHAPES = HEAD + '''@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:read ; sh:minCount 1 ] .
'''


def _matters(tmp_path, before, after):
    from types import SimpleNamespace

    from rdflib import Graph

    from semforge.editor.incremental import knowledge_matters

    path = tmp_path / 'k.ttl'
    path.write_text(after)
    shapes = Graph().parse(data=SHAPES, format='turtle')
    old = SimpleNamespace(package=SimpleNamespace(shapes=shapes),
                          knowledge={str(path): before.encode('utf-8')})
    return knowledge_matters(old, SimpleNamespace(shapes=shapes, path=str(tmp_path)), [str(path)])


def test_a_label_change_does_not_matter_beside_a_type(tmp_path):
    """The OPC UA case: a browse name edited in the statement that types the node."""
    assert not _matters(tmp_path, HEAD + 'ex:x a ex:C ; rdfs:label "a" ; ex:read 1 .\n',
                        HEAD + 'ex:x a ex:C ; rdfs:label "b" ; ex:read 1 .\n')


def test_a_read_predicate_inside_a_blank_node_matters(tmp_path):
    assert _matters(tmp_path, HEAD + 'ex:x ex:other [ ex:read 1 ] .\n',
                    HEAD + 'ex:x ex:other [ ex:read 2 ] .\n')


def test_a_type_change_matters(tmp_path):
    assert _matters(tmp_path, HEAD + 'ex:x a ex:C .\n', HEAD + 'ex:x a ex:D .\n')


def test_changed_prefixes_matter(tmp_path):
    assert _matters(tmp_path, HEAD + 'ex:x rdfs:label "a" .\n',
                    HEAD.replace('https://example.org/', 'https://example.org/v2/')
                    + 'ex:x rdfs:label "a" .\n')


def test_a_statement_that_does_not_parse_alone_matters(tmp_path):
    assert _matters(tmp_path, HEAD + 'ex:x rdfs:label "a" .\n', HEAD + 'ex:x rdfs:label .\n')


def test_nothing_changed_does_not_matter(tmp_path):
    text = HEAD + 'ex:x a ex:C ; ex:read [ ex:deep 1 ] .\n'
    assert not _matters(tmp_path, text, text)


def test_verdicts_from_disk_make_the_first_edit_incremental(root, monkeypatch):
    """After a restart the verdicts come from disk and the worker held no run:
    the first edit validated everything (5-6 s on the OPC UA pumps). Primed
    with them, it is compared with that version like any later edit."""
    import semforge.editor.incremental as incremental

    from semforge.editor.cache import fingerprint

    stored = compute(load(root), fingerprint(root))   # what the disk cache holds
    session = Session(load)
    assert session.prime(root, stored)
    assert not session.prime(root, stored), 'once per version'
    full = []
    monkeypatch.setattr(incremental, 'compute',
                        lambda package, stamp: full.append(stamp) or compute(package, stamp))
    _replace(root, 'model-instance.jsonld', '"urn:cutter:1"', '"urn:cutter:1" ')
    after = session.run(root, fingerprint(root))
    assert full == [], 'the first edit after the restart validated everything'
    assert _keys(after) == _keys(compute(load(root), 'v2'))


def test_an_edit_before_the_prime_keeps_it_out(root):
    """The prime waits in the worker's queue. Edited meanwhile, the files
    are not what the verdicts judged: kept as their version, the next run
    would find nothing changed and show the old verdicts as current."""
    from semforge.editor.cache import fingerprint

    stored = compute(load(root), fingerprint(root))
    _replace(root, 'model-instance.jsonld', '"urn:cutter:1"', '"urn:cutter:1" ')
    session = Session(load)
    assert not session.prime(root, stored)
    assert root not in session._last
    after = session.run(root, fingerprint(root))
    assert _keys(after) == _keys(compute(load(root), 'v2'))


def test_the_prime_builds_what_the_first_edit_would(root, monkeypatch):
    """The model validated and the findings computed once: the Turtle
    index the findings build was 8 of the 13 s of the first edit."""
    import semforge.editor.incremental as incremental
    import semforge.validate.orchestrator as orchestrator
    from semforge.editor.cache import fingerprint

    stored = compute(load(root), fingerprint(root))
    called = []
    real_findings, real_validate = incremental.findings, orchestrator.validate_graphs
    monkeypatch.setattr(incremental, 'findings',
                        lambda *a: called.append('findings') or real_findings(*a))
    monkeypatch.setattr(orchestrator, 'validate_graphs',
                        lambda *a, **k: called.append('model') or real_validate(*a, **k))
    assert Session(load).prime(root, stored)
    assert called == ['model', 'findings']
