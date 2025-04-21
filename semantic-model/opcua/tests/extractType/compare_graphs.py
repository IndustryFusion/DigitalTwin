import argparse
from rdflib import Graph
from rdflib.compare import to_isomorphic, graph_diff

def load_graph(filename, format=None):
    """
    Load an RDF graph from a file.

    Parameters:
    - filename: The path to the file containing the RDF graph.
    - format: Optional format specifier for the RDF file (e.g., 'ttl', 'xml', 'n3').

    Returns:
    - An rdflib.Graph object loaded with the contents of the file.
    """
    g = Graph()
    g.parse(filename, format=format)
    return g

def graphs_are_isomorphic(graph1, graph2):
    """
    Check if two RDF graphs are isomorphic (contain the same triples).

    Parameters:
    - graph1: The first rdflib.Graph to compare.
    - graph2: The second rdflib.Graph to compare.

    Returns:
    - True if the graphs are isomorphic, False otherwise.
    """
    return to_isomorphic(graph1) == to_isomorphic(graph2)

def show_diff(graph1, graph2, filename):
    """
    Show the difference between two RDF graphs.

    Parameters:
    - graph1: The first rdflib.Graph to compare.
    - graph2: The second rdflib.Graph to compare.
    """
    iso1 = to_isomorphic(graph1)
    iso2 = to_isomorphic(graph2)

    in_both, in_graph1_not_graph2, in_graph2_not_graph1 = graph_diff(iso1, iso2)

    with open(filename, 'w') as f:
        print("\nTriples in graph1 but not in graph2:", file=f)
        for triple in in_graph1_not_graph2:
            print(triple, file=f)

        print("\nTriples in graph2 but not in graph1:", file=f)
        for triple in in_graph2_not_graph1:
            print(triple, file=f)

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Compare two RDF graphs for isomorphism.")
    parser.add_argument('graph1', help='Path to the first RDF graph file.')
    parser.add_argument('graph2', help='Path to the second RDF graph file.')
    parser.add_argument('--format', '-f', default=None, help='Format of the RDF files (e.g., ttl, xml, n3). If not provided, it will be guessed based on file extension.')
    parser.add_argument('--output', '-o', default='graph-diff.ttl', help='Name of output file showing the diff.')
    args = parser.parse_args()

    outfile = args.output
    # Load the graphs
    graph1 = load_graph(args.graph1, format=args.format)
    graph2 = load_graph(args.graph2, format=args.format)

    # Compare the graphs
    if graphs_are_isomorphic(graph1, graph2):
        print("Graphs are isomorphic (identical).")
        exit(0)
    else:
        print(f"Graphs are not isomorphic (different). Output dumped to {outfile}.")
        show_diff(graph1, graph2, outfile)
        exit(1)

if __name__ == "__main__":
    main()
