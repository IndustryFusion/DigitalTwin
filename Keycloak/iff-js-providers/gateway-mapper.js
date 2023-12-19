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

var tainted = 'TAINTED';
var gatewayIdH = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-GatewayID")[0];
var inputRequest = keycloakSession.getContext().getHttpRequest();
var params = inputRequest.getDecodedFormParameters();
var origTokenParam = params.getFirst("orig_token");
var grantType = params.getFirst("grant_type");
if (grantType === 'refresh_token') {
    var tokens = keycloakSession.tokens();
    var session = userSession.getId();
    var origToken = tokens.decode(origTokenParam, Java.type("org.keycloak.representations.AccessToken").class)
    var origTokenGatewayId = origToken.getOtherClaims().get("gateway");
    var origTokenSession = origToken.getSessionId();

    if (origTokenGatewayId !== null && origTokenGatewayId !== undefined) {
        // Has origToken same session?
        if (origTokenSession !== session) {
            print("Warning: Rejecting token due to session mismatch between refresh_token and orig_token")
            exports = tainted;
        } else {
            exports = origTokenGatewayId;
        }
    } else {
        // If there is no origTokenGatewayId, there must be an X-GatewayId header AND origToken must be valid
        if (!origToken.isExpired() && gatewayIdH !== null && gatewayIdH !== undefined) {
            exports = gatewayIdH
        } else {
            print("Warning: Rejecting token due to orig_token is expired or there is not valid X-GatewayId Header.")
            exports = tainted;
        }   
    }
}

