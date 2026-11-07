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

// COPY of Core Services' output format. Core Services' Flink SQL turns the bridge's attributes into the
// update records of the ngsild-updates topic. The chain test doesn't run Flink, so this function writes those
// records by hand. It is the known gap of the test, stated in contracts/opcua-live-data: a change to Core
// Services, for instance to how it turns lowercase `true` into a boolean, isn't seen here. Keep it in step with
// the real output, which K8s tests still covers.
'use strict';

function toUpdate (attribute) {
  const attr = { observedAt: new Date().toISOString(), type: attribute.type, datasetId: '@none' };
  const value = attribute.attributeValue;
  if (attribute.nodeType === '@json') {
    attr.json = JSON.parse(value);
  } else if (attribute.nodeType === '@id') {
    attr.value = { '@id': value };
  } else if (/^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$/.test(value) || ['true', 'false', 'null'].includes(value)) {
    attr.value = JSON.parse(value);
  } else {
    attr.value = value;
  }
  return {
    op: 'update',
    overwriteOrReplace: true,
    noForward: true,
    entities: JSON.stringify([{ id: attribute.entityId, [attribute.name]: [attr] }])
  };
}

module.exports = { toUpdate };
