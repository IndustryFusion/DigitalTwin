#
# Copyright (c) 2024 Intel Corporation
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

import argparse
from rdflib import Graph, Namespace
from rdflib.namespace import OWL

def main(input_file, output_file):
    # Define the base namespace
    BASE = Namespace("https://industryfusion.github.io/contexts/ontology/v0/base/")

    # Create an RDF graph
    g = Graph()

    # Parse the input file
    g.parse(input_file, format="turtle")

    # Filter out all triples with predicates related to BASE and OWL
    triples_to_remove = [(s, p, o) for s, p, o in g if 
                         p == BASE.hasValueNode or 
                         o == BASE.ValueNode or 
                         p == BASE.hasEnumValue or
                         p == BASE.hasValueClass or
                         p == OWL.imports]
    
    # Remove the identified triples from the graph
    for triple in triples_to_remove:
        g.remove(triple)

    # Serialize the modified graph to a new Turtle file
    g.serialize(destination=output_file, format="turtle")

    print(f"Filtered graph saved to {output_file}")

if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Filter and remove specific triples from a Turtle file.")
    parser.add_argument("input_file", type=str, help="Path to the input Turtle file")
    parser.add_argument("output_file", type=str, help="Path to the output Turtle file")

    args = parser.parse_args()
    
    main(args.input_file, args.output_file)
