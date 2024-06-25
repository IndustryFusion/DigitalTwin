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
var subdeviceIdsH = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-SubDeviceIDs")[0];
if (subdeviceIdsH !== null && subdeviceIdsH !== undefined) {
    subdeviceIdsH = JSON.parse(subdeviceIdsH)
}
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
    var origTokenSubDeviceIds;
    if (otherClaims !== null) {
        
        origTokenSubDeviceIds = otherClaims.get("sub_device_ids");
    }
    var origTokenSession = origToken.getSessionId();

    if (origTokenSubDeviceIds !== null && origTokenSubDeviceIds !== undefined) {
        // Has origToken same session?
        if (origTokenSession !== session) {
            print("Warning: Rejecting subdeviceids claim due to session mismatch between refresh_token and orig_token")
            exports = JSON.stringify([]);
        } else {
            exports = origTokenSubDeviceIds;
        }
    } else {
        // If there is no origTokenDeviceId, there must be an X-DeviceId header AND origToken must be valid
        if (!origToken.isExpired() && subdeviceIdsH !== null && subdeviceIdsH !== undefined) {
            exports = subdeviceIdsH
        } else {
            print("Warning: Rejecting subdeviceid claim due to orig_token is expired or there is not valid X-SubDeviceIDs Header.")
            exports = JSON.stringify([]);
        }   
    }
} else if (grantType === 'password'){
    var currentTimeInSeconds = new Date().getTime() / 1000;
    token.exp(currentTimeInSeconds + onboarding_token_expiration);
    exports = null
} else if (origToken === null) {
    print("Warning: Rejecting token due to invalid orig_token.")
    exports = JSON.stringify([])
}
