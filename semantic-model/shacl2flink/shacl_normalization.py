#!/usr/bin/env python3
"""
shacl_wrap_or.py

For each sh:property shape in a SHACL shapes file (top-level or nested):
- If it already has only sh:path and sh:or, leave it alone.
- If it has sh:or plus other predicates, propagate those predicates to each member of the OR list.
- Otherwise, wrap all other predicates in a one-element sh:or list.

Usage:
    python shacl_wrap_or.py INPUT.ttl OUTPUT.ttl
"""
import argparse
from rdflib import Graph, BNode
from rdflib.collection import Collection
from rdflib.namespace import SH


def wrap_property_or(g):
    # Collect all blank nodes appearing as objects of sh:property
    prop_nodes = set(g.objects(None, SH.property))
    for prop in prop_nodes:
        # Gather all predicate-object pairs on this prop node
        preds = list(g.predicate_objects(prop))
        # Identify predicates other than sh:path and sh:or
        extras = [(p, o) for p, o in preds if p not in (SH.path, SH['or'])]
        # Does this prop have an existing OR?
        or_lists = [o for _, _, o in g.triples((prop, SH['or'], None))]

        if or_lists:
            # Propagate extras into each OR branch
            for or_list in or_lists:
                members = list(Collection(g, or_list))
                for branch in members:
                    for p, o in extras:
                        # add extra predicate/object to each branch
                        g.add((branch, p, o))
            # remove extras from the prop node itself
            for p, o in extras:
                g.remove((prop, p, o))
        else:
            # No OR: wrap extras into a single-element OR
            inner = BNode()
            for p, o in extras:
                g.add((inner, p, o))
                g.remove((prop, p, o))
            or_list = BNode()
            Collection(g, or_list, [inner])
            g.add((prop, SH['or'], or_list))


def main():
    parser = argparse.ArgumentParser(
        description="Wrap and propagate sh:property extras into sh:or branches."
    )
    parser.add_argument("input", help="Input SHACL Turtle file")
    parser.add_argument("output", help="Output simplified SHACL Turtle file")
    args = parser.parse_args()

    g = Graph().parse(args.input, format="turtle")
    wrap_property_or(g)
    g.serialize(destination=args.output, format="turtle")
    print(f"Written adjusted-OR propagation form to {args.output}")


if __name__ == "__main__":
    main()
