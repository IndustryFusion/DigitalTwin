/**
 * Copyright (c) 2023 Intel Corporation
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

var gatewayIdH = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-GatewayID")[0];
var gatewayIdS = userSession.getNote('gatewayId');
var grantType = params.getFirst("grant_type");
if (gatewayIdS !== null && gatewayIdS !== undefined) {
    if (gatewayIdH !== null && gatewayIdH !== undefined) {
        if (gatwayIdH === gatewayIdS) {
            // You get only gateway_id claim when you know who you are
            exports = gatewayIdS;
        } else {
            print("Warning: Rejecting gateway_id claim: Mismatch between stored gateway_id and header.")
        }
    } else {
        exports = gatewayIdS;        
    }
} else {
    if (gatewayIdH !== null && gatewayIdH !== undefined) {
        userSession.setNote('gatewayId', gatewayIdH);
        exports = gatewayIdH;
    } else if (grantType == 'refresh_token') {
        // Refreshing without assigning gatewayId? Token is tainted. Forget it.
        userSession.setNote('gatewayId', 'TAINTED');
        exports = 'TAINTED'
    }
}
