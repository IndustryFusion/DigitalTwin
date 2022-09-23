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

var USER = "user";
var DEVICE = "device";
var context = $evaluation.getContext();
var identity = context.getIdentity();
var attributes = identity.getAttributes();
var type = attributes.getValue('type').asString(0);
var accessToken = identity.getAccessToken();
var otherClaims = accessToken.getOtherClaims();
var accounts = otherClaims.get('accounts');
var permission = $evaluation.getPermission();
var path = permission.getClaims().get('accessed-endpoint').toArray()[0];
var accountIdRegExp = new RegExp("/api/accounts/(.[^/]*)");
var accountId = accountIdRegExp.exec(path);

if (accountId && type === USER) {
    var grantAccess = false;
    accountId = accountId[1];
    accounts.forEach(function(account) {
        if (account.id === accountId) {
            grantAccess = true;
        }
    });
    if (grantAccess) {
        $evaluation.grant();
    } else {
        $evaluation.deny();
    }
} else if(!accountId && type === DEVICE) {
    $evaluation.grant();
} else {
    $evaluation.deny();
}
