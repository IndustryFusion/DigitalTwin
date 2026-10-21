"""Several shapes on one attribute: one row, what holds when all apply.

SHACL conjoins every shape that targets an entity. The case that asked for
this: MachineShape says hasPressure is optional, a double, 0 <= x < 100;
MachineShape2 says it is required, a literal, x < 200. Together: required,
a double, 0 <= x < 100 -- and MachineShape2's "< 200" decides nothing.
"""

import pytest

from semforge.cooked.accumulate import accumulate
from semforge.cooked.typepage import build_type_page
from semforge.package import load
from semforge.package.scaffold import create_package


def _row(shape, attribute_params, value_params, **extra):
    parameters = [{'parameter': k, 'value': v, 'path': ['x:hasPressure'], 'layer': 'attribute'}
                  for k, v in attribute_params.items()]
    parameters += [{'parameter': k, 'value': v, 'path': ['x:hasPressure', 'ngsild:hasValue'],
                    'layer': 'value'} for k, v in value_params.items()]
    return dict({'label': 'hasPressure', 'kind': 'Property', 'path': ['x:hasPressure'],
                 'shapeName': shape, 'shape': f'https://x/{shape}', 'parameters': parameters,
                 'presence': '', 'value': '', 'verbatim': [], 'violations': [],
                 'tested': 'untested', 'inherited': False, 'valueEditable': True}, **extra)


def test_the_strictest_of_each_holds_and_the_rest_has_no_effect():
    one = _row('A', {'sh:minCount': '0', 'sh:maxCount': '1'},
               {'sh:datatype': 'xsd:double', 'sh:minInclusive': '0', 'sh:maxExclusive': '100'})
    two = _row('B', {'sh:minCount': '1', 'sh:maxCount': '1'},
               {'sh:nodeKind': 'sh:Literal', 'sh:maxExclusive': '200'})
    [row] = accumulate([one, two])
    assert row['presence'] == 'required · one'
    assert row['value'] == 'number · ≥ 0 and < 100'
    assert row['shapes'] == ['A', 'B'] and not row['notes']
    assert one['noEffect'] == ['sh:minCount 0']
    assert two['noEffect'] == ['sh:maxExclusive 200']


def test_at_an_equal_bound_the_exclusive_one_is_stricter():
    one = _row('A', {}, {'sh:maxInclusive': '100'})
    two = _row('B', {}, {'sh:maxExclusive': '100'})
    [row] = accumulate([one, two])
    assert '< 100' in row['value'] and one['noEffect'] == ['sh:maxInclusive 100']


@pytest.mark.parametrize('a, b, said', [
    ({'sh:datatype': 'xsd:double'}, {'sh:datatype': 'xsd:string'}, 'no literal has two datatypes'),
    ({'sh:minInclusive': '50'}, {'sh:maxInclusive': '10'}, 'admit no value'),
    ({'sh:minExclusive': '10'}, {'sh:maxInclusive': '10'}, 'admit no value'),
])
def test_a_contradiction_is_said(a, b, said):
    [row] = accumulate([_row('A', {}, a), _row('B', {}, b)])
    assert any(said in note for note in row['notes'])


def test_a_count_contradiction_is_said():
    [row] = accumulate([_row('A', {'sh:minCount': '2'}, {}), _row('B', {'sh:maxCount': '1'}, {})])
    assert any('admit nothing' in note for note in row['notes'])


def test_one_shape_leaves_the_row_as_it_was():
    single = _row('A', {'sh:minCount': '1'}, {}, presence='required', value='any value')
    assert accumulate([single]) == [single]


def test_a_conditional_shape_is_listed_not_merged():
    always = _row('A', {'sh:minCount': '0'}, {'sh:maxInclusive': '100'})
    sometimes = _row('B', {'sh:minCount': '1'}, {'sh:maxInclusive': '10'},
                     condition='only when it has hasValve', via='x:B', inherited=True)
    [row] = accumulate([always, sometimes])
    assert row['presence'] == 'any number' and '≤ 100' in row['value']
    assert row['contributions'] == [always, sometimes]


def test_the_user_s_two_machine_shapes(tmp_path):
    """The package as it was asked about, rebuilt in a scaffold."""
    root = str(tmp_path / 'my-model')
    create_package(root)
    from semforge.cooked.constrain import add_attribute_constraint
    from semforge.cooked.knowledge import add_attribute_term
    from semforge.cooked.shapes import add_shape
    from semforge.cooked.tree import add_constraint

    package = load(root)
    machine = next(str(c) for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    first = next(str(s) for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    add_attribute_term(package, 'hasPressure', 'Property', machine)
    add_attribute_constraint(load(root), first, 'hasPressure', required=False,
                             datatype='xsd:double')
    path = ['myModelEntities:hasPressure']
    add_constraint(load(root), first, path, 'sh:minInclusive', '0')
    add_constraint(load(root), first, path, 'sh:maxExclusive', '100')
    second = add_shape(load(root), 'MachineShape2', 'class', machine)['iri']
    add_attribute_constraint(load(root), second, 'hasPressure', required=True)
    add_constraint(load(root), second, path, 'sh:maxExclusive', '200')

    rows = build_type_page(load(root), machine)['attributes']
    pressure = [r for r in rows if r['label'] == 'hasPressure']
    assert len(pressure) == 1, 'one row for the attribute, not one per shape'
    row = pressure[0]
    assert row['presence'] == 'required · one'
    assert row['value'] == 'number · ≥ 0 and < 100'
    from semforge.cooked.shapes import base_name

    # By the name a reader reads: a new shape carries a random part.
    by_shape = {base_name(c['shapeName'].split(':')[-1]): c['noEffect']
                for c in row['contributions']}
    assert by_shape['MachineShape2'] == ['sh:maxExclusive 200']
