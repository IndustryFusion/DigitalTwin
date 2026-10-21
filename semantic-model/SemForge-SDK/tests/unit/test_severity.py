"""Severity, in SHACL's own vocabulary.

`sh:Severity` is the class; `sh:Violation` (the default), `sh:Warning` and
`sh:Info` are always offered; a package adds levels as individuals of
`sh:Severity` or of a class derived from it, and derives further classes.
`sh:severity` is set on any constraint: an attribute's property shape or a
SPARQL constraint. Run on copies of the kms corpus (its files link into
semantic-model/kms, so a copy follows the links).
"""

import shutil
import subprocess
import sys
import os

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF, RDFS, SH

from semforge.cooked.severity import (add_class, add_level, describe, levels, link_class,
                                      set_severity, severity_classes)
from semforge.errors import PackageError
from semforge.package import load

KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
SHAPES = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
CUTTER = SHAPES + 'StateOnCutterShape'
FILTER = SHAPES + 'FilterShape'
SEMFORGE = os.path.join(os.path.dirname(sys.executable), 'semforge')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


# --- the vocabulary ---------------------------------------------------------------------

def test_shacl_s_three_are_always_offered_then_the_package_s(kms):
    found = [(level['term'], level['label'], level['class']) for level in levels(load(str(kms)))]
    assert found[:3] == [('sh:Violation', 'violation', 'sh:Severity'),
                         ('sh:Warning', 'warning', 'sh:Severity'),
                         ('sh:Info', 'info', 'sh:Severity')]
    assert ('base:severityCritical', 'critical', 'base:SeverityClass') in found


def test_a_class_used_for_severities_but_not_linked_is_said_so(kms):
    classes = {c['term']: c for c in severity_classes(load(str(kms)))}
    assert classes['sh:Severity']['linked']
    assert classes['base:SeverityClass']['linked'] is False


def test_linking_it_makes_it_a_kind_of_sh_severity(kms):
    link_class(load(str(kms)), KNOW + 'SeverityClass')
    package = load(str(kms))
    assert (URIRef(KNOW + 'SeverityClass'), RDFS.subClassOf, SH.Severity) in package.knowledge
    assert {c['term']: c for c in severity_classes(package)}['base:SeverityClass']['linked']


def test_a_level_is_said_by_its_label_and_the_default_is_violation(kms):
    package = load(str(kms))
    assert describe(package, KNOW + 'severityCritical') == {
        'iri': KNOW + 'severityCritical', 'label': 'critical', 'known': True}
    assert describe(package, None)['label'] == 'violation'
    assert describe(package, str(SH.Info))['label'] == 'info'
    assert describe(package, KNOW + 'severityNowhere')['known'] is False


def test_a_new_level_of_sh_severity_itself(kms):
    made = add_level(load(str(kms)), 'sh:Severity', 'severityMajor', 'major')
    package = load(str(kms))
    iri = URIRef(made['iri'])
    assert (iri, RDF.type, SH.Severity) in package.knowledge
    assert (iri, RDFS.label, None) in package.knowledge
    assert any(level['iri'] == made['iri'] and level['label'] == 'major'
               for level in levels(package))


def test_a_derived_class_and_a_level_of_it(kms):
    made = add_class(load(str(kms)), 'AlarmLevel')
    package = load(str(kms))
    assert (URIRef(made['iri']), RDFS.subClassOf, SH.Severity) in package.knowledge
    sub = add_class(package, 'PlantAlarm', made['term'])
    package = load(str(kms))
    assert (URIRef(sub['iri']), RDFS.subClassOf, URIRef(made['iri'])) in package.knowledge
    level = add_level(package, sub['term'], 'plantStop', 'critical')
    assert any(lv['iri'] == level['iri'] and lv['class'] == sub['term']
               for lv in levels(load(str(kms))))


@pytest.mark.parametrize('call, said', [
    (lambda p: add_level(p, 'base:Wasteclass', 'x'), 'not sh:Severity or a class derived'),
    (lambda p: add_level(p, 'sh:Severity', '2bad'), 'not a name'),
    (lambda p: add_level(p, 'sh:Severity', 'severityCritical'), 'already declared'),
    (lambda p: add_class(p, 'lowercase'), 'not a class name'),
    (lambda p: add_class(p, 'Fine', 'base:Wasteclass'), 'not sh:Severity or a class derived'),
])
def test_what_cannot_be_a_severity_is_refused(kms, call, said):
    with pytest.raises(PackageError, match=said):
        call(load(str(kms)))


# --- setting it on a constraint ---------------------------------------------------------

def test_an_attribute_constraint_gets_a_severity(kms):
    before = _read(kms / 'shacl.ttl')
    set_severity(load(str(kms)), FILTER, path=['iffBaseEntities:hasStrength'],
                 severity='sh:Warning')
    package = load(str(kms))
    group = next(g for g in package.shapes.objects(URIRef(FILTER), SH.property)
                 if (g, SH.path, URIRef(ENT + 'hasStrength')) in package.shapes)
    assert (group, SH.severity, SH.Warning) in package.shapes
    after = _read(kms / 'shacl.ttl')
    assert len(after.splitlines()) == len(before.splitlines()) + 1, 'one line added'


def test_changing_and_removing_it(kms):
    set_severity(load(str(kms)), FILTER, path=['iffBaseEntities:hasStrength'],
                 severity='sh:Warning')
    set_severity(load(str(kms)), FILTER, path=['iffBaseEntities:hasStrength'],
                 severity='base:severityCritical')
    package = load(str(kms))
    assert len(list(package.shapes.objects(None, SH.severity))) == 3, 'replaced, not added'
    set_severity(load(str(kms)), FILTER, path=['iffBaseEntities:hasStrength'], severity=None)
    assert len(list(load(str(kms)).shapes.objects(None, SH.severity))) == 2, \
        'back to the default; the kms\'s own two stay'


def test_a_sparql_constraint_gets_one_by_its_position(kms):
    set_severity(load(str(kms)), CUTTER, holder=0, severity='sh:Info')
    shapes = load(str(kms)).shapes
    holder = next(shapes.objects(URIRef(CUTTER), SH.sparql))
    assert (holder, SH.severity, SH.Info) in shapes


def test_the_shapes_test_the_same_after_a_severity_change_they_do_not_see(kms):
    set_severity(load(str(kms)), FILTER, path=['iffBaseEntities:hasStrength'],
                 severity='sh:Warning')
    run = subprocess.run([SEMFORGE, 'test', str(kms)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-600:]


@pytest.mark.parametrize('kwargs, said', [
    ({'path': ['iffBaseEntities:hasStrength'], 'severity': 'base:Wasteclass'},
     'not a severity level'),
    ({'path': ['iffBaseEntities:hasNothing'], 'severity': 'sh:Info'}, 'no property shape'),
    ({'holder': 5, 'severity': 'sh:Info'}, 'no SPARQL query 5'),
    ({'severity': 'sh:Info'}, 'which constraint'),
])
def test_setting_is_refused_when_it_cannot_be_right(kms, kwargs, said):
    shape = CUTTER if 'holder' in kwargs else FILTER
    before = _read(kms / 'shacl.ttl')
    with pytest.raises(PackageError, match=said):
        set_severity(load(str(kms)), shape, **kwargs)
    assert _read(kms / 'shacl.ttl') == before
