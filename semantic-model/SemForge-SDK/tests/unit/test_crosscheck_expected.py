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

"""The differences the SQLite cross-check lists as expected (#966,
semforge-sdk/model-numbers).

Two kinds the compiler makes on purpose, and the tests that they stay
narrow: a string the compiled SQL judges by its text (#958, design D5), and
an sh:or of datatypes the compiled SQL names after its datatype check. The
probe package is the one of task 4.2 of #958: one entity per row of
shacl2flink's number table, on an xsd:double, an xsd:integer and an sh:or
attribute.
"""

import json
import os
import shutil
import sys

import pytest
from click.testing import CliRunner

from semforge.errors import Diagnostic
from semforge.validate.results import UNTYPED, Result
from semforge.target.crosscheck import available, compare, cross_check

XSD = 'http://www.w3.org/2001/XMLSchema#'
DOUBLE, INTEGER, STRING, BOOLEAN = (XSD + t for t in ('double', 'integer', 'string', 'boolean'))
SHACL2FLINK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shacl2flink'))
VECTORS = os.path.join(SHACL2FLINK, 'tests', 'jsonld-number-vectors.json')
# The interpreter that runs shacl2flink's build. Its own dependencies
# (requirements-crosscheck.txt) need not be in the SDK's environment.
COMPILER_PYTHON = os.environ.get('SEMFORGE_CROSSCHECK_PYTHON', sys.executable)


def _result(attribute, component, value='', value_datatype='', datatypes=(), resource='urn:e:1'):
    return Result(resource=resource, attribute=attribute, component=component,
                  shape='urn:s:S', severity='violation', value=value,
                  value_datatype=value_datatype, datatypes=tuple(datatypes))


# --- an sh:or, named twice ------------------------------------------------

def test_a_failing_sh_or_named_after_its_datatype_check_is_one_expected_difference():
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasEither)', 'warning')]
    ours = [_result('hasEither', 'OrConstraintComponent', 'true', BOOLEAN, (DOUBLE, INTEGER))]
    [found] = compare(rows, ours)
    assert (found.code, found.severity) == ('SF-XCHK-EXPECTED', 'info')
    assert 'DatatypeConstraintComponent(hasEither)' in found.message
    assert 'OrConstraintComponent(hasEither)' in found.message
    assert 'sh:or of datatypes' in found.message and 'expected, not a compiler bug' in found.message


def test_an_sh_or_that_is_not_of_datatypes_is_not_merged():
    """An sh:or over shapes compiles into no datatype check: a datatype alert
    against it is a real difference."""
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasEither)', 'warning')]
    ours = [_result('hasEither', 'OrConstraintComponent', 'true', BOOLEAN, ())]
    assert [d.code for d in compare(rows, ours)] == ['SF-XCHK-MISSED', 'SF-XCHK-EXTRA']


def test_the_merge_needs_the_same_entity_and_attribute():
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasOther)', 'warning'),
            ('urn:e:2', 'DatatypeConstraintComponent(hasEither)', 'warning')]
    ours = [_result('hasEither', 'OrConstraintComponent', 'true', BOOLEAN, (DOUBLE, INTEGER))]
    assert [d.code for d in compare(rows, ours)] == [
        'SF-XCHK-MISSED', 'SF-XCHK-MISSED', 'SF-XCHK-EXTRA']


def test_the_merge_pairs_one_to_one():
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasEither)', 'warning')] * 2
    ours = [_result('hasEither', 'OrConstraintComponent', 'true', BOOLEAN, (DOUBLE, INTEGER))]
    assert [d.code for d in compare(rows, ours)] == ['SF-XCHK-EXPECTED', 'SF-XCHK-MISSED']


# --- strings judged by their text -----------------------------------------

@pytest.mark.parametrize('text, component, datatypes', [
    ('80.0', 'DatatypeConstraintComponent', (DOUBLE,)),
    ('1e3', 'DatatypeConstraintComponent', (DOUBLE,)),
    ('80', 'DatatypeConstraintComponent', (INTEGER,)),
    ('-3', 'DatatypeConstraintComponent', (INTEGER,)),
    ('0', 'OrConstraintComponent', (DOUBLE, INTEGER)),
    ('80.0', 'OrConstraintComponent', (DOUBLE, INTEGER)),
])
def test_a_string_the_compiled_sql_reads_as_an_admitted_number_is_expected(text, component, datatypes):
    [found] = compare([], [_result('hasX', component, text, UNTYPED, datatypes)])
    assert found.code == 'SF-XCHK-EXPECTED'
    assert f'the string "{text}"' in found.message
    assert 'judged by their text' in found.message


@pytest.mark.parametrize('value, value_datatype, component, datatypes', [
    # a number, not a string: a real difference
    ('80', INTEGER, 'DatatypeConstraintComponent', (DOUBLE,)),
    ('80.5', DOUBLE, 'DatatypeConstraintComponent', (INTEGER,)),
    # a string whose text is a number the constraint does not admit
    ('80.0', UNTYPED, 'DatatypeConstraintComponent', (INTEGER,)),
    ('80.5', UNTYPED, 'DatatypeConstraintComponent', (INTEGER,)),
    # a string whose text is no number
    ('eighty', UNTYPED, 'DatatypeConstraintComponent', (DOUBLE,)),
    ('true', UNTYPED, 'OrConstraintComponent', (DOUBLE, INTEGER)),
    # a constraint other than sh:datatype and sh:or
    ('80', UNTYPED, 'MaxInclusiveConstraintComponent', ()),
    # an sh:or with a branch that is not a datatype
    ('80', UNTYPED, 'OrConstraintComponent', ()),
    # a declared xsd:string: its type decides, on both sides
    ('80.0', STRING, 'DatatypeConstraintComponent', (DOUBLE,)),
    ('80', STRING, 'OrConstraintComponent', (DOUBLE, INTEGER)),
    # digits of another script: the SQL's \\d is ASCII
    ('\u0668\u0660', UNTYPED, 'DatatypeConstraintComponent', (INTEGER,)),
    ('\u0668\u0660.\u0660', UNTYPED, 'DatatypeConstraintComponent', (DOUBLE,)),
    # a trailing newline is not part of a number
    ('80\n', UNTYPED, 'DatatypeConstraintComponent', (INTEGER,)),
])
def test_a_real_difference_stays_unexpected(value, value_datatype, component, datatypes):
    [found] = compare([], [_result('hasX', component, value, value_datatype, datatypes)])
    assert (found.code, found.severity) == ('SF-XCHK-EXTRA', 'warning')


def test_a_difference_the_compiled_sql_reports_alone_stays_missed():
    """D5 makes the SQL more lenient, never stricter: a datatype alert pyshacl
    does not raise is never expected."""
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasX)', 'warning')]
    assert [d.code for d in compare(rows, [])] == ['SF-XCHK-MISSED']


def test_only_the_surplus_of_a_key_is_classified():
    """Two datatype results on one attribute, one alert in the SQL: the alert
    is the number's, so the one difference is the string's."""
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasX)', 'warning')]
    ours = [_result('hasX', 'DatatypeConstraintComponent', '80.0', UNTYPED, (DOUBLE,)),
            _result('hasX', 'DatatypeConstraintComponent', '80', INTEGER, (DOUBLE,))]
    assert [d.code for d in compare(rows, ours)] == ['SF-XCHK-EXPECTED']


def test_a_surplus_the_counts_cannot_attribute_stays_a_difference():
    """Two numbers and a string against one alert: which number the SQL
    matched, and whether it rejected the string as well, is not knowable."""
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasX)', 'warning')]
    ours = [_result('hasX', 'DatatypeConstraintComponent', '80.0', UNTYPED, (DOUBLE,)),
            _result('hasX', 'DatatypeConstraintComponent', '80', INTEGER, (DOUBLE,)),
            _result('hasX', 'DatatypeConstraintComponent', '7', INTEGER, (DOUBLE,))]
    [found] = compare(rows, ours)
    assert found.code == 'SF-XCHK-EXTRA' and '(2 times)' in found.message
    # and with no alert at all, the number is a difference the string cannot hide
    [found] = compare([], ours[:2])
    assert found.code == 'SF-XCHK-EXTRA' and '(2 times)' in found.message


def test_a_string_s_sh_or_is_no_partner_for_another_value_s_datatype_alert():
    """Two values on one sh:or attribute, the string "80" and the integer 80.
    pyshacl rejects only the string; a datatype alert of the SQL is about the
    integer, then, and stays missed -- the string is expected by its text."""
    rows = [('urn:e:1', 'DatatypeConstraintComponent(hasEither)', 'warning')]
    ours = [_result('hasEither', 'OrConstraintComponent', '80', UNTYPED, (DOUBLE, INTEGER))]
    found = compare(rows, ours)
    assert [d.code for d in found] == ['SF-XCHK-MISSED', 'SF-XCHK-EXPECTED']
    assert 'judged by their text' in found[1].message


# --- the probe package ----------------------------------------------------

E = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
ATTRIBUTES = ('hasDoubleX', 'hasIntegerX', 'hasEitherX')
SHAPES = '''
<https://example.org/NumberProbeShape> a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasDoubleX ; sh:nodeKind sh:BlankNode ;
                  sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                                sh:datatype xsd:double ] ] ,
                [ sh:path iffBaseEntities:hasIntegerX ; sh:nodeKind sh:BlankNode ;
                  sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                                sh:datatype xsd:integer ] ] ,
                [ sh:path iffBaseEntities:hasEitherX ; sh:nodeKind sh:BlankNode ;
                  sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                                sh:or ( [ sh:datatype xsd:double ] [ sh:datatype xsd:integer ] ) ] ] .
'''
KNOWLEDGE = ''.join(f'\n<{E}{name}> a <http://www.w3.org/2002/07/owl#ObjectProperty> ; '
                    f'<http://www.w3.org/2000/01/rdf-schema#domain> <{E}Filter> .\n'
                    for name in ATTRIBUTES)
with open(VECTORS, encoding='utf-8') as _handle:
    TABLE = json.load(_handle)['vectors']


def _entity(row):
    return f'urn:probe:{row + 1}'


@pytest.fixture
def probe(tmp_path, corpus):
    """A copy of the corpus whose model holds one Filter per row of the
    number table, each giving all three attributes the row's value."""
    from semforge.package import load

    root = tmp_path / 'probe'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    (root / 'shacl.ttl').write_text((root / 'shacl.ttl').read_text() + SHAPES)
    (root / 'knowledge.ttl').write_text((root / 'knowledge.ttl').read_text() + KNOWLEDGE)
    model = root / 'model-instance.jsonld'
    entities = json.loads(model.read_text())
    context = entities[0]['@context']
    for row, vector in enumerate(TABLE):
        value = json.loads(vector['json'])
        entities.append({'@context': context, 'id': _entity(row), 'type': 'iffBaseEntities:Filter',
                         **{f'iffBaseEntities:{name}': {'type': 'Property', 'value': value}
                            for name in ATTRIBUTES}})
    model.write_text(json.dumps(entities))
    return load(str(root))


def _rows(predicate):
    return [row for row, vector in enumerate(TABLE) if predicate(vector)]


def _expected_probe_differences():
    """What the cross-check lists as expected on the probe, derived from the
    table: each string pyshacl rejects where its text is an admitted number,
    and the boolean on the sh:or, which both reject under two names."""
    expected = set()
    for row in _rows(lambda v: v['datatype'] == 'string'):
        text = json.loads(TABLE[row]['json'])
        if '.' in text or 'e' in text.lower():
            expected |= {(_entity(row), 'DatatypeConstraintComponent', 'hasDoubleX'),
                         (_entity(row), 'OrConstraintComponent', 'hasEitherX')}
        else:
            expected |= {(_entity(row), 'DatatypeConstraintComponent', 'hasIntegerX'),
                         (_entity(row), 'OrConstraintComponent', 'hasEitherX')}
    for row in _rows(lambda v: v['datatype'] == 'boolean'):
        expected.add((_entity(row), 'DatatypeConstraintComponent', 'hasEitherX'))
    return expected


def _named(diagnostic):
    """(entity, component, attribute) an expected entry is about: the first
    `Component(attribute)` its message names."""
    import re
    component, attribute = re.search(r'(\w+ConstraintComponent)\((\w+)\)', diagnostic.message).groups()
    return diagnostic.subject, component, attribute


def test_pyshacl_reports_the_value_and_what_the_constraint_admits(probe):
    """What the cross-check classifies by: the rejected value and its type,
    and the datatypes of the sh:datatype or sh:or that rejected it."""
    from semforge.validate import validate_package

    found = {(r.resource, r.attribute): r for r in validate_package(probe, strict=False).violations
             if r.resource.startswith('urn:probe:') and r.attribute in ATTRIBUTES}
    [digits] = _rows(lambda v: v['json'] == '"80"')
    either = found[(_entity(digits), 'hasEitherX')]
    assert (either.component, either.value, either.value_datatype) == ('OrConstraintComponent', '80', UNTYPED)
    assert either.datatypes == (DOUBLE, INTEGER)
    double = found[(_entity(digits), 'hasDoubleX')]
    assert (double.component, double.datatypes) == ('DatatypeConstraintComponent', (DOUBLE,))
    [boolean] = _rows(lambda v: v['datatype'] == 'boolean')
    assert found[(_entity(boolean), 'hasEitherX')].value_datatype == BOOLEAN


def test_the_probe_package_cross_checks_with_only_expected_differences(probe):
    """Task 4.2 of #958 again: every number agrees, and the strings and the
    sh:or naming are listed as expected, each with its reason."""
    from semforge.validate import validate_package

    ok, reason = available(SHACL2FLINK, COMPILER_PYTHON)
    if not ok:
        pytest.skip(f'the cross-check cannot run here: {reason}')
    found = cross_check(probe, validate_package(probe, strict=False), SHACL2FLINK,
                        python_exe=COMPILER_PYTHON)
    unexpected = [str(d) for d in found if d.code != 'SF-XCHK-EXPECTED']
    assert unexpected == []
    probes = [d for d in found if d.subject.startswith('urn:probe:')]
    assert {_named(d) for d in probes} == _expected_probe_differences()
    assert len(probes) == len(_expected_probe_differences())
    assert all('expected, not a compiler bug' in d.message for d in probes)
    assert all(('judged by their text' in d.message) != ('sh:or of datatypes' in d.message)
               for d in probes)


# --- the command ----------------------------------------------------------

def test_the_command_says_the_sql_agrees_when_every_difference_is_expected(corpus_path, monkeypatch):
    from semforge.cli import main

    note = Diagnostic(code='SF-XCHK-EXPECTED', category='divergence', severity='info',
                      subject='urn:e:1', message='a reason -- expected, not a compiler bug')
    monkeypatch.setattr(main, 'cross_check_sqlite', lambda *args: [note])
    result = CliRunner().invoke(main.cli, ['validate', corpus_path, '--cross-check', 'sqlite'])
    assert 'SF-XCHK-EXPECTED' in result.output
    assert 'the compiled SQL agrees with pyshacl' in result.output


def test_the_command_does_not_say_so_with_a_real_difference(corpus_path, monkeypatch):
    from semforge.cli import main

    notes = [Diagnostic(code=code, category='divergence', severity=severity, subject='urn:e:1',
                        message='m') for code, severity in
             (('SF-XCHK-EXPECTED', 'info'), ('SF-XCHK-EXTRA', 'warning'))]
    monkeypatch.setattr(main, 'cross_check_sqlite', lambda *args: notes)
    result = CliRunner().invoke(main.cli, ['validate', corpus_path, '--cross-check', 'sqlite'])
    assert 'SF-XCHK-EXTRA' in result.output
    assert 'agrees' not in result.output


def test_a_missing_compiler_names_the_option_that_finds_it(tmp_path):
    ok, reason = available(str(tmp_path / 'nowhere'))
    assert not ok and '--shacl2flink <path>' in reason


def test_a_relative_compiler_path_is_taken_from_where_it_was_given(probe, monkeypatch):
    """The build runs in a temporary directory; a relative --shacl2flink
    must not resolve there."""
    from semforge.target import crosscheck

    seen = []

    def available(directory, python):
        seen.append(directory)
        return False, 'not here'

    monkeypatch.setattr(crosscheck, 'available', available)
    monkeypatch.chdir(os.path.dirname(SHACL2FLINK))
    crosscheck.cross_check(probe, None, 'shacl2flink')
    assert seen == [SHACL2FLINK]


def test_what_a_result_records_of_a_value_and_its_constraint():
    from rdflib import Graph, Literal, URIRef

    from semforge.validate.adapters.pyshacl_adapter import _admitted_datatypes, _value

    assert _value(Literal('80')) == ('80', UNTYPED)
    assert _value(Literal('80', lang='en')) == ('80', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#langString')
    assert _value(Literal(80)) == ('80', INTEGER)
    assert _value(URIRef('urn:x')) == ('', '')
    assert _value(None) == ('', '')

    shapes = Graph().parse(format='turtle', data='''
        @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        <urn:s:datatypes> sh:or ( [ sh:datatype xsd:double ] [ sh:datatype xsd:integer ] ) .
        <urn:s:mixed> sh:or ( [ sh:datatype xsd:double ] [ sh:class <urn:c:C> ] ) ; sh:datatype xsd:string .
        <urn:s:bounded> sh:or ( [ sh:datatype xsd:integer ; sh:maxInclusive 100 ] [ sh:datatype xsd:boolean ] ) .
        <urn:s:named> sh:or ( [ sh:datatype xsd:integer ; sh:name "n" ; sh:message "m" ] [ sh:datatype xsd:double ] ) .
    ''')
    assert _admitted_datatypes('OrConstraintComponent', URIRef('urn:s:datatypes'), shapes) == (DOUBLE, INTEGER)
    assert _admitted_datatypes('OrConstraintComponent', URIRef('urn:s:mixed'), shapes) == ()
    assert _admitted_datatypes('DatatypeConstraintComponent', URIRef('urn:s:mixed'), shapes) == (STRING,)
    assert _admitted_datatypes('ClassConstraintComponent', URIRef('urn:s:mixed'), shapes) == ()
    assert _admitted_datatypes('DatatypeConstraintComponent', None, shapes) == ()
    # a branch that constrains more than the datatype: "500" fails it whatever its text
    assert _admitted_datatypes('OrConstraintComponent', URIRef('urn:s:bounded'), shapes) == ()
    assert _admitted_datatypes('OrConstraintComponent', URIRef('urn:s:named'), shapes) == (DOUBLE, INTEGER)


def test_a_bounded_branch_keeps_its_violation_a_difference():
    """sh:or ( [sh:datatype xsd:integer; sh:maxInclusive 100] [sh:datatype xsd:boolean] ) with the
    string "500": its text is an integer, but the bound rejects it too, so it is no D5 divergence."""
    from rdflib import Graph, URIRef

    from semforge.validate.adapters.pyshacl_adapter import _admitted_datatypes

    shapes = Graph().parse(format='turtle', data='''
        @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        <urn:s:bounded> sh:or ( [ sh:datatype xsd:integer ; sh:maxInclusive 100 ] [ sh:datatype xsd:boolean ] ) .
    ''')
    admitted = _admitted_datatypes('OrConstraintComponent', URIRef('urn:s:bounded'), shapes)
    [found] = compare([], [_result('hasX', 'OrConstraintComponent', '500', UNTYPED, admitted)])
    assert found.code == 'SF-XCHK-EXTRA'


def test_a_declared_string_is_recorded_as_declared():
    from rdflib import Literal
    from rdflib.namespace import XSD as RDFLIB_XSD

    from semforge.validate.adapters.pyshacl_adapter import _value

    assert _value(Literal('80.0', datatype=RDFLIB_XSD.string)) == ('80.0', STRING)
    assert _value(Literal('80.0')) == ('80.0', UNTYPED)


def test_a_sqlite3_without_regexp_makes_the_check_unavailable(monkeypatch):
    """Skipped, not failed: without its PCRE extension sqlite3 cannot load
    the generated SQL, and that is a reason the check cannot run."""
    from semforge.target import crosscheck

    monkeypatch.setattr(crosscheck, 'regexp_available', lambda: False)
    ok, reason = crosscheck.available(SHACL2FLINK, COMPILER_PYTHON)
    if 'oxrdflib' in reason or 'sqlite3 command' in reason:
        pytest.skip(reason)
    assert not ok and 'REGEXP' in reason
