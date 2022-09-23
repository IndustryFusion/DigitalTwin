/**
 * Copyright (c) 2022 Intel Corporation
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

/**
 * Available variables:
 * user - the current user
 * realm - the current realm
 * token - the current token
 * userSession - the current userSession
 * keycloakSession - the current keycloakSession
 */

var DEVICE = "device";
var USER = "user";

var accessType = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-Access-Type");
if (accessType.length > 0) {
    accessType = accessType[0];
} else {
    accessType = USER;
}

var gatewayId = "";

// Set type and subject id
if (accessType === DEVICE) {
    gatewayId = keycloakSession.getContext().getRequestHeaders()
        .getRequestHeader("X-GatewayId")[0];
}

exports = gatewayId;
