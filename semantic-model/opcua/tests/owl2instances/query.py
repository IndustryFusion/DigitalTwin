import rdflib
import argparse

def load_ttl_and_query(input_file, input_format, sparql_query_file):
    # Initialize an RDF graph
    graph = rdflib.Graph()
    contextgraph = rdflib.Graph()

    # Load the Turtle file into the graph
    graph.parse(input_file, format=input_format)
    contextgraph.parse("context.jsonld", format="json-ld")
    # Extract namespaces from the graph
    init_ns = {prefix: rdflib.Namespace(ns) for prefix, ns in contextgraph.namespaces()}

    # Load the SPARQL query from the file
    with open(sparql_query_file, "r") as f:
        sparql_query = f.read()

    # Execute the SPARQL query against the graph with initial namespaces
    results = graph.query(sparql_query, initNs=init_ns)

    # Write the results to stdout
    for row in results:
        print(row)

    if not results:
        print("No results found.")

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Apply a SPARQL query to a Turtle file and output the results.")
    parser.add_argument("input_file", help="The path to the input file")
    parser.add_argument("-f", "--input_format", help="Format of input file, e.g. ttl or json-ld", default="ttl")
    parser.add_argument("sparql_query_file", help="The path to the SPARQL query file")

    # Parse the arguments
    args = parser.parse_args()

    # Load the TTL and SPARQL query, and execute
    load_ttl_and_query(args.input_file, args.input_format, args.sparql_query_file)

if __name__ == "__main__":
    main()
