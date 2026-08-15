#
# Copyright (c) 2026 Intel Corporation
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

"""
Derive the knowledge file a set of shapes needs to compile.

The OPC UA generator emits shapes but no ontology, and shacl2flink needs every
targeted class declared before it will extract anything. Deriving the
declarations from the shapes themselves keeps this check tracking whatever the
generator emits, instead of a hand-written list that goes stale the first time
a new type appears.
"""

import sys

import rdflib
from rdflib.namespace import SH


def main(shapefile):
    graph = rdflib.Graph()
    graph.parse(shapefile, format='turtle')
    print('@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .')
    print('@prefix iff: <https://industry-fusion.com/types/v0.9/> .')
    for target in sorted({str(o) for o in graph.objects(None, SH.targetClass)}):
        print(f'<{target}> a rdfs:Class ; a iff:class .')


if __name__ == '__main__':
    main(sys.argv[1])
