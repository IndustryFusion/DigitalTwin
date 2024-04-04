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

const { assert } = require('chai');
const chai = require('chai');
global.should = chai.should();

const rewire = require('rewire');
const ToTest = rewire('../lib/jsonldUtils.js');
const resolve = require('path').resolve;

describe('Test loadContextFromFile', function () {
  it('Should load context from filename', function () {
    const fs = {
      readFileSync: (filename, coding) => {
        filename.should.equal('filename');
        return '["context"]';
      }
    };
    const revert = ToTest.__set__('fs', fs);
    // ToTest.__set__('process', process)
    const loadContextFromFile = ToTest.__get__('loadContextFromFile');
    const result = loadContextFromFile('filename');
    result.should.deep.equal(['context']);
    revert();
  });
});

describe('Test mergeContexts', function () {
  it('should return null with undefined contexts', function () {
    const result = ToTest.mergeContexts(undefined, undefined);
    assert(result === null);
  });
  it('should return only the global context', function () {
    const context = 'http://context';
    const result = ToTest.mergeContexts(undefined, context);
    result.should.deep.equal([context]);
  });
  it('should return only the local context', function () {
    const context = [{ '@context': 'http://context' }];
    const result = ToTest.mergeContexts(context, undefined);
    result.should.deep.equal([['http://context']]);
  });
  it('should merge both contexts', function () {
    const globalcontext = 'http://context2';
    const context = [{ '@context': 'http://context' }];
    const result = ToTest.mergeContexts(context, globalcontext);
    result.should.deep.equal([['http://context', 'http://context2']]);
  });
  it('should merge object with string contexts', function () {
    const globalcontext = 'http://context2';
    const context = [{ '@context': { ns: 'http://context' } }];
    const result = ToTest.mergeContexts(context, globalcontext);
    result.should.deep.equal([[{ ns: 'http://context' }, 'http://context2']]);
  });
  it('should remove double context', function () {
    const globalcontext = 'http://context2';
    const context = [{ '@context': { ns: 'http://context' } }, { '@context': 'http://context2' }];
    const result = ToTest.mergeContexts(context, globalcontext);
    result.should.deep.equal([[{ ns: 'http://context' }, 'http://context2'], ['http://context2']]);
  });
});
describe('Test conciseExpandedForm', function () {
  it('should concise a property', function () {
    const expandedForm = [{
      '@id': 'id',
      '@type': 'type',
      property: [{
        '@type': ['https://uri.etsi.org/ngsi-ld/Property'],
        'https://uri.etsi.org/ngsi-ld/hasValue': [{ '@value': 'value' }]
      }]
    }];
    const expectedConciseForm = [{
      '@id': 'id',
      '@type': 'type',
      property: [{ '@value': 'value' }]
    }];
    const result = ToTest.conciseExpandedForm(expandedForm);
    expectedConciseForm.should.deep.equal(result);
  });
  it('should concise a relationship', function () {
    const expandedForm = [{
      '@id': 'id',
      '@type': 'type',
      hasRelationship: [{
        '@type': ['https://uri.etsi.org/ngsi-ld/Relationship'],
        'https://uri.etsi.org/ngsi-ld/hasObject': [{ '@id': 'iri' }]
      }]
    }];
    const expectedConciseForm = [{
      '@id': 'id',
      '@type': 'type',
      hasRelationship: [{ 'https://uri.etsi.org/ngsi-ld/hasObject': [{ '@id': 'iri' }] }]
    }];
    const result = ToTest.conciseExpandedForm(expandedForm);
    expectedConciseForm.should.deep.equal(result);
  });
});
describe('Test normalizeExpandedForm', function () {
  it('should normalize a property', function () {
    const expandedForm = [{
      '@id': 'id',
      '@type': 'type',
      property: [{
        'https://uri.etsi.org/ngsi-ld/hasValue': [{ '@value': 'value' }]
      }]
    }];
    const expectedNormalizedForm = [{
      '@id': 'id',
      '@type': 'type',
      property: [{
        '@type': ['https://uri.etsi.org/ngsi-ld/Property'],
        'https://uri.etsi.org/ngsi-ld/hasValue': [{ '@value': 'value' }]
      }]
    }];
    const result = ToTest.normalizeExpandedForm(expandedForm);
    expectedNormalizedForm.should.deep.equal(result);
  });
  it('should normalize a property', function () {
    const expandedForm = [{
      '@id': 'id',
      '@type': 'type',
      hasRelationship: [{
        'https://uri.etsi.org/ngsi-ld/hasObject': [{ '@id': 'iri' }]
      }]
    }];
    const expectedNormalizedForm = [{
      '@id': 'id',
      '@type': 'type',
      hasRelationship: [{
        '@type': ['https://uri.etsi.org/ngsi-ld/Relationship'],
        'https://uri.etsi.org/ngsi-ld/hasObject': [{ '@id': 'iri' }]
      }]
    }];
    const result = ToTest.normalizeExpandedForm(expandedForm);
    expectedNormalizedForm.should.deep.equal(result);
  });
});
describe('Test Context Manager', function () {
  it('should create a context manager', function () {
    const contextmanager = new ToTest.ContextManager('context');
    contextmanager._context.should.equal('context');
  });
  it('should expand a term', async function () {
    const absolutecontextpath = resolve('./tests/context.jsonld');
    const contextmanager = new ToTest.ContextManager('file://' + absolutecontextpath);
    await contextmanager.init();
    const expandedTerm = contextmanager.expandTerm('rdf:term');
    expandedTerm.should.equal('http://www.w3.org/1999/02/22-rdf-syntax-ns#term');
  });
  it('should check isValidIri', function () {
    const contextmanager = new ToTest.ContextManager('context');
    contextmanager.isValidIri('iri').should.equal(false);
    contextmanager.isValidIri('http://example.com/test').should.equal(true);
  });
  it('should create hash prefix', async function () {
    const absolutecontextpath = resolve('./tests/context.jsonld');
    const contextmanager = new ToTest.ContextManager('file://' + absolutecontextpath);
    await contextmanager.init();
    const namespaceHash = contextmanager.getNamespacePrefixes();
    namespaceHash.should.deep.equal({ rdf: 'http://www.w3.org/1999/02/22-rdf-syntax-ns#' });
  });
});
