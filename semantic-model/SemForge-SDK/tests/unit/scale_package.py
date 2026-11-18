#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""A large package of the shape the OPC UA packages have (issue #991).

The kms corpus without its examples, grown by `types` entity types under
Machine -- each with an attribute of its own and a node shape that constrains
it -- and `entities` entities, every one of them carrying the same @context as
NGSI-LD writes it. The OPC UA demo package that showed the problem has 457
types, 86 node shapes and 311 entities; the editor must stay usable at
thousands.
"""

import json
import os
import shutil

ENTITIES = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
CORPUS = os.path.join(os.path.dirname(__file__), '..', 'corpus', 'kms')


def make(target, types=300, entities=3000):
    """Write the package into `target` (a directory that does not exist yet)."""
    os.makedirs(target)
    for name in ('knowledge.ttl', 'shacl.ttl', 'model-instance.jsonld',
                 'context.jsonld', 'kms.yaml'):
        shutil.copyfile(os.path.join(CORPUS, name), os.path.join(target, name))
    shutil.copytree(os.path.join(CORPUS, 'vocabulary'), os.path.join(target, 'vocabulary'))

    with open(os.path.join(target, 'knowledge.ttl'), 'a', encoding='utf-8') as out:
        out.write('\n# --- generated (tests/unit/scale_package.py) ---\n')
        for i in range(types):
            out.write(f'iffBaseEntities:GenType{i} a owl:Class ;\n'
                      f'    rdfs:subClassOf iffBaseEntities:Machine .\n'
                      f'iffBaseEntities:hasGen{i} a owl:ObjectProperty ;\n'
                      f'    rdfs:domain iffBaseEntities:GenType{i} ;\n'
                      f'    rdfs:range <https://uri.etsi.org/ngsi-ld/Property> .\n')

    with open(os.path.join(target, 'shacl.ttl'), 'a', encoding='utf-8') as out:
        out.write('\n# --- generated (tests/unit/scale_package.py) ---\n')
        for i in range(types):
            out.write(f'iffBaseShacl:GenType{i}Shape a sh:NodeShape ;\n'
                      f'    sh:property [ sh:maxCount 1 ;\n'
                      f'            sh:minCount 0 ;\n'
                      f'            sh:nodeKind sh:BlankNode ;\n'
                      f'            sh:path iffBaseEntities:hasGen{i} ;\n'
                      f'            sh:property [ sh:maxCount 1 ;\n'
                      f'                    sh:minCount 1 ;\n'
                      f'                    sh:nodeKind sh:Literal ;\n'
                      f'                    sh:path ngsild:hasValue ] ] ;\n'
                      f'    sh:targetClass iffBaseEntities:GenType{i} .\n')

    path = os.path.join(target, 'model-instance.jsonld')
    with open(path, encoding='utf-8') as handle:
        model = json.load(handle)
    context = model[0]['@context']
    for n in range(entities):
        i = n % types
        model.append({
            '@context': context,
            'id': f'urn:gen:{n}',
            'type': f'iffBaseEntities:GenType{i}',
            # As the corpus writes a valid Machine state: the model is clean,
            # as a shipped one is, so the verdicts are not a report of errors.
            'iffBaseEntities:hasState': [{
                'type': 'Property', 'value': {'@id': 'base:state_ON'},
                'iffBaseEntities:hasXXXWorkpiece': {'type': 'Relationship',
                                                    'object': 'urn:workpiece:1'}}],
            f'iffBaseEntities:hasGen{i}': [{'type': 'Property', 'value': n}],
        })
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(model, handle, indent=1)
    return target
