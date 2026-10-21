"""Sanity: references that point at nothing, and declarations nothing uses.

Each check is driven by breaking ONE link in a copy of the corpus and asserting
the finding lands on the line that holds it -- a finding on the wrong line is a
finding nobody can act on. The clean corpus must produce none, or the check is
noise. The quick fixes are then applied to those same findings.
"""

import os
import shutil
import subprocess
import sys

import pytest

from semforge.cooked.remove_attribute import remove_declaration
from semforge.package import load
from semforge.sanity import known_constraints, sanity

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
WORKPIECE_BAD = os.path.join('examples', 'test_WorkpieceShape', 'bad',
                             'expectations.yaml')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _line(path, line):
    with open(path, encoding='utf-8') as handle:
        return handle.read().split('\n')[line - 1]


def _by_code(root, code):
    return [f for f in sanity(load(root)) if f.code == code]


def _edit(root, relative, old, new):
    path = os.path.join(root, relative)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    assert old in text, f'{old!r} not in {relative}'
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace(old, new, 1))
    return path


# --- the clean corpus is clean ------------------------------------------------

def test_the_corpus_has_no_broken_links(kms):
    # Its datasetIds included: urn:index:1 reads hasX[index:1], the kms
    # registering index: for urn:index:.
    loud = [f for f in sanity(load(kms)) if f.severity in ('error', 'warning')]
    assert loud == [], loud


def test_every_real_assert_names_a_known_constraint(kms):
    from semforge.expect.store import load_expectations

    known = known_constraints(load(kms))
    asserted = {a['constraint'] for e in load_expectations(kms).examples
                for a in e.asserts}
    assert asserted and asserted <= known


# --- each check, on the line that holds it -------------------------------------

def test_a_sh_path_to_a_removed_declaration_is_an_error_on_that_line(kms):
    remove_declaration(load(kms), 'iffBaseEntities:hasWidth', force=True)
    found = _by_code(kms, 'undeclared-path')
    assert len(found) == 1 and found[0].severity == 'error'
    text = _line(found[0].file, found[0].line)
    assert 'sh:path' in text and 'hasWidth' in text


def test_a_query_reading_a_removed_declaration_is_a_warning_on_that_line(kms):
    remove_declaration(load(kms), 'iffBaseEntities:hasStrength', force=True)
    found = _by_code(kms, 'sparql-undeclared')
    assert found and all(f.severity == 'warning' for f in found)
    for finding in found:
        assert 'hasStrength' in _line(finding.file, finding.line)
        assert 'sh:path' not in _line(finding.file, finding.line)


def test_a_stale_assert_is_an_error_on_its_constraint_line(kms):
    _edit(kms, WORKPIECE_BAD, 'hasHeight/MaxInclusive', 'hasNoSuchThing/MaxInclusive')
    found = _by_code(kms, 'stale-assert')
    assert len(found) == 1
    assert 'hasNoSuchThing' in _line(found[0].file, found[0].line)
    assert 'hasHeight/MaxInclusive' in found[0].message, \
        'it should say what the shape DOES declare'


@pytest.mark.parametrize('old, new, which', [
    ('sh:class iffBaseEntities:Filter', 'sh:class iffBaseEntities:Filtre', 'sh:class'),
    ('sh:targetClass iffBaseEntities:Workpiece',
     'sh:targetClass iffBaseEntities:Werkstueck', 'sh:targetClass')])
def test_an_undeclared_class_is_an_error(kms, old, new, which):
    _edit(kms, 'shacl.ttl', old, new)
    found = _by_code(kms, 'undeclared-class')
    assert found and which in found[0].message
    assert new.split()[-1] in _line(found[0].file, found[0].line)


def test_a_declared_attribute_nothing_uses_is_a_note_until_it_is_used(kms):
    from semforge.cooked.constrain import add_attribute_constraint
    from semforge.cooked.knowledge import add_attribute_term

    made = add_attribute_term(load(kms), 'hasNothingYet', 'Property',
                              'iffBaseEntities:Workpiece')
    found = _by_code(kms, 'unused-attribute')
    assert [f.subject for f in found] == [made['iri']]
    assert found[0].severity == 'information'
    assert 'hasNothingYet' in _line(found[0].file, found[0].line)

    add_attribute_constraint(load(kms), BASE + 'base_shacl/WorkpieceShape',
                             made['iri'])
    assert _by_code(kms, 'unused-attribute') == []


# --- the test runner says what is wrong ----------------------------------------

def test_a_stale_assert_fails_with_the_reason_not_with_did_not_fire(kms):
    _edit(kms, WORKPIECE_BAD, 'hasHeight/MaxInclusive', 'hasNoSuchThing/MaxInclusive')
    out = subprocess.run([sys.executable, '-m', 'semforge', 'test', kms],
                         capture_output=True, text=True)
    assert out.returncode == 1
    assert 'a constraint no shape declares' in out.stdout
    assert 'but it did not' not in out.stdout


# --- the quick fixes, applied to the findings ----------------------------------

def test_remove_this_use_takes_only_the_marked_property_shape(kms):
    from rdflib import URIRef
    from rdflib.namespace import SH

    from semforge.cooked.remove_use import remove_property_at

    remove_declaration(load(kms), 'iffBaseEntities:hasWidth', force=True)
    finding = _by_code(kms, 'undeclared-path')[0]
    remove_property_at(finding.fix['file'], finding.fix['offset'])
    shapes = load(kms).shapes
    assert (None, SH.path, URIRef(BASE + 'base_entities/hasWidth')) not in shapes
    assert (None, SH.path, URIRef(BASE + 'base_entities/hasHeight')) in shapes
    assert _by_code(kms, 'undeclared-path') == []


def test_remove_this_assert_flags_a_bad_case_left_with_none(kms):
    from semforge.cooked.remove_use import remove_assert

    _edit(kms, WORKPIECE_BAD, 'hasHeight/MaxInclusive', 'hasNoSuchThing/MaxInclusive')
    finding = _by_code(kms, 'stale-assert')[0]
    note = remove_assert(finding.fix['file'], finding.fix['case'], finding.fix['index'])
    assert 'no longer asserts' in note
    assert _by_code(kms, 'stale-assert') == []


def test_remove_this_key_takes_only_the_marked_key(kms):
    from semforge.cooked.remove_use import remove_key_at

    path = os.path.join(kms, 'examples', 'subobjects', 'workpiece-steel.jsonld')
    with open(path, encoding='utf-8') as handle:
        before = handle.read()
    line = next(n for n, text in enumerate(before.split('\n'), 1) if 'hasWidth' in text)
    remove_key_at(load(kms), path, line, BASE + 'base_entities/hasWidth')
    with open(path, encoding='utf-8') as handle:
        after = handle.read()
    assert 'hasWidth' not in after and 'hasHeight' in after


def test_a_fix_on_a_stale_place_refuses_rather_than_guesses(kms):
    from semforge.cooked.remove_use import remove_key_at
    from semforge.errors import PackageError

    path = os.path.join(kms, 'examples', 'subobjects', 'workpiece-steel.jsonld')
    with pytest.raises(PackageError, match='changed'):
        remove_key_at(load(kms), path, 1, BASE + 'base_entities/hasWidth')


def test_each_finding_offers_its_quick_fixes():
    from lsprotocol import types

    from semforge.editor.server import _fixes_for

    def diagnostic(data):
        return types.Diagnostic(
            range=types.Range(types.Position(4, 0), types.Position(4, 200)),
            message='m', source='semforge (sanity)', data=data)

    iri = BASE + 'base_entities/hasWidth'
    titles = {code: [a.title for a in _fixes_for(diagnostic(data), 'file:///p/x')]
              for code, data in {
                  'undeclared-path': {'code': 'undeclared-path', 'subject': iri,
                                      'declare': iri, 'file': '/p/x', 'offset': 9},
                  'undeclared-key': {'code': 'undeclared-key', 'subject': iri,
                                     'declare': iri},
                  'stale-assert': {'code': 'stale-assert', 'subject': 'S/a/C',
                                   'file': '/p/e.yaml', 'case': 'c', 'index': 0},
                  'unused-attribute': {'code': 'unused-attribute', 'subject': iri,
                                       'delete': iri}}.items()}
    assert titles['undeclared-path'] == ['Declare hasWidth in the knowledge',
                                         'Remove this property shape for hasWidth']
    assert titles['undeclared-key'] == ['Declare hasWidth in the knowledge',
                                        'Remove hasWidth from this entity']
    assert titles['stale-assert'] == ['Remove this assert']
    assert titles['unused-attribute'] == ['Delete hasWidth…']
    key = _fixes_for(diagnostic({'code': 'undeclared-key', 'subject': iri,
                                 'declare': iri}), 'file:///p/x')[1]
    assert key.command.arguments[0]['line'] == 5, 'the diagnostic line, 1-based'


def test_the_editor_carries_sanity_findings_with_their_fix_data(kms):
    from semforge.editor import analyse

    remove_declaration(load(kms), 'iffBaseEntities:hasWidth', force=True)
    findings, _ = analyse(kms)
    flat = [f for items in findings.values() for f in items]
    path = [f for f in flat if f.code == 'undeclared-path']
    assert path and path[0].data['declare'].endswith('hasWidth')
    keys = [f for f in flat if f.code == 'undeclared-key']
    assert keys and all(f.data['declare'] for f in keys)


# --- semforge check -------------------------------------------------------------

def _check(root, *flags):
    return subprocess.run([sys.executable, '-m', 'semforge', 'check', root, *flags],
                          capture_output=True, text=True)


def test_check_passes_a_clean_package(kms):
    out = _check(kms)
    assert out.returncode == 0, out.stdout + out.stderr
    assert '0 error(s)' in out.stdout


def test_check_fails_on_a_broken_link_and_names_its_line(kms):
    remove_declaration(load(kms), 'iffBaseEntities:hasWidth', force=True)
    out = _check(kms)
    assert out.returncode == 1
    assert 'undeclared-path' in out.stdout and 'shacl.ttl:' in out.stdout
    assert 'undeclared-key' in out.stdout


def test_check_strict_fails_on_a_warning(kms):
    """A typo inside a query is the warning-only case: nothing else breaks."""
    _edit(kms, 'shacl.ttl', '?wp iffBaseEntities:hasHeight [',
          '?wp iffBaseEntities:hasHeigth [')
    loose = _check(kms)
    assert 'sparql-undeclared' in loose.stdout and 'hasHeigth' in loose.stdout
    assert loose.returncode == 0, 'a warning alone must not fail a plain check'
    assert _check(kms, '--strict').returncode == 1
