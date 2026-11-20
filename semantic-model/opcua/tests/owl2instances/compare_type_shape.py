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
"""Compare the node shapes targeting one type in two SHACL files.

Exits 0 if both files contain node shapes for the type and the shapes, with everything reachable from them through
blank nodes, are isomorphic. Used to check that the shape of a type does not depend on the path to the type.
"""
import argparse
import sys
from rdflib import Graph, URIRef, BNode
from rdflib.compare import isomorphic
from rdflib.namespace import SH


def shape_of(filename, targetclass):
    g = Graph()
    g.parse(filename)
    result = Graph()
    todo = list(g.subjects(SH.targetClass, URIRef(targetclass)))
    seen = set()
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for p, o in g.predicate_objects(node):
            result.add((node, p, o))
            if isinstance(o, BNode):
                todo.append(o)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shacl1')
    parser.add_argument('shacl2')
    parser.add_argument('targetclass')
    args = parser.parse_args()
    shape1 = shape_of(args.shacl1, args.targetclass)
    shape2 = shape_of(args.shacl2, args.targetclass)
    if len(shape1) == 0 or len(shape2) == 0:
        print(f"No node shape for {args.targetclass} in {args.shacl1 if len(shape1) == 0 else args.shacl2}")
        sys.exit(1)
    if not isomorphic(shape1, shape2):
        print(f"The node shapes for {args.targetclass} differ")
        sys.exit(1)
    print(f"The node shapes for {args.targetclass} are the same")


if __name__ == '__main__':
    main()
