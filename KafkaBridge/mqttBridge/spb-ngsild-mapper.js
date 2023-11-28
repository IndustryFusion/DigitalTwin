/**
* Copyright (c) 2017, 2020 Intel Corporation
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

/* Example. NGSI-LD format for Relationship"
*
{
    “id”: “urn:plasmacutter:1\\https://industry-fusion.com/types/v0.9/hasFilter”,
    “entityId”: “urn:plasmacutter:1”,
    “name”: “https://industry-fusion.com/types/v0.9/hasFilter”,
    “type”: “https://uri.etsi.org/ngsi-ld/Relationship”,
    “https://uri.etsi.org/ngsi-ld/hasObject”: “urn:filter:1”,
    “nodeType”: “@id”,
    “index”: 0
}
*/

/**
 *  Example Received metric:
 *
 * {"timestamp":1655974018778,"
metrics":
    [{
    "name":"relationship/https://industry-fusion.com/types/v0.9/hasFilter",
    "alias":"fbb3b7cd-a5ff-491b-ad61-d43edf513b7a",
    "timestamp":1655974018777,
    "dataType":"string",
    "value":"urn:filter:1"}],
"seq":2},

 */

const etsiNgsiRelationshipUrl = 'https://uri.etsi.org/ngsi-ld/Relationship';
const etsiNgsiPropertysUrl = 'https://uri.etsi.org/ngsi-ld/Property';

module.exports.mapSpbRelationshipToKafka = function (deviceId, metric) {
  const originalName = metric.name.substr(metric.name.indexOf('/') + 1);
  const mappedKafkaMessage = {
    id: deviceId + '\\' + originalName,
    entityId: deviceId,
    name: originalName,
    type: etsiNgsiRelationshipUrl,
    'https://uri.etsi.org/ngsi-ld/hasObject': metric.value,
    nodeType: '@id',
    index: 0
  };
  return mappedKafkaMessage;
};

module.exports.mapSpbPropertyToKafka = function (deviceId, metric) {
  const originalName = metric.name.substr(metric.name.indexOf('/') + 1);
  const mappedPropKafkaMessage = {
    id: deviceId + '\\' + originalName,
    entityId: deviceId,
    nodeType: '@value',
    name: originalName,
    type: etsiNgsiPropertysUrl,
    'https://uri.etsi.org/ngsi-ld/hasValue': metric.value,
    index: 0
  };
  return mappedPropKafkaMessage;
};
