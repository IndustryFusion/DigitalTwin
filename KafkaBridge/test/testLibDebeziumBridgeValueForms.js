/**
* Copyright (c) 2026 IndustryFusion Foundation
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/
'use strict';

// The forms the bridge gives values, which shacl2flink's datatype check is tested with (valueForms.json, #1097).
const { assert } = require('chai');
const rewire = require('rewire');
const ToTest = rewire('../lib/debeziumBridge.js');
const { forms } = require('./valueForms.json');

const NAME = 'https://example.org/attribute';

describe('The forms the bridge gives the values of an attribute', function () {
  let revert;
  before(function () {
    revert = ToTest.__set__('Logger', function () {
      return { debug: function () {}, error: function () {}, warn: function () {} };
    });
  });
  after(function () {
    revert();
  });

  forms.forEach(({ name, expanded, bridge }) => {
    it(name, function () {
      const debeziumBridge = new ToTest({ bridgeCommon: { hashLength: 24 } });
      const { attributes } = debeziumBridge.parseBeforeAfterEntity({
        id: 'urn:x:1',
        e_types: ['https://example.org/Type'],
        entity: JSON.stringify({ '@id': 'urn:x:1', '@type': ['https://example.org/Type'], [NAME]: [expanded] })
      });
      if (bridge === null) {
        assert.isUndefined(attributes[NAME]);
        return;
      }
      const { attributeValue, valueType, nodeType, type } = attributes[NAME][0];
      const form = { attributeValue, nodeType, type };
      if (valueType !== undefined) {
        form.valueType = valueType;
      }
      assert.deepEqual(form, bridge);
    });
  });
});
