#!/usr/bin/env python3
import sys
import os
import rdflib
import shutil
import argparse
import subprocess


def is_remote(uri):
    return uri.startswith("http://") or uri.startswith("https://")


def collect_dependencies(source, visited):
    """
    Recursively parse the ontology at 'source' and return two sets:
    - local_files: absolute paths to ontologies available locally.
    - remote_uris: IRIs that are remote (http/https).
    The 'visited' set is used to avoid reprocessing the same ontology.
    """
    local_files = set()
    remote_uris = set()
    if source in visited:
        return local_files, remote_uris
    visited.add(source)
    try:
        g = rdflib.Graph()
        g.parse(source)
    except Exception as e:
        print(f"Error parsing {source}: {e}")
        return local_files, remote_uris

    owl_import = rdflib.URIRef("http://www.w3.org/2002/07/owl#imports")
    for _, _, o in g.triples((None, owl_import, None)):
        imp = str(o)
        if imp in visited:
            continue
        # Process remote imports
        if is_remote(imp):
            remote_uris.add(imp)
            # Recursively collect dependencies from the remote ontology
            l, r = collect_dependencies(imp, visited)
            local_files.update(l)
            remote_uris.update(r)
        else:
            # For non-remote IRIs, try to resolve as a local file.
            local_path = imp
            if local_path.startswith("file://"):
                local_path = local_path[7:]
            if os.path.exists(local_path):
                abs_local = os.path.abspath(local_path)
                local_files.add(abs_local)
                l, r = collect_dependencies(abs_local, visited)
                local_files.update(l)
                remote_uris.update(r)
            else:
                print(f"Warning: Local file for import '{imp}' not found. Treating as remote if possible.")
                remote_uris.add(imp)
                l, r = collect_dependencies(imp, visited)
                local_files.update(l)
                remote_uris.update(r)
    return local_files, remote_uris


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Fuseki configuration file from an ontology and its dependencies, \
and optionally start Fuseki."
    )
    parser.add_argument("ontology_file", help="Path to the main ontology file.")
    parser.add_argument("--prefixes-file",
                        help="Path to a file with SPARQL PREFIX declarations.",
                        default=None)
    parser.add_argument("--fuseki-exec",
                        help="Path to the fuseki-server executable. If provided, the server will be started.",
                        default=None)
    args = parser.parse_args()

    ontology_path = args.ontology_file
    prefixes_file = args.prefixes_file
    fuseki_exec = args.fuseki_exec

    if not os.path.exists(ontology_path):
        print(f"Ontology file '{ontology_path}' not found.")
        sys.exit(1)

    # Create a directory to store ontology files.
    ontology_dir = "ontology_files"
    os.makedirs(ontology_dir, exist_ok=True)

    # Copy the main ontology file.
    main_filename = os.path.basename(ontology_path)
    main_dest = os.path.join(ontology_dir, main_filename)
    shutil.copy(ontology_path, main_dest)
    print("Main ontology:", ontology_path)

    # Recursively collect dependencies from the main ontology.
    visited = set()
    local_deps, remote_deps = collect_dependencies(ontology_path, visited)
    # Remove the main ontology if it was included in the recursive results.
    main_abs = os.path.abspath(ontology_path)
    if main_abs in local_deps:
        local_deps.remove(main_abs)

    print("Recursively found dependencies:")
    print(" Local files:")
    for dep in local_deps:
        print("   ", dep)
    print(" Remote URIs:")
    for uri in remote_deps:
        print("   ", uri)

    # Copy local dependency files into the ontology directory.
    ontology_files = [main_filename]
    for dep in local_deps:
        dep_filename = os.path.basename(dep)
        dest_path = os.path.join(ontology_dir, dep_filename)
        try:
            shutil.copy(dep, dest_path)
            ontology_files.append(dep_filename)
            print(f"Copied local dependency: {dep_filename}")
        except Exception as e:
            print(f"Error copying '{dep}': {e}")

    # Default prefix declarations if no prefixes file is provided.
    default_prefixes = """\
PREFIX base: <https://industryfusion.github.io/contexts/ontology/v0/base/>
PREFIX opcua: <http://opcfoundation.org/UA/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>"""

    if prefixes_file and os.path.exists(prefixes_file):
        with open(prefixes_file, 'r') as pf:
            prefix_declarations = pf.read().strip()
    else:
        prefix_declarations = default_prefixes

    # Define a default query.
    default_query_body = 'SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10'
    default_query_full = f"{prefix_declarations}\n\n{default_query_body}"

    # Generate the Fuseki assembler configuration file.
    config_content = ""
    config_content += f"# Default prefixes:\n{prefix_declarations}\n\n"
    config_content += """@prefix ja:     <http://jena.hpl.hp.com/2005/11/Assembler#> .
@prefix fuseki: <http://jena.apache.org/fuseki#> .

"""
    # Build the list of ontology URIs.
    local_uris = [f'"file://{os.path.abspath(os.path.join(ontology_dir, f))}"' for f in ontology_files]
    remote_uris = [f'"{uri}"' for uri in remote_deps]
    all_uris = local_uris + remote_uris
    file_uris = ", ".join(all_uris)

    config_content += "<#dataset> a ja:MemoryDataset ;\n"
    config_content += f"    ja:data {file_uris} .\n\n"
    config_content += f'''<#service> a fuseki:Service ;
    fuseki:name "ds" ;
    fuseki:dataset <#dataset> ;
    fuseki:serviceQuery "sparql" ;
    fuseki:serviceUpdate "update" ;
    fuseki:queryDefault """{default_query_full}""" .
'''

    config_filename = "fuseki_config.ttl"
    with open(config_filename, "w") as cf:
        cf.write(config_content)

    print("\nGenerated Fuseki configuration file:", config_filename)
    print("To start Fuseki, run:")
    print(f"fuseki-server --config={config_filename}")

    print("\nCopy and paste the following default query into the Fuseki query editor if needed:")
    print("--------------------------------------------------------")
    print(default_query_full)
    print("--------------------------------------------------------")

    if fuseki_exec:
        if not os.path.exists(fuseki_exec):
            print(f"Fuseki executable '{fuseki_exec}' not found.")
        else:
            print("\nStarting fuseki-server...")
            try:
                subprocess.run([fuseki_exec, f"--config={config_filename}"])
            except Exception as e:
                print("Error starting fuseki-server:", e)


if __name__ == "__main__":
    main()
