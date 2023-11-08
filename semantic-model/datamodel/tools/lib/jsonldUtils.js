
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
'use strict'
const url = require('url')
const fs = require('fs')

function loadContextFromFile (fileName) {
  const context = fs.readFileSync(fileName, 'utf8')
  const contextParsed = JSON.parse(context)
  return contextParsed
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
    let mergedContext = []
    if (!Array.isArray(localContext) && localContext !== undefined) {
      mergedContext = [localContext]
    }
    if (context === undefined) {
      if (mergedContext.length === 0) {
        return null
      }
      return mergedContext
    } else if (!Array.isArray(context)) {
      context = [context]
    }
    context.forEach(c => {
      if (typeof (c) !== 'string' || mergedContext.find(x => c === x) === undefined) {
        mergedContext.push(c)
      }
    })
    return mergedContext
  }
  if (context !== undefined) {
    const parseContextUrl = new url.URL(context)
    if (parseContextUrl.protocol === 'file:') {
      context = loadContextFromFile(parseContextUrl.pathname)
    }
  }
  return jsonArr.map(jsonObj => {
    const localContext = jsonObj['@context']
    return mergeContext(localContext, context)
  })
}

module.exports = {
  mergeContexts
}
