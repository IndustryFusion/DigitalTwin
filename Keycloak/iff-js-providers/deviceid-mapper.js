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
var deviceIdH = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-DeviceID")[0];
var inputRequest = keycloakSession.getContext().getHttpRequest();
var params = inputRequest.getDecodedFormParameters();
var grantType = params.getFirst("grant_type");
var  deviceIdS = userSession.getNote('deviceId');
if (deviceIdS !== null && deviceIdS !== undefined) {
    if (deviceIdH !== null && deviceIdH !== undefined) {
        if (deviceIdH === deviceIdS) {
            // You get only a device_id claim when you know who you are
            exports = deviceIdS;
        } else {
            print("Warning: Rejecting device_id claim: Mismatch between stored device_id and header. device_id is now tainted.")
            userSession.setNote('deviceId', 'TAINTED');
            exports = 'TAINTED'
        }
    } else {
        exports = deviceIdS;        
    }
} else {
    if (deviceIdH !== null && deviceIdH !== undefined) {
        userSession.setNote('deviceId', deviceIdH);
        exports = deviceIdH;
    } else if (grantType == 'refresh_token') {
        // Refreshing without assigning deviceId? Token is tainted. Forget it.
        print("Warning: Refreshing token without device_id. device_id is now tainted. You cannot use the token any longer.")
        userSession.setNote('deviceId', 'TAINTED');
        exports = 'TAINTED'
    }
}