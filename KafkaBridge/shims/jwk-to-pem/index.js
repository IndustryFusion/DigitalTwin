/**
* Copyright (c) 2026 Intel Corporation
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

// keycloak-connect only uses jwk-to-pem to turn the realm's JWKS keys into
// PEM for crypto.verify. node:crypto imports JWK natively, so the upstream
// package (and its elliptic dependency) is not needed.
const crypto = require('crypto');

module.exports = function jwkToPem (jwk, options) {
  if (!jwk || typeof jwk !== 'object') {
    throw new TypeError('Expected "jwk" to be an Object');
  }
  if (options && options.private) {
    return crypto.createPrivateKey({ key: jwk, format: 'jwk' })
      .export({ type: 'pkcs8', format: 'pem' });
  }
  const { d, p, q, dp, dq, qi, ...publicJwk } = jwk;
  return crypto.createPublicKey({ key: publicJwk, format: 'jwk' })
    .export({ type: 'spki', format: 'pem' });
};
