/**
* Copyright (c) 2024 Intel Corporation
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

const $rdf = require('rdflib');

const RDF = $rdf.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#');
const RDFS = $rdf.Namespace('http://www.w3.org/2000/01/rdf-schema#');
const OWL = $rdf.Namespace('http://www.w3.org/2002/07/owl#');
const NGSILD = $rdf.Namespace('https://uri.etsi.org/ngsi-ld/');

const globalAttributes = [];
const globalEntities = [];

class Entity {
  constructor (iri) {
    this._iri = iri;
  }

  get iri () {
    return this._iri;
  }
}

class Attribute {
  constructor (attributeName) {
    this._entities = [];
    this._attributeName = attributeName;
    this._isProperty = true;
  }

  addEntity (entity) {
    this._entities.push(entity);
  }

  set isProperty (isProp) {
    this._isProperty = isProp;
  }

  get isProperty () {
    return this._isProperty;
  }

  get attributeName () {
    return this._attributeName;
  }

  get entities () {
    return this._entities;
  }
}

function dumpAttribute (attribute, entity, store) {
  if (attribute.entities.filter(attrent => attrent.iri === entity.iri)) {
    store.add($rdf.sym(attribute.attributeName), RDF('type'), OWL('Property'));
    store.add($rdf.sym(attribute.attributeName), RDFS('domain'), $rdf.sym(entity.iri));
    if (attribute.isProperty) {
      store.add($rdf.sym(attribute.attributeName), RDFS('range'), NGSILD('Property'));
    } else {
      store.add($rdf.sym(attribute.attributeName), RDFS('range'), NGSILD('Relationship'));
    }
  }
}

function dumpEntity (entity, contextManager, store) {
  const nodeName = decodeURIComponent(contextManager.expandTerm(entity.iri));
  store.add($rdf.sym(nodeName), RDF('type'), OWL('Class'));
  globalAttributes.forEach((attribute) => {
    dumpAttribute(attribute, entity, store);
  });
}

function scanEntity (typeschema, contextManager) {
  const id = typeschema.$id;

  const entity = new Entity(id);
  globalEntities.push(entity);
  scanProperties(entity, typeschema, contextManager);
  return entity;
}

function scanProperties (entity, typeschema, contextManager) {
  if ('properties' in typeschema) {
    Object.keys(typeschema.properties).forEach(
      (property) => {
        if (property === 'type' || property === 'id') {
          return;
        }
        let isProperty = true;
        if ('relationship' in typeschema.properties[property]) {
          isProperty = false;
        }
        let path = property;
        if (!contextManager.isValidIri(path)) {
          path = contextManager.expandTerm(path);
        }

        const attribute = new Attribute(path);
        attribute.addEntity(entity);
        attribute.isProperty = isProperty;
        globalAttributes.push(attribute);
      });
  }
  if ('allOf' in typeschema) {
    typeschema.allOf.forEach((elem) => {
      scanProperties(entity, elem, contextManager);
    });
  }
}

/* istanbul ignore next */
function owlize (schemas, id, contextManager) {
  id = encodeHash(id);
  const store = new $rdf.IndexedFormula();
  const typeschema = schemas.find((schema) => schema.$id === id);
  const entity = scanEntity(typeschema, contextManager);
  dumpEntity(entity, contextManager, store);
  const serializer = new $rdf.Serializer(store);
  serializer.setFlags('u');
  serializer.setNamespaces(contextManager.getNamespacePrefixes());
  const turtle = serializer.statementsToN3(store.statementsMatching(undefined, undefined, undefined, undefined));
  console.log(turtle);
}

function encodeHash (id) {
  const url = new URL(id);
  const hash = encodeURIComponent(url.hash);
  return `${url.protocol}//${url.hostname}${url.pathname}${hash}`;
}

module.exports = {
  Entity,
  Attribute,
  owlize
};
