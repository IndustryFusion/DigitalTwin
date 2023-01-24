/**
 * Copyright (c) 2020 Intel Corporation
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

var HttpGet = Java.type("org.apache.http.client.methods.HttpGet");
var HttpClientBuilder = Java.type("org.apache.http.impl.client.HttpClientBuilder");
var RequestConfig = Java.type("org.apache.http.client.config.RequestConfig");
var EntityUtils = Java.type("org.apache.http.util.EntityUtils");

var TIMEOUT = 5 * 1000;
var LEGACY_UID = "legacy_app_uid";
var USER = "user";
var DEVICE = "device";
var DEVICE_ENDPOINT_ENV = "OISP_FRONTEND_DEVICE_ACCOUNT_ENDPOINT";
var USER_ENDPOINT_ENV = "OISP_FRONTEND_USER_ACCOUNT_ENDPOINT";
var SECRET = java.lang.System.getenv("OISP_FRONTEND_SECRET");
var placeholder = "placeholder@placeholder.org";
var placeholderActivationCode = 'placeholder';

function httpGet(url) {
    var ret = { data: "[]", statusCode: 500 };
    var config = RequestConfig.custom()
        .setConnectTimeout(TIMEOUT)
        .setConnectionRequestTimeout(TIMEOUT)
        .setSocketTimeout(TIMEOUT)
        .build();
    var httpClient = HttpClientBuilder.create().setDefaultRequestConfig(config).build();
    try {
        var request = new HttpGet(url);
        request.addHeader("Authorization", "Basic " + SECRET);
        var response = httpClient.execute(request);
        try {
            var responseCode = response.getStatusLine().getStatusCode();
            var entity = response.getEntity();
            if (entity) {
                var result = EntityUtils.toString(entity);
                ret = { data: result, statusCode: responseCode };
            }
         } catch(err) {
            print("Error Response: Can't get accounts - ", err);
        }
        response.close();
    } catch(err) {
        print("Error Http Client: Can't get accounts - ", err);
    }
    httpClient.close();
    return ret;
}

var accessType = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-Access-Type");
if (accessType.length > 0) {
    accessType = accessType[0];
}

var path;
if (accessType && accessType === DEVICE) {
    path = java.lang.System.getenv(DEVICE_ENDPOINT_ENV);
    var activationCode = keycloakSession.getContext().getRequestHeaders()
        .getRequestHeader("X-Activation-Code");
    if (activationCode.length > 0) {
        activationCode = activationCode[0];
    } else if (user.username === placeholder) {
        activationCode = placeholderActivationCode;
    } else {
        activationCode = "invalid";
    }
    path = path.replace(":activationCode", activationCode);
    var deviceUID = keycloakSession.getContext().getRequestHeaders()
        .getRequestHeader("X-DeviceUID")[0];
    path = path.replace(":deviceUID", deviceUID);
} else {
    path = java.lang.System.getenv(USER_ENDPOINT_ENV);
    var userId = user.id;
    var legacyUID = user.getFirstAttribute(LEGACY_UID);
    if (legacyUID) {
        userId = legacyUID;
    }
    path = path.replace(":userId", userId);
}

var res = httpGet(path);
print("Accounts for: ", path, " - ", JSON.stringify(res));
exports = res.data;
