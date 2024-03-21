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
from bunch import Bunch
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
    mock_configs.attributes_table_obj_name = 'attributes'
    mock_configs.rdf_table_obj_name = 'rdf'
    mock_configs.attributes_view_obj_name = 'attributes-view'
    sh = Namespace("http://www.w3.org/ns/shacl#")
    targetclass = MagicMock()
    targetclass.toPython.return_value = 'targetclass'
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
    g.__iadd__.return_value.query.return_value = [Bunch()]
    g.__iadd__.return_value.query.return_value[0].targetclass = targetclass
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
    prefixes = {"sh": "http://example.com/sh", "base": "http://example.com/base"}
    sqlite, (statementsets, tables, views) = \
        lib.shacl_properties_to_sql.translate('kms/shacl.ttl',
                                              'kms/knowledge.ttl', prefixes)

    assert tables == ['alerts-bulk', 'attributes', 'rdf', 'targetclass',
                      'attributeclass']
    assert views == ['attributes-view', 'targetclass-view',
                     'attributeclass-view']
    assert len(statementsets) == 2
    lower_sqlite = sqlite.lower()
    assert lower_sqlite.count('select') == 13
    assert lower_sqlite.count(' < 4') == 4
    assert lower_sqlite.count(' < 3') == 3
    assert lower_sqlite.count(' <= 2') == 3
    assert lower_sqlite.count(' > 0') == 3
    assert lower_sqlite.count(' >= 1') == 3
    assert lower_sqlite.count("regexp 'pattern'") == 2
    assert lower_sqlite.count("('shin1', 'shin2')") == 2
    assert lower_sqlite.count("inconstraintcomponent") == 1

    targetclass = MagicMock()
    targetclass.toPython.return_value = 'targetclass'
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
    g.__iadd__.return_value.query.return_value = [Bunch()]
    g.__iadd__.return_value.query.return_value[0].targetclass = targetclass
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
    g.__iadd__.return_value.query.return_value[0].ins = None

    sqlite, (statementsets, tables, views) = \
        lib.shacl_properties_to_sql.translate('kms/shacl.ttl',
                                              'kms/knowledge.ttl', prefixes)

    assert tables == ['alerts-bulk', 'attributes', 'rdf', 'targetclass',
                      'attributeclass']
    assert views == ['attributes-view', 'targetclass-view',
                     'attributeclass-view']
    assert len(statementsets) == 2
    lower_sqlite = sqlite.lower()
    assert lower_sqlite.count('select') == 10
    assert lower_sqlite.count('> 10') == 3
    assert lower_sqlite.count('< 3') == 3
