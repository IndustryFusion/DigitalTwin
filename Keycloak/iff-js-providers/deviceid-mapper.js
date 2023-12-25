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

var onboarding_token_expiration = java.lang.System.getenv("OISP_FRONTEND_DEVICE_ACCOUNT_ENDPOINT");
var tainted = 'TAINTED';
exports = tainted;
var deviceIdH = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-DeviceID")[0];
var inputRequest = keycloakSession.getContext().getHttpRequest();
var params = inputRequest.getDecodedFormParameters();
var origTokenParam = params.getFirst("orig_token");
var grantType = params.getFirst("grant_type");
var tokens = keycloakSession.tokens();
var origToken = tokens.decode(origTokenParam, Java.type("org.keycloak.representations.AccessToken").class)

if (typeof(onboarding_token_expiration) !== 'number') {
    // if not otherwise configured onboardig token is valid for 5 minutes
    onboarding_token_expiration = 300;
}
if (grantType === 'refresh_token' && origToken !== null) {
    var session = userSession.getId();
    var otherClaims = origToken.getOtherClaims();
    var origTokenDeviceId;
    if (otherClaims !== null) {
        
        origTokenDeviceId = otherClaims.get("device_id");
    }
    var origTokenSession = origToken.getSessionId();

    if (origTokenDeviceId !== null && origTokenDeviceId !== undefined) {
        // Has origToken same session?
        if (origTokenSession !== session) {
            print("Warning: Rejecting token due to session mismatch between refresh_token and orig_token")
            exports = tainted;
        } else {
            exports = origTokenDeviceId;
        }
    } else {
        // If there is no origTokenDeviceId, there must be an X-DeviceId header AND origToken must be valid
        if (!origToken.isExpired() && deviceIdH !== null && deviceIdH !== undefined) {
            exports = deviceIdH
        } else {
            print("Warning: Rejecting token due to orig_token is expired or there is not valid X-DeviceId Header.")
            exports = tainted;
        }   
    }
} else if (grantType === 'password'){
    var currentTimeInSeconds = new Date().getTime() / 1000;
    token.exp(currentTimeInSeconds + onboarding_token_expiration);
    exports = null
} else if (origToken === null) {
    print("Warning: Rejecting token due to invalid orig_token.")
    exports = tainted
}
