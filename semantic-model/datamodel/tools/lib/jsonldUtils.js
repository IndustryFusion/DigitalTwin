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
'use strict';
const url = require('url');
const fs = require('fs');
const ContextParser = require('jsonld-context-parser').ContextParser;
const ContextUtil = require('jsonld-context-parser').Util;
const myParser = new ContextParser();

function loadContextFromFile (fileName) {
  const context = fs.readFileSync(fileName, 'utf8');
  const contextParsed = JSON.parse(context);
  return contextParsed;
}

/**
 * Merge local context from jsonld and external given context
 * into a joint array
 * @param {object} jsonArr
 * @param {array or string} context
 * @returns mergedContext
 */
function mergeContexts (jsonArr, context) {
  function mergeContext (localContext, context) {
    let mergedContext = [];
    if (!Array.isArray(localContext) && localContext !== undefined) {
      mergedContext = [localContext];
    }
    if (context === undefined) {
      if (mergedContext.length === 0) {
        return null;
      }
      return mergedContext;
    } else if (!Array.isArray(context)) {
      context = [context];
    }
    context.forEach(c => {
      if (typeof (c) !== 'string' || mergedContext.find(x => c === x) === undefined) {
        mergedContext.push(c);
      }
    });
    return mergedContext;
  }
  if (context !== undefined) {
    const parseContextUrl = new url.URL(context);
    if (parseContextUrl.protocol === 'file:') {
      context = loadContextFromFile(parseContextUrl.pathname);
    }
  }
  if (jsonArr === undefined) {
    return mergeContext(undefined, context);
  }
  return jsonArr.map(jsonObj => {
    const localContext = jsonObj['@context'];
    return mergeContext(localContext, context);
  });
}

/**
 * Expects NGSI-LD object in expanded form and transforms to NGSI-LD concise form
 * @param {object} expanded
 * @returns concise and expanded form
 */
function conciseExpandedForm (expanded) {
  function filterAttribute (attr) {
    if (typeof (attr) === 'object') {
      if ('@type' in attr && (attr['@type'][0] === 'https://uri.etsi.org/ngsi-ld/Property' ||
                                    attr['@type'][0] === 'https://uri.etsi.org/ngsi-ld/Relationship')) {
        delete attr['@type'];
      }
      if ('https://uri.etsi.org/ngsi-ld/hasValue' in attr) {
        if (!(attr['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'])) {
          attr['@value'] = attr['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'];
          delete attr['https://uri.etsi.org/ngsi-ld/hasValue'];
        }
      }
    }
  }
  expanded.forEach(c => {
    Object.keys(c).forEach(key => {
      if (Array.isArray(c[key])) {
        c[key].forEach(a => filterAttribute(a));
      } else {
        filterAttribute(c[key]);
      }
    });
  });
  return expanded;
}

/**
 * Expects NGSI-LD object in expanded form and transforms to NGSI-LD normalized
 * @param {object} expanded
 * @returns normalized NGSI-LD and expanded form
 */
function normalizeExpandedForm (expanded) {
  function extendAttribute (attr) {
    if (typeof (attr) === 'object') {
      if (!('@type' in attr)) {
        if ('https://uri.etsi.org/ngsi-ld/hasValue' in attr || '@value' in attr || '@id' in attr) {
          attr['@type'] = ['https://uri.etsi.org/ngsi-ld/Property'];
        } else if ('https://uri.etsi.org/ngsi-ld/hasObject' in attr) {
          attr['@type'] = ['https://uri.etsi.org/ngsi-ld/Relationship'];
        }
        if ('@value' in attr) {
          attr['https://uri.etsi.org/ngsi-ld/hasValue'] = attr['@value'];
          delete attr['@value'];
        } else if ('@id' in attr) {
          attr['https://uri.etsi.org/ngsi-ld/hasValue'] = { '@id': attr['@id'] };
          delete attr['@id'];
        }
      }
    }
  }
  expanded.forEach(c => {
    Object.keys(c).forEach(key => {
      if (Array.isArray(c[key])) {
        c[key].forEach(a => extendAttribute(a));
      } else {
        extendAttribute(c[key]);
      }
    });
  });
  return expanded;
}

class ContextManager {
  constructor (context) {
    this._context = context;
  }

  async init () {
    const parseUrl = new url.URL(this._context);
    if (parseUrl.protocol === 'file:') {
      this._context = JSON.parse(fs.readFileSync(parseUrl.pathname, 'utf-8'));
    }
    this._mycontext = await myParser.parse(this._context);
    const prefixHash = {};
    Object.keys(this._mycontext.getContextRaw()).filter((key) => key !== '@vocab').forEach((key) => {
      const value = this._mycontext.getContextRaw()[key];
      if (typeof value === 'string') {
        if (ContextUtil.isPrefixIriEndingWithGenDelim(value)) {
          prefixHash[key] = value;
        }
      } else if (typeof value === 'object') {
        if (ContextUtil.isPrefixIriEndingWithGenDelim(value['@id'])) {
          prefixHash[key] = value['@id'];
        }
      }
    });
    this._prefixHash = prefixHash;
    // test expansion to check default context
    if (this._mycontext.expandTerm('test', true) === 'test') {
      console.log('Cannot derive default namespace. Neither derived by context nor explict given.');
      process.exit(1);
    }
  }

  /**
   * Function to extract namespace prefixes from a JSON-LD context
   * @param {parsed JSON structure} context
   */
  getNamespacePrefixes () {
    return this._prefixHash;
  }

  expandTerm (term) {
    return this._mycontext.expandTerm(term, true);
  }

  isValidIri (iri) {
    return ContextUtil.isValidIri(iri);
  }
}
module.exports = {
  mergeContexts,
  conciseExpandedForm,
  normalizeExpandedForm,
  ContextManager
};
