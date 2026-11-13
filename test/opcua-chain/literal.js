/**
* Copyright (c) 2026 IndustryFusion Foundation
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

// A property value as a reader of the NGSI-LD API means it (contracts/typed-literals,
// #961, design D6). A double is written declared, {"@value": 80.0, "@type": xsd:double},
// and the broker returns it as an object, its @type compacted to `type`. A merge keeps the
// stored type, so a live value -- even one sent as a string -- comes back as
// {"type": "…#double", "@value": "42.5"}; a replacing update drops it again. Whatever the
// form, the reader gets the plain value: the number for a declared number.
'use strict';

const NUMERIC = /#(double|float|decimal|integer|int|long|short)$/;

function literalValue (value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value) || !('@value' in value)) {
    return value;
  }
  const inner = value['@value'];
  const type = value['@type'] || value.type || '';
  if (typeof inner === 'string' && NUMERIC.test(type) && inner.trim() !== '' && !isNaN(Number(inner))) {
    return Number(inner);
  }
  return inner;
}

module.exports = { literalValue };

// node literal.js: check the three forms of the specification's scenarios.
if (require.main === module) {
  const DOUBLE = 'http://www.w3.org/2001/XMLSchema#double';
  const cases = [
    [{ type: DOUBLE, '@value': 42.5 }, 42.5, 'a declared value read back'],
    [{ type: DOUBLE, '@value': '42.5' }, 42.5, 'a live string merged onto a declared value'],
    [42.5, 42.5, 'a plain value'],
    [{ '@type': DOUBLE, '@value': 0 }, 0, 'expanded form, zero'],
    [{ '@id': 'urn:x' }, { '@id': 'urn:x' }, 'an IRI stays as it is'],
    ['with "quotes"', 'with "quotes"', 'a string stays as it is']
  ];
  let failed = 0;
  for (const [input, want, name] of cases) {
    const got = literalValue(input);
    const ok = JSON.stringify(got) === JSON.stringify(want);
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}`);
    if (!ok) failed++;
  }
  process.exit(failed ? 1 : 0);
}
