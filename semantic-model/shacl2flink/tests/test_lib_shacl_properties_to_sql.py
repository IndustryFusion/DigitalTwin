#
# Copyright (c) 2022 Intel Corporation
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

from unittest.mock import MagicMock, patch
import lib.shacl_properties_to_sql
import lib.utils as utils
import lib.configs as configs
from munch import Munch
from rdflib import Namespace


@patch('lib.shacl_properties_to_sql.Graph')
@patch('lib.shacl_properties_to_sql.ruamel.yaml')
@patch('lib.shacl_properties_to_sql.configs')
@patch('lib.shacl_properties_to_sql.utils')
def test_lib_shacl_prroperties_to_sql(mock_utils, mock_configs, mock_yaml,
                                      mock_graph):
    def identity(klass):
        return klass
    mock_utils.strip_class = identity
    mock_utils.class_to_obj_name = identity
    mock_utils.camelcase_to_snake_case = identity
    mock_utils.init_constraint_check = utils.init_constraint_check
    mock_utils.add_table_values.return_value = ['value']

    mock_configs.attributes_table_obj_name = 'attributes'
    mock_configs.rdf_table_obj_name = 'rdf'
    mock_configs.attributes_view_obj_name = 'attributes-view'
    mock_configs.kafka_topic_ngsi_prefix_name = 'ngsild-prefix'
    mock_configs.constraint_combination_table_object_name = configs.constraint_combination_table_object_name
    mock_configs.constraint_trigger_table_object_name = configs.constraint_trigger_table_object_name
    mock_configs.constraint_table_object_name = configs.constraint_table_object_name
    sh = Namespace("http://www.w3.org/ns/shacl#")
    targetclass = MagicMock()
    targetclass.toPython.return_value = 'targetclass'
    inheritedTargetclass = MagicMock()
    inheritedTargetclass.toPython.return_value = 'inheritedTargetclass'
    propertypath = MagicMock()
    propertypath.toPython.return_value = 'propertypath'
    attributeclass = MagicMock()
    attributeclass.toPython.return_value = 'attributeclass'
    mincount = MagicMock()
    mincount.toPython.return_value = 4
    maxcount = MagicMock()
    maxcount.toPython.return_value = None
    g = mock_graph.return_value
    severitycode = MagicMock()
    severitycode.toPython.return_value = 'severitycode'
    nodeshape = MagicMock()
    nodeshape.toPython.return_value = 'nodeshape'
    minexclusive = MagicMock()
    minexclusive.toPython.return_value = 0
    maxexclusive = MagicMock()
    maxexclusive.toPython.return_value = 3
    mininclusive = MagicMock()
    mininclusive.toPython.return_value = 1
    maxinclusive = MagicMock()
    maxinclusive.toPython.return_value = 2
    minlength = MagicMock()
    minlength.toPython.return_value = None
    maxlength = MagicMock()
    maxlength.toPython.return_value = None
    pattern = MagicMock()
    pattern.toPython.return_value = 'pattern'
    ins = MagicMock()
    ins.toPython.return_value = '"SHIN1","SHIN2"'
    property = MagicMock()
    property.toPython.return_value = 'property'
    valuepath = MagicMock()
    valuepath.toPython.return_value = 'valuepath'
    datatypes = MagicMock()
    datatypes.toPython.return_value = 'datatypes'
    hasValue = MagicMock()
    hasValue.toPython.return_value = 'hasValue'
    g.__iadd__.return_value.query.return_value = [Munch()]
    g.__iadd__.return_value.query.return_value[0].targetclass = targetclass
    g.__iadd__.return_value.query.return_value[0].inheritedTargetclass = inheritedTargetclass
    g.__iadd__.return_value.query.return_value[0].propertypath = propertypath
    g.__iadd__.return_value.query.return_value[0].attributeclass = \
        attributeclass
    g.__iadd__.return_value.query.return_value[0].mincount = mincount
    g.__iadd__.return_value.query.return_value[0].maxcount = maxcount
    g.__iadd__.return_value.query.return_value[0].severitycode = severitycode
    g.__iadd__.return_value.query.return_value[0].nodeshape = nodeshape
    g.__iadd__.return_value.query.return_value[0].nodekind = sh.Literal
    g.__iadd__.return_value.query.return_value[0].minexclusive = minexclusive
    g.__iadd__.return_value.query.return_value[0].maxexclusive = maxexclusive
    g.__iadd__.return_value.query.return_value[0].mininclusive = mininclusive
    g.__iadd__.return_value.query.return_value[0].maxinclusive = maxinclusive
    g.__iadd__.return_value.query.return_value[0].minlength = minlength
    g.__iadd__.return_value.query.return_value[0].maxlength = maxlength
    g.__iadd__.return_value.query.return_value[0].pattern = pattern
    g.__iadd__.return_value.query.return_value[0].ins = ins
    g.__iadd__.return_value.query.return_value[0].property = property
    g.__iadd__.return_value.query.return_value[0].valuepath = valuepath
    g.__iadd__.return_value.query.return_value[0].datatypes = datatypes
    g.__iadd__.return_value.query.return_value[0].hasValue = hasValue

    g.value.side_effect = ['value1']
    g.subjects.side_effect = [[iter([])]]
    prefixes = {"sh": "http://example.com/sh", "base": "http://example.com/base"}
    with patch('lib.shacl_properties_to_sql.get_full_path_of_shacl_property', return_value=['mocked_full_path']):
        sqlite, (statementsets, tables, views, constraints) = \
            lib.shacl_properties_to_sql.translate('kms/shacl.ttl',
                                                  'kms/knowledge.ttl', prefixes)

    assert tables == ['alerts-bulk', 'attributes', 'rdf', 'ngsild-prefix', 'constraint-table',
                      'constraint-combination-table', 'constraint-trigger-table', 'constraint-table']
    assert views == ['attributes-view', 'ngsild-prefix-view']
    assert len(statementsets) == 4
    assert constraints == ['value', 'value']

    targetclass = MagicMock()
    targetclass.toPython.return_value = 'targetclass'
    ins = MagicMock()
    ins.toPython.return_value = 'ins'
    propertypath = MagicMock()
    propertypath.toPython.return_value = 'propertypath'
    attributeclass = MagicMock()
    attributeclass.toPython.return_value = 'attributeclass'
    mincount = MagicMock()
    mincount.toPython.return_value = 0
    maxcount = MagicMock()
    maxcount.toPython.return_value = 3
    g = mock_graph.return_value
    severitycode = MagicMock()
    severitycode.toPython.return_value = 'severitycode'
    nodeshape = MagicMock()
    nodeshape.toPython.return_value = 'nodeshape'
    minexclusive = MagicMock()
    minexclusive.toPython.return_value = None
    maxexclusive = MagicMock()
    maxexclusive.toPython.return_value = None
    mininclusive = MagicMock()
    mininclusive.toPython.return_value = None
    maxinclusive = MagicMock()
    maxinclusive.toPython.return_value = None
    minlength = MagicMock()
    minlength.toPython.return_value = 3
    maxlength = MagicMock()
    maxlength.toPython.return_value = 10
    datatypes = MagicMock()
    datatypes.toPython.return_value = ''
    g.__iadd__.return_value.query.return_value = [Munch()]
    g.__iadd__.return_value.query.return_value[0].targetclass = targetclass
    g.__iadd__.return_value.query.return_value[0].inheritedTargetclass = inheritedTargetclass
    g.__iadd__.return_value.query.return_value[0].propertypath = propertypath
    g.__iadd__.return_value.query.return_value[0].attributeclass = \
        attributeclass
    g.__iadd__.return_value.query.return_value[0].mincount = mincount
    g.__iadd__.return_value.query.return_value[0].maxcount = maxcount
    g.__iadd__.return_value.query.return_value[0].severitycode = severitycode
    g.__iadd__.return_value.query.return_value[0].nodeshape = nodeshape
    g.__iadd__.return_value.query.return_value[0].nodekind = sh.IRI
    g.__iadd__.return_value.query.return_value[0].minexclusive = minexclusive
    g.__iadd__.return_value.query.return_value[0].maxexclusive = maxexclusive
    g.__iadd__.return_value.query.return_value[0].mininclusive = mininclusive
    g.__iadd__.return_value.query.return_value[0].maxinclusive = maxinclusive
    g.__iadd__.return_value.query.return_value[0].minlength = minlength
    g.__iadd__.return_value.query.return_value[0].maxlength = maxlength
    g.__iadd__.return_value.query.return_value[0].pattern = None
    g.__iadd__.return_value.query.return_value[0].ins = ins
    g.__iadd__.return_value.query.return_value[0].property = property
    g.__iadd__.return_value.query.return_value[0].valuepath = None
    g.__iadd__.return_value.query.return_value[0].datatypes = datatypes
    g.__iadd__.return_value.query.return_value[0].hasValue = None

    with patch('lib.shacl_properties_to_sql.get_full_path_of_shacl_property',
               return_value=['mocked_full_path']):
        sqlite, (statementsets, tables, views, constraints) = \
            lib.shacl_properties_to_sql.translate('kms/shacl.ttl',
                                                  'kms/knowledge.ttl',
                                                  prefixes)

    assert tables == ['alerts-bulk', 'attributes', 'rdf', 'ngsild-prefix', 'constraint-table',
                      'constraint-combination-table', 'constraint-trigger-table', 'constraint-table']
    assert views == ['attributes-view', 'ngsild-prefix-view']
    assert len(statementsets) == 4
    assert constraints == ['value', 'value']
