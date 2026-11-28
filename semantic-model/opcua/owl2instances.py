#!/usr/bin/env python3
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
import sys
import os
import urllib
import lib.jsonld as libjsonld
from lib.utils import warnings, print_warning
from collections import defaultdict
from rdflib import Graph, Namespace, URIRef, BNode
from rdflib.namespace import OWL, RDF, SH
import argparse
import lib.utils as utils
from lib.utils import RdfUtils, OntologyLoader, UARDF
from lib.bindings import Bindings
from lib.jsonld import JsonLd
from lib.entity import Entity
from lib.shacl import Shacl
import logging

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper())
logger = logging.getLogger(__name__)


warnings.filterwarnings("ignore", message=".*anyType is not defined in namespace XSD.*")
attribute_prefix = utils.ATTRIBUTE_PREFIX
default_context_url = "https://industryfusion.github.io/contexts/staging/opcua/v0.2/context.jsonld"

query_namespaces = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?uri ?prefix ?ns WHERE {
    ?ns rdf:type base:Namespace .
    ?ns base:hasUri ?uri .
    ?ns base:hasPrefix ?prefix .
}
"""

query_subclasses = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

CONSTRUCT {
  ?subclass rdfs:subClassOf ?superclass .
  ?subclass a owl:Class .
  ?superclass a owl:Class .
}
WHERE {
  ?subclass rdfs:subClassOf* <http://opcfoundation.org/UA/BaseObjectType> .
  ?subclass rdfs:subClassOf ?superclass .

  # Ensure both subclasses and superclasses are marked as owl:Class
  {
    ?subclass a owl:Class .
  } UNION {
    ?superclass a owl:Class .
  }
}
"""


randnamelength = 16
modelling_nodeid_optional = 80
modelling_nodeid_mandatory = 78
modelling_nodeid_optional_array = 11508
basic_types = [
    'String',
    'Boolean',
    'Byte',
    'SByte',
    'Int16',
    'UInt16',
    'Int32',
    'UInt32',
    'Uin64',
    'Int64',
    'Float',
    'DateTime',
    'Guid',
    'ByteString',
    'Double'
]
workaround_instances = [
    'http://opcfoundation.org/UA/DI/FunctionalGroupType',
    'http://opcfoundation.org/UA/FolderType'
]
datasetid_urn = 'urn:iff:datasetId'


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='\
parse nodeset instance and create ngsi-ld model')

    parser.add_argument('instance', help='Path to the instance nodeset2 file.')
    parser.add_argument('-t', '--type',
                        help='Type of root object to be extracted, e.g. http://opcfoundation.org/UA/Pumps/',
                        required=False)
    parser.add_argument('-so', '--shacl-only', help='Only create SHACL shapes without JSON-LD instances.',
                        required=False, action='store_true')
    parser.add_argument('-ta', '--type-all', help='Extract all ObjectTypes of the mainontologies namespace.'
                        ' In additiion, extract all well known instances (i.e. referenced by the "objects" folder)',
                        required=False, action='store_true')
    parser.add_argument('-eid', '--extract-instance-declarations', help='Extract all instance declarations'
                        ' in order to validate them. This option only works with -ta option enabled.',
                        required=False, action='store_true')
    parser.add_argument('-j', '--jsonld',
                        help='Filename of jsonld output file',
                        required=False,
                        default='instances.jsonld')
    parser.add_argument('-e', '--entities',
                        help='Filename of entities output file',
                        required=False,
                        default='entities.ttl')
    parser.add_argument('-s', '--shacl',
                        help='Filename of SHACL output file',
                        required=False,
                        default='shacl.ttl')
    parser.add_argument('-b', '--bindings',
                        help='Filename of bindings output file',
                        required=False,
                        default='bindings.ttl')
    parser.add_argument('-c', '--context',
                        help='Filename of JSONLD context output file',
                        required=False,
                        default='context.jsonld')
    parser.add_argument('-d', '--debug',
                        help='Add additional debug info to structure (e.g. for better SHACL debug)',
                        required=False,
                        action='store_true')
    parser.add_argument('-ma', '--maximalshacl',
                        help='Add all types from nodes in the namespace.',
                        required=False,
                        action='store_true')
    parser.add_argument('-n', '--namespace', help='Namespace prefix for entities, SHACL and JSON-LD', required=True)
    parser.add_argument('-i', '--id',
                        help='ID prefix of the entities. The ID of every entity is "<prefix><base64url encoded '
                        'canonical ExpandedNodeId of its node>", default prefix: urn:uaentity:',
                        required=False)
    parser.add_argument('-xe', '--entity-namespace',
                        help='Overwrite Namespace for entities (which is otherwise derived from <namespace>/entity)',
                        required=False)
    parser.add_argument('-xc', '--context-url', help=f'Context URL, default: {default_context_url}',
                        default=f"{default_context_url}",
                        required=False)
    parser.add_argument('-r', '--recursive-import',
                        help='Import dependencies of dependencies',
                        required=False,
                        default=False,
                        action='store_true')
    parser.add_argument('-sw', '--suppress-warnings', type=str, nargs='*',
                        help='List of Warnings which are to be suppressed.')
    parser.add_argument('--no-properties', dest='properties', help='Do not follow OPC UA Properties (HasProperty). '
                        'By default they are followed: they become attributes of the entities, or sub-attributes of '
                        'the variable they belong to, e.g. EngineeringUnits.',
                        required=False, default=True, action='store_false')
    parser.add_argument('-p', '--properties', dest='properties_compat',
                        help='No effect, kept for compatibility: OPC UA Properties are followed by default.',
                        required=False, default=False, action='store_true')
    parser.add_argument('-vrs', '--value-rank-subshapes', help='Add ValueRank subshapes (instead of nest '
                        'the whole expression).',
                        required=False, default=False,
                        action='store_true')
    parser.add_argument('-sb', '--semantic-bridge', help='Add Semantic Bridge in JSON-LD to allow convenient '
                        'mapping back to OWL (includes --node-references)',
                        required=False, default=False,
                        action='store_true')
    parser.add_argument('-nr', '--node-references', help='Add a reference (base:hasNodeRef) from every entity to '
                        'the OPC UA node it is created from',
                        required=False, default=False,
                        action='store_true')

    parsed_args = parser.parse_args(args)
    return parsed_args


def get_ignored_hierarchical_references(follow_properties, opcua_namespace):
    """The hierarchical references the scan does not follow: HasProperty unless OPC UA Properties are followed
       (the default; --no-properties turns it off)."""
    if follow_properties:
        return []
    return [opcua_namespace['HasProperty']]


basens = None  # Will be defined by the imported ontologies
opcuans = None  # dito
ngsildns = Namespace('https://uri.etsi.org/ngsi-ld/')
scanned_types = set()
scanned_entities = set()
# declaring type -> browse paths of declarations that add members more than one relationship deep
deep_additions = defaultdict(set)
# instance declaration node -> its declaration shape (one shape per declaration, also when several types
# refer to the same declaration node)
declaration_shapes = {}
empty_declarations = set()       # declarations whose additions give no rule


def check_object_consistency(shapenode, attribute_path, classtype, suppress_warnings=False, add_entity=True):
    """Check if attribute_path is already known.
       In this case, it is important to differentiate between FolderTypes and
       regular objects. For FolderType, we are relaxed, and search for common
       superclass to make sure objects stay compliant.
       If it is a regular object, then this means that the reference has already
       been found. What can happen is that there is a superclass with the same
       attribute_path but different classtype. This is only allowed when
       classtype of superclass is subclass of existing. Since the objecttypes are
       always scanned from special to general, it the superclass classtype must
       always fit.

    Args:
        shapenode (URIRef): SHACL shape node to compare with (node on which the constraints are defined)
        attribute_path (URIRef): property path which is questioned
        classtype (URIRef): sh:class of referenced object through property

    Returns:
        bool, URIRef: stop_scanning, common superclass if found
    """
    needed_superclass = None
    property = shaclg.get_property_from_shape(shapenode, attribute_path)
    instancetype = shaclg.get_targetclass(shapenode)
    if property is None:
        if add_entity and instancetype is not None:
            e.add_instancetype(instancetype, attribute_path)
            e.add_type(classtype)
        return False, None
    # Check if opcua:FolderType or its subclasses. This needs special treatment
    is_folder = utils.is_subclass(g, instancetype, opcuans['FolderType']) if instancetype is not None else False
    shclass = shaclg._get_shclass_from_property(property)
    if is_folder:
        if shclass != classtype:
            common_superclass = utils.get_common_supertype(g, shclass, classtype)
            shaclg.update_shclass_in_property(property, common_superclass)
            if not suppress_warnings:
                warnmsg = f"Class inconsistency found in (FolderType) \
    {instancetype}. The class {shclass} and {classtype} are defined for the same reference {attribute_path}."
            print_warning('folder_reference_inconsistency', warnmsg)
        return True, needed_superclass
    else:  # Normal Object
        # shclass must be subclass of classtype since we assume that classtype must come
        # from a superclass
        is_subclass = utils.is_subclass(g, shclass, classtype)
        if not is_subclass and not suppress_warnings:
            warnmsg = f"Class inconsistency found in shape {shapenode}. \
The class {shclass} must be subclass of {classtype} found in the hierarchy."
            print_warning('subclass_inconsistency', warnmsg)
        return True, None


def check_variable_consistency(shapenode, attribute_path, classtype):
    if shaclg.attribute_is_indomain(shapenode, attribute_path):
        return True
    instancetype = shaclg.get_targetclass(shapenode)
    if instancetype is not None:
        e.add_instancetype(instancetype, attribute_path)
    e.add_type(classtype)
    return False


def uardf_import(graph):
    """The document the ontologies import as uardf ontology, by default the local uardf.ttl (as nodeset2owl.py)."""
    for imported in sorted(set(graph.objects(None, OWL.imports))):
        if str(imported).endswith('/uardf.ttl'):
            return imported
    return URIRef(utils.file_path_to_uri(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uardf.ttl')))


def collect_deep_additions(declaration, declaring_type, path, depth=0):
    """Record the object declarations below `declaration` which add members beyond their type. They are
    more than one relationship away from the owning type, so their additions are not validated."""
    if depth > 20:
        return
    for reference, child in rdfutils.get_all_subreferences(g, declaration, opcuans['HasChild']):
        if reference in ignored_hierarchical_references:
            continue
        nodeclass, childtype = rdfutils.get_type(g, child)
        if not rdfutils.isObjectNodeClass(nodeclass) or childtype is None:
            continue
        if next(g.objects(child, opcuans['HasModellingRule']), None) is None:
            continue
        childpath = f"{path}/{next(g.objects(child, UARDF['name']), child)}"
        if rdfutils.get_added_children(g, child, childtype, ignored_hierarchical_references):
            deep_additions[declaring_type].add(childpath)
        collect_deep_additions(child, declaring_type, childpath, depth + 1)


def report_deep_additions():
    """Report, once per declaring type, the declarations whose additions are not validated."""
    for declaring_type in sorted(deep_additions):
        paths = sorted(deep_additions[declaring_type])
        print_warning('deep_declaration_additions',
                      f"{declaring_type}: {len(paths)} instance declaration(s) add members more than one "
                      f"relationship deep, which are not validated: {', '.join(paths)}")


def scan_type(node, instancetype, shape_node=None):
    logger.debug('Scanning type: %s with node %s', instancetype, node)
    # Loop through all supertypes
    supertypes = rdfutils.get_all_supertypes_and_interfaces(g, instancetype, node)
    # Loop through all components
    if shape_node is None:
        shapename = shaclg.create_shacl_type(instancetype)
    else:
        shapename = shape_node
    has_components = False
    for (curtype, curnode) in supertypes:
        children = rdfutils.get_all_subreferences(g, curnode, opcuans['HasChild'])
        for reference, target in children:
            if reference not in ignored_hierarchical_references:
                has_components = scan_type_recursive(target, curnode, instancetype, shapename,
                                                     reference) or has_components
        organizes = rdfutils.get_all_subreferences(g, curnode, opcuans['Organizes'])
        nonhierachical = rdfutils.get_all_subreferences(g, curnode, opcuans['NonHierarchicalReferences'])
        # Treat organizes like non-hierarchical references
        nonhierachical += organizes
        # Now group tuples after reference, i.e.
        # [(ref1, node1), (ref2, node2), (ref1, node2)] => [(ref1, [node1, node3]), (ref2, node2)]
        grouped = defaultdict(list)
        for key, value in nonhierachical:
            grouped[key].append(value)
        grouped_references = [(key, values) for key, values in grouped.items()]
        for generic_reference, target in grouped_references:
            if generic_reference not in ignored_references:
                has_components = scan_type_non_hierachical(target, curnode, instancetype, shapename,
                                                           generic_reference) or has_components
    return has_components


def is_unconstrained_value(shacl_rule):
    """Whether a variable's rule gives no value shape: any value rank, no data type and no array
    dimensions (the case Shacl.create_shacl_property writes without one)."""
    value_rank = shacl_rule.get('value_rank')
    if value_rank is None or int(value_rank) != -2:
        return False
    return shacl_rule.get('datatype') is None and shacl_rule.get('array_dimensions') is None


def scan_type_recursive(o, node, instancetype, shapename, reftype):
    logger.debug(f"Scanning type recursively: {instancetype} with node {node} and reference {reftype} and shape"
                 f"{shapename}")
    shacl_rule = {}
    browse_name = next(g.objects(o, UARDF['name']))
    nodeclass, classtype = rdfutils.get_type(g, o)
    if rdfutils.isMethodNodeClass(nodeclass):
        return False
    attributename = rdfutils.get_semantic_bridge(g, node, o)
    rdfutils.get_modelling_rule(g, o, shacl_rule, instancetype)
    placeholder_pattern = None
    decoded_attributename = urllib.parse.unquote(attributename)
    if utils.contains_both_angle_brackets(decoded_attributename):
        _, placeholder_pattern = utils.normalize_angle_bracket_name(browse_name)
    shacl_rule['path'] = attributename

    if rdfutils.isObjectNodeClass(nodeclass):
        stop_scan, _ = check_object_consistency(shapename, attributename, classtype)
        if stop_scan:
            return True
        # check for loop
        if (instancetype, node, o) in scanned_types:
            pnodeclass, _ = rdfutils.get_type(g, node)
            if rdfutils.isObjectTypeNodeClass(pnodeclass):
                return False
            print(f"Warning: Found already scanned node {node}=>{o} in hierarchical references. Could be potentially \
a loop.")
            return False
        else:
            scanned_types.add((instancetype, node, o))
        has_components = False
        shacl_rule['is_property'] = False
        _, is_placeholder_array = rdfutils.get_modelling_rule(g, o, None, instancetype)
        if is_placeholder_array:
            # This indicates a placeholder
            shacl_rule['array'] = True
        if not is_placeholder_array and placeholder_pattern is not None:
            logger.warning(f"Placeholder pattern with non matching modelling rule found for node {o}.")
        if is_placeholder_array and placeholder_pattern is None:
            logger.warning(f"Array modelling rule found for node {o} but no placeholder pattern in Browsename"
                           f"{attributename}.")
        # Members this declaration adds beyond its type are part of the declaring type's definition.
        # They are validated one relationship deep, through a declaration shape (see below); deeper
        # additions are only reported.
        declaration = o
        additions = []
        declaring_type = None
        parent_nodeclass, _ = rdfutils.get_type(g, node)
        if rdfutils.isObjectTypeNodeClass(parent_nodeclass):
            declaring_type = next(g.objects(node, UARDF['definesType']), None)
            additions = rdfutils.get_added_children(g, declaration, classtype, ignored_hierarchical_references)
            if declaring_type is not None:
                collect_deep_additions(declaration, declaring_type, str(browse_name))
        # Now, get the type node. Do not recurse on the instance declaration
        # instance declarations might contain references which are not normative
        # for the type node
        _, typeiri = rdfutils.get_type(g, o)
        try:
            typenode = next(g.subjects(UARDF['definesType'], typeiri))
            o = typenode
        except Exception:
            pass
        components_found = scan_type(o, classtype)
        # scan_type reports the content of a type only on its first visit. A member of a declaration shape
        # (a shape without target) gets its rule whenever its type has rules, however often it was visited.
        if not components_found and shaclg.get_targetclass(shapename) is None and shaclg.type_has_rules(classtype):
            components_found = True
        if maximal_shacl:
            components_found = True
        # A placeholder is normative even if its type defines no rules of its own:
        # without the property, the parent shape would not allow these children at all.
        if is_placeholder_array or additions:
            components_found = True
        if components_found:
            has_components = True
            # only if modelling rule is defined (otherwise we assume that this is just
            # an instance declaration which contains references which are not normative
            shacl_rule['contentclass'] = classtype
            property = shaclg.create_shacl_property(shapename,
                                                    shacl_rule['path'],
                                                    shacl_rule['optional'],
                                                    shacl_rule['array'],
                                                    False,
                                                    True,
                                                    shacl_rule['contentclass'],
                                                    None,
                                                    is_subcomponent=True,
                                                    placeholder_pattern=placeholder_pattern,
                                                    reftype=reftype)
            if additions and declaring_type is not None and property is not None:
                declaration_shape = declaration_shapes.get(declaration)
                if declaration_shape is None:
                    declaration_shape = shaclg.get_declaration_shape_name(declaring_type, browse_name)
                    declaration_shapes[declaration] = declaration_shape
                    if shaclg.create_declaration_shape(declaration_shape):
                        for added_reference, added_child in additions:
                            scan_type_recursive(added_child, declaration, classtype, declaration_shape,
                                                added_reference)
                        if shaclg.remove_empty_declaration_shape(declaration_shape):
                            # none of the additions gives a rule: nothing to apply
                            empty_declarations.add(declaration)
                if declaration not in empty_declarations:
                    shaclg.add_node_to_relationship(property, declaration_shape)
    elif rdfutils.isVariableNodeClass(nodeclass):
        stop_scan = check_variable_consistency(shapename, attributename, classtype)
        if stop_scan:
            return True
        has_components = True
        try:
            # IsAbstract is an attribute of the type node which defines the class
            typenode = next(g.subjects(UARDF['definesType'], classtype))
            isAbstract = utils.rdfStringToPythonBool(next(g.objects(typenode, UARDF['isAbstract'])))
        except Exception:
            isAbstract = False
        if isAbstract:
            return False
        shacl_rule['is_property'] = True
        shaclg.get_shacl_iri_and_contentclass(g, o, node, shacl_rule)
        if placeholder_pattern is not None and is_unconstrained_value(shacl_rule):
            # A placeholder variable (e.g. DI's <ParameterIdentifier>) of any value rank and data type gives
            # no value shape, and its instances are named freely, so its name cannot be checked either: the
            # member would require an attribute literally called has<...>. It gives no rule.
            logger.info(f"Placeholder variable {o} has no value constraint: no rule.")
            return False
        shacl_node = shaclg.create_shacl_property(shapename,
                                                  shacl_rule['path'],
                                                  shacl_rule['optional'],
                                                  shacl_rule['array'],
                                                  True, shacl_rule['is_iri'],
                                                  shacl_rule['contentclass'],
                                                  shacl_rule['datatype'],
                                                  pattern=shacl_rule['pattern'],
                                                  value_rank=shacl_rule.get('value_rank'),
                                                  array_dimensions=shacl_rule.get('array_dimensions'),
                                                  reftype=reftype)
        if shacl_node is not None:
            if shacl_rule['datatype'] != opcuans['NodeId']:
                e.add_enum_class(g, shacl_rule['contentclass'])
            components_found = scan_type(o, classtype, shacl_node)
    return has_components


def scan_type_non_hierachical(target, node, instancetype, shapename, reftype):
    """scan non-hierarchical relationship

    Args:
        target (URIRef): targetnode
        node (URIRef): node containing the reference
        instancetype (URIRef): type for which the shacl constraint is defined
        shapename (URIRef): Name of SHACL Shape
        is_nh_reference (Bool): True for NH-references.
        reftype (URIRef): Reference name

    Returns:
        bool: True if the shape holds a rule for this reference afterwards
    """
    logger.debug(f"Scanning non-hierarchical reference: {reftype} with target {target} in node {node} for type"
                 f"{instancetype} and shape {shapename}")
    shacl_rule = {}
    # check if at least one object nodeclass is found
    full_attribute_name = reftype
    for t in target:
        nodeclass, _ = rdfutils.get_type(g, t)
        if not rdfutils.isVariableNodeClass(nodeclass):
            break

    if rdfutils.isObjectNodeClass(nodeclass) or rdfutils.isObjectTypeNodeClass(nodeclass):
        property = shaclg.get_property_from_shape(shapename, full_attribute_name)
        is_indomain = property is not None
        shclass = shaclg._get_shclass_from_property(property)
        for t in target:
            t_nodeclass, t_classtype = rdfutils.get_type(g, t)
            if rdfutils.isVariableNodeClass(t_nodeclass):
                warnmsg = f"Warning: Variable node {t} is target of \
non-owning or non-hierarchical reference {reftype} This will be ignored."
                if type_all is False:
                    print_warning('ignored_variable_reference', warnmsg)
                continue
            if shclass is None:
                shclass = t_classtype
            else:
                shclass = utils.get_common_supertype(g, shclass, t_classtype)
            check_object_consistency(shapename, full_attribute_name, shclass, not is_indomain, add_entity=False)
        if is_indomain:
            shaclg.update_shclass_in_property(full_attribute_name, shclass)
            return True
        shacl_rule['path'] = full_attribute_name
        rdfutils.get_modelling_rule(g, t, shacl_rule, instancetype)
        e.add_instancetype(instancetype, full_attribute_name)
        e.add_type(shclass)
        maxcount = None

        shacl_rule['is_property'] = False
        shacl_rule['contentclass'] = shclass
        shaclg.create_shacl_property(shapename,
                                     shacl_rule['path'],
                                     True,
                                     False,
                                     False,
                                     True,
                                     shacl_rule['contentclass'],
                                     None,
                                     reftype=reftype,
                                     maxCount=maxcount)
        return True
    elif rdfutils.isVariableNodeClass(nodeclass) and type_all is False:
        warnmsg = f"Warning: Variable node {target} is target of \
non-owning or non-hierarchical reference {reftype} This will be ignored."
        print_warning('ignored_variable_reference', warnmsg)
    return False


def scan_entity(node, instancetype, id, optional=False, declaration_shape=None):
    logger.debug(f"Scanning entity: {node} for type {instancetype} with id {id}")
    node_id = rdfutils.generate_node_id(g, rootentity, node, id)
    # detect recursion
    if node_id in scanned_entities:
        return node_id

    instance = {}
    prefixed_type = utils.get_prefixed(context_graph, instancetype)
    instance['type'] = prefixed_type
    instance['id'] = node_id
    if node_references_enabled:
        noderef_key = utils.get_prefixed(context_graph, basens['hasNodeRef'])
        noderef_value = utils.get_prefixed(context_graph, node)
        instance[noderef_key] = jsonld.get_ngsild_vocab(noderef_value)
    instance['@context'] = [
        context_url
    ]
    followed_nodes.add(node)

    # Loop through all components
    has_components = False
    children = rdfutils.get_all_subreferences(g, node, opcuans['HasChild'])
    for reference, target in children:
        if reference not in ignored_hierarchical_references:
            has_components = scan_entity_recursive(node, id, instance, node_id, target, type=instancetype,
                                                   declaration_shape=declaration_shape) or has_components
    organizes = rdfutils.get_all_subreferences(g, node, opcuans['Organizes'])
    for organizes_reference, target in organizes:
        has_components = scan_entity_nonrecursive(node, id, instance, node_id, target,
                                                  organizes_reference) or has_components
    non_hierarchicals = rdfutils.get_all_subreferences(g, node, opcuans['NonHierarchicalReferences'])
    for generic_reference, target in non_hierarchicals:
        if generic_reference not in ignored_references:
            has_components = scan_entity_nonrecursive(node, id, instance, node_id, target,
                                                      generic_reference) or has_components
    if has_components or not optional or maximal_shacl:
        jsonld.add_instance(instance)
        scanned_entities.add(node_id)
        return node_id
    else:
        return None


def scan_entity_variable(node, instancetype, id, optional=False):
    logger.debug(f"Scanning variable entity: {node} for type {instancetype} with id {id}")
    node_id = rdfutils.generate_node_id(g, rootentity, node, id)
    # detect recursion
    if node_id in scanned_entities:
        return node_id

    attributes = {}
    # Loop through all components
    has_components = False
    children = rdfutils.get_all_subreferences(g, node, opcuans['HasComponent'])
    for reference, target in children:
        has_components = scan_entity_recursive(node, id, attributes, node_id, target) or has_components
    children = rdfutils.get_all_subreferences(g, node, opcuans['HasProperty'])
    for reference, target in children:
        if reference not in ignored_hierarchical_references:
            has_components = scan_entity_recursive(node,
                                                   id,
                                                   attributes,
                                                   node_id,
                                                   target,
                                                   is_property=True) or has_components
    non_hierarchicals = rdfutils.get_all_subreferences(g, node, opcuans['NonHierarchicalReferences'])
    for generic_reference, target in non_hierarchicals:
        if generic_reference not in ignored_references:
            has_components = scan_entity_nonrecursive(node, id, attributes, node_id, target,
                                                      generic_reference) or has_components
    return attributes


def scan_entity_recursive(node, id, instance, node_id, o, type=None, is_property=False, declaration_shape=None):
    """Scan the child `o` of `node`. `declaration_shape` constrains the members that the instance
    declaration of `node` adds beyond its type; they are looked up there when the type does not
    declare them."""
    logger.debug(f"Scanning entity recursively: {node} for type {type} with id {id}")
    has_components = False
    shacl_rule = {}
    browse_name = next(g.objects(o, UARDF['name']))
    nodeclass, classtype = rdfutils.get_type(g, o)
    attributename = rdfutils.get_semantic_bridge(g, node, o)

    original_attributename = None
    if type is not None:
        optional, array, path = shaclg.get_modelling_rule_and_path(browse_name, URIRef(type),
                                                                   classtype, attribute_prefix,
                                                                   bridge=attributename)
    else:
        optional, array, path = (None, None, None)
    if path is None and declaration_shape is not None and rdfutils.isObjectNodeClass(nodeclass):
        # An object member the declaration adds: found in the declaration shape by its semantic bridge (a fixed
        # name, namespace included) or its placeholder pattern, whatever its class, so that the shape's sh:class
        # checks the instance's class. A fully generic placeholder (e.g. <Part>) takes in only children of its
        # type or a subtype, as a placeholder that a type defines does (see get_modelling_rule_and_path).
        optional, array, path = shaclg.get_modelling_rule_and_path(browse_name, None, classtype,
                                                                   attribute_prefix, shape=declaration_shape,
                                                                   bridge=attributename)
    if path is not None:
        original_attributename = urllib.parse.quote(browse_name)
        attributename = path
    shacl_rule['optional'] = optional
    shacl_rule['array'] = array
    datasetId = None

    try:
        expanded_type = utils.expand_term(context_graph, instance['type'])
        is_placeholder = shaclg.is_placeholder(expanded_type, attributename) or \
            (declaration_shape is not None and
             shaclg.is_placeholder(None, attributename, shape=declaration_shape))
    except Exception:
        is_placeholder = False
    if is_placeholder:
        if original_attributename is None:
            print(f"Warning: Cannot find proper match in SHACL description for placeholder value \
{attributename}. Will keep it with default datasetId. But it is very likely that the SHACL validation \
will flag this.")
            datasetId = "@none"
        else:
            datasetId = rdfutils.get_semantic_bridge(g, node, o)

    if rdfutils.isObjectNodeClass(nodeclass):
        shacl_rule['is_property'] = False
        # A placeholder child is kept even without content, like its SHACL rule in scan_type_recursive
        child_declaration_shape = shaclg.get_declaration_shape(URIRef(type), attributename) \
            if type is not None else None
        relid = scan_entity(o, classtype, id, shacl_rule['optional'] and not is_placeholder,
                            declaration_shape=child_declaration_shape)
        if relid is not None:
            has_components = True
            full_attribute_name = utils.get_prefixed(context_graph, attributename)
            if instance.get(full_attribute_name) is None:
                instance[full_attribute_name] = []
            attr_instance = jsonld.get_ngsild_relationship(relid)
            if is_placeholder and datasetId is not None:
                attr_instance['datasetId'] = datasetId
            if debug:
                attr_instance['debug'] = \
                    f'{full_attribute_name}, {str(node)}'
            instance[full_attribute_name].append(attr_instance)
            shacl_rule['contentclass'] = classtype
        if not shacl_rule['optional']:
            has_components = True
            shacl_rule['contentclass'] = classtype
    elif rdfutils.isVariableNodeClass(nodeclass):
        shacl_rule['is_property'] = True
        shaclg.get_shacl_iri_and_contentclass(g, o, node, shacl_rule)
        full_attribute_name = utils.get_prefixed(context_graph, attributename)
        try:
            value = next(g.objects(o, basens['hasValue']), None)
            if value is None:
                value = next(g.objects(o, basens['hasValueList']), None)
            if value is not None:
                if not shacl_rule['is_iri']:
                    value = jsonld.get_value(g, value, shacl_rule['datatype'])
                else:
                    # IRI but no Relationship
                    # Currently this means two types: ENUMS and NodeIds
                    # ENUMs need to be queried to translated to IRIs
                    # NodeIDs take directly the IRI from value
                    if shacl_rule['datatype'] == opcuans['NodeId']:
                        e.add_all_objects_of_type(g, value)
                    else:
                        e.add_contentclass_if_missing(g, shacl_rule['contentclass'])
                        value = e.get_contentclasses(g, shacl_rule['contentclass'], value)
                    if isinstance(value, BNode):
                        value = utils.collection_to_list(value, g, scalar_conversion=False)
            else:
                if not shacl_rule['is_iri']:
                    if shacl_rule['isAbstract']:
                        warnmsg = f"Abstract OPCUA DataType \
    {str(shacl_rule.get('orig_datatype'))} in instance attribute {attributename} \
    found without concreate value in {node}."
                        print_warning('abstract_datatype', warnmsg)
                    value = jsonld.get_default_value(shacl_rule['datatype'],
                                                     shacl_rule.get('orig_datatype'),
                                                     shacl_rule.get('value_rank'),
                                                     shacl_rule.get('array_dimensions'), g=g)
                else:
                    value = e.get_default_contentclasses(g,
                                                         shacl_rule['contentclass'],
                                                         shacl_rule.get('value_rank'),
                                                         shacl_rule.get('array_dimensions'))
        except Exception as error:
            logger.error(f"Error processing variable entity: {error}", exc_info=True)
        has_components = True
        if not shacl_rule['is_iri']:
            instance[f'{full_attribute_name}'] = \
                jsonld.get_ngsild_property(value, datatype=shacl_rule['datatype'])
        else:
            if value is None:
                value = jsonld.get_default_iri(shacl_rule['datatype'], shacl_rule.get('value_rank'),
                                               shacl_rule.get('array_dimensions'), g=g)
                if value != []:
                    # Only "valid" case is allowed empty list.
                    warnmsg = f"IRI value is not found for {full_attribute_name} in node {node}." \
                        f"Will use default '{value}' but this might trigger validation problems."
                    print_warning('no_iri_value', warnmsg)
            instance[f'{full_attribute_name}'] = jsonld.get_ngsild_property(value)
        if debug:
            instance[f'{full_attribute_name}']['debug'] = \
                f'{full_attribute_name}, {str(node)}'
        if not is_property:
            create_binding(node_id, o, attributename, shacl_rule)
        attributes = scan_entity_variable(o, classtype, id, shacl_rule['optional'])
        utils.merge_attributes(instance[f'{full_attribute_name}'], attributes)
    return has_components


def create_binding(node_id, var_node, attributename, shacl_rule):
    """Bind a Variable, so that the binding delivers the value in the same form as the instance has it."""
    logic = None
    attribute_type = None
    is_scalar = shacl_rule.get('value_rank') is None or int(shacl_rule['value_rank']) <= 0
    if not shacl_rule['is_iri'] and shacl_rule['datatype'] is not None and RDF.JSON in shacl_rule['datatype']:
        # A structure, or an array of structures, is a JsonProperty like in the instance
        attribute_type = utils.NGSILD['JsonProperty']
    elif is_scalar and shacl_rule['is_iri'] and shacl_rule['datatype'] != opcuans['NodeId']:
        e.add_contentclass_if_missing(g, shacl_rule['contentclass'])
        logic = bindingsg.enum_logic(shacl_rule['contentclass'])
    bindingsg.create_binding(g, URIRef(node_id), var_node, attributename, logic_transform=logic,
                             attribute_type=attribute_type)


def scan_entity_nonrecursive(node, id, instance, node_id, o, generic_reference=None):
    logger.debug(f"Scanning entity non-recursively: {node} for id {id} with generic reference {generic_reference}")
    has_components = False
    shacl_rule = {}
    nodeclass, classtype = rdfutils.get_type(g, o)
    attributename = rdfutils.get_semantic_bridge(g, node, o)
    prefixed_attribute_name = utils.get_prefixed(context_graph, attributename)
    shacl_rule['path'] = entity_namespace[attributename]

    if generic_reference is not None:
        prefixed_attribute_name = g.qname(generic_reference)
    if rdfutils.isObjectNodeClass(nodeclass):
        shacl_rule['is_property'] = False
        relid = rdfutils.generate_node_id(g, rootentity, o, id)
        if relid is not None:
            has_components = True
            if prefixed_attribute_name not in instance:
                instance[prefixed_attribute_name] = []
            toappend = jsonld.get_ngsild_relationship(relid)
            non_followed_nodes.add(o)
            if debug:
                toappend['debug'] = prefixed_attribute_name
            instance[prefixed_attribute_name].append(toappend)
            shacl_rule['contentclass'] = classtype
    elif rdfutils.isVariableNodeClass(nodeclass):
        if type_all is False:
            warnmsg = f"Warning: Variable node {o} is target of non-owning reference {prefixed_attribute_name}."\
                      " This will be ignored."
            print_warning('ignored_variable_reference', warnmsg)
    return has_components


if __name__ == '__main__':

    args = parse_args()
    instancename = args.instance
    rootinstancetype = args.type
    jsonldname = args.jsonld
    entitiesname = args.entities
    shaclname = args.shacl
    bindingsname = args.bindings
    contextname = args.context
    debug = args.debug
    namespace_prefix = args.namespace
    entity_id = args.id
    maximal_shacl = args.maximalshacl
    context_url = args.context_url
    entity_namespace = args.entity_namespace
    parse_properties = args.properties
    value_rank_subshapes_enabled = args.value_rank_subshapes
    semantic_bridge_enabled = args.semantic_bridge
    node_references_enabled = args.semantic_bridge or args.node_references
    shacl_only = args.shacl_only
    type_all = args.type_all
    extract_instance_declarations = args.extract_instance_declarations
    if entity_id is not None and not utils.has_iri_scheme(entity_id):
        print(f"Error: ID prefix '{entity_id}' does not start an IRI, the entity IDs would not be valid. Please use "
              "e.g. urn:mypump:sn1234: or leave it out to get the default urn:uaentity:.")
        sys.exit(1)
    if rootinstancetype is not None and type_all:
        print("Error: root-instance and type-all are mutually exclusive. Please either provide a root-instance or use"
              "type-all to extract all types.")
        sys.exit(1)

    if extract_instance_declarations and not type_all:
        print("Error: extract-instance-declarations only works in combination with type-all. Please use type-all to"
              " extract all types and then extract instance declarations.")
        sys.exit(1)
    # create the context_graph
    # Context graph is resolving the context_url and provides just the
    # namespace manager
    context_graph = libjsonld.get_context_namespaces(context_url)

    # set filter for warning suppressions
    for warnstr in args.suppress_warnings or []:
        message = f"{warnstr}.*"
        warnings.filterwarnings("ignore", message=message)
    entity_namespace = Namespace(f'{namespace_prefix}entity/') if entity_namespace is None else entity_namespace
    shacl_namespace = Namespace(f'{namespace_prefix}shacl/')
    binding_namespace = Namespace(f'{namespace_prefix}bindings/')
    g = Graph(store='Oxigraph')
    g.parse(instancename)
    # get all owl imports
    mainontology = next(g.subjects(RDF.type, OWL.Ontology))
    imports = g.objects(mainontology, OWL.imports)
    if args.recursive_import:
        ontology_loader = OntologyLoader(True)
        ontology_loader.init_imports(imports)
        g += ontology_loader.get_graph()
    else:
        for imprt in imports:
            h = Graph(store="Oxigraph")
            logger.info(f'Importing ontology {imprt}')
            h.parse(imprt)
            g += h
            for k, v in list(h.namespaces()):
                if k != '':
                    g.bind(k, v)

    types = []
    basens = next(Namespace(uri) for prefix, uri in list(g.namespaces()) if prefix == 'base')
    opcuans = next(Namespace(uri) for prefix, uri in list(g.namespaces()) if prefix == 'opcua')
    bindingsg = Bindings(namespace_prefix, basens)
    bindingsg.bind('base', basens)
    bindingsg.bind('binding', binding_namespace)
    shaclg = Shacl(g, namespace_prefix, basens, opcuans, value_rank_subshapes_enabled=value_rank_subshapes_enabled)
    shaclg.bind('shacl', shacl_namespace)
    shaclg.bind('ngsi-ld', ngsildns)
    shaclg.bind('sh', SH)
    shaclg.bind('base', basens)
    e = Entity(namespace_prefix, basens, opcuans)
    e.bind('base', basens)
    e.bind('example', utils.EX)
    e.bind('ngsi-ld', ngsildns)
    rdfutils = RdfUtils(basens, opcuans)
    e.create_ontolgoy_header(entity_namespace)
    # entities.ttl uses uardf terms (the node classes of NodeId targets), so it imports the uardf ontology:
    # the same document the input ontologies import, so a package built from entities.ttl carries it.
    e.add((URIRef(entity_namespace), OWL.imports, uardf_import(g)))
    for k, v in list(g.namespaces()):
        e.bind(k, v)
        shaclg.bind(k, v)

    jsonld = JsonLd(basens, opcuans)
    result = g.query(query_namespaces, initNs={'base': basens, 'opcua': opcuans})
    # The prefixes the namespaces declare (base:hasPrefix), for shacl.ttl as for entities.ttl: an import that
    # names a namespace with a generated ns<N> prefix would otherwise leave it in shacl.ttl (#1226).
    for uri, prefix, _ in result:
        e.bind(prefix, Namespace(uri))
        shaclg.bind(prefix, Namespace(uri))
    ignored_references = rdfutils.get_ignored_references(g)
    ignored_hierarchical_references = get_ignored_hierarchical_references(parse_properties, opcuans)

    # First scan the templates to create the rules
    # If there is a rootinstancetype defined, use it. Otherwise,
    # check if there is a machinery folder
    rootentity = None
    instancetypes = None
    if rootinstancetype is None and not type_all:
        machinery_nodes_and_types = rdfutils.get_machinery_nodes(g)
        if machinery_nodes_and_types is None:
            logger.error("Error: root-instance could not be determined. Neither type given explicitly (via -t) nor a \
Machinery Folder was found in instance ontology.")
            sys.exit(1)
        rootentity = machinery_nodes_and_types[0][0]
        rootinstancetype = machinery_nodes_and_types[0][1]
        if maximal_shacl:
            # Get all types which stem from objects in the entity namespace
            instancetypes = rdfutils.get_object_types_from_namespace(g, mainontology)
        else:
            instancetypes = [rootinstancetype]
    elif type_all:
        instancetypes = utils.get_all_types_in_namespace(g, opcuans["BaseObjectType"], mainontology, basens, opcuans)
    if rootinstancetype is not None:
        try:
            root = next(g.subjects(UARDF['definesType'], URIRef(rootinstancetype)))
        except Exception:
            print(f"Error: root-instance with type {rootinstancetype} not found. Please review the type parameter.")
            sys.exit(1)
        if instancetypes is None:
            instancetypes = [URIRef(rootinstancetype)]
    for instancetype in instancetypes:
        logger.debug(f"Scanning type: {instancetype}")
        root = next(g.subjects(UARDF['definesType'], URIRef(str(instancetype))))
        scan_type(root, instancetype)
    report_deep_additions()
    if shaclname is not None:
        shaclg.serialize(destination=shaclname)
    if shacl_only:
        # If only SHACL shapes are to be created, skip the entity scanning
        sys.exit(0)
    # Then scan the entity with the real values
    rootentities = None
    if extract_instance_declarations:
        rootentities = utils.get_all_objects_in_namespace(g, mainontology, basens, opcuans)
    elif type_all:
        rootentities = utils.get_all_objects_from_object_folder_in_namespace(g, mainontology, basens, opcuans)
    elif rootentity is None:
        # the instance node declares its type by uardf:hasTypeDefinition (rdf:type when the nodeset was
        # created with --enforce-opcua-type-semantic)
        rootentities = [next(g.subjects(UARDF['hasTypeDefinition'], URIRef(rootinstancetype)),
                             next(g.subjects(RDF.type, URIRef(rootinstancetype)), None))]
        if rootentities[0] is None:
            print(f"Error: no instance of type {rootinstancetype} found. Instances are usually dynamic nodes, "
                  "which are only exported when the nodeset was translated with nodeset2owl.py --serverUri.")
            sys.exit(1)
    else:
        rootentities = [rootentity]
    entity_id = f'{entity_id}' if entity_id is not None else None
    non_followed_nodes = set()
    followed_nodes = set()
    for rootentity in rootentities:
        _, type = rdfutils.get_type(g, rootentity)
        scan_entity(rootentity, type, entity_id)
    # Check if nodes from non-hierarchical references are left-out
    for node_id in non_followed_nodes.difference(followed_nodes):
        _, type = rdfutils.get_type(g, node_id)
        scan_entity(node_id, type, entity_id)
    # Did we catch all? If not, give warning
    if len(non_followed_nodes.difference(followed_nodes)) > 0:
        warnstr = "Some nodes referenced by non-hierarchical references are not \
added. This will potentially create validation issues."
        print_warning('non_reached_nodes', warnstr)
    # Add types to entities
    for type in types:
        e.add_subclass(type)
    jsonld.serialize(jsonldname)
    # Add all subclassing to entities
    if entitiesname is not None:
        result = g.query(query_subclasses)
        e.add_subclasses(result)
        e.add_subclasses_recursive(g, UARDF['Node'])
        e.serialize(destination=entitiesname)
    entities_ns = utils.extract_namespaces(e.get_graph())
    shacl_ns = utils.extract_namespaces(shaclg.get_graph())
    # The instances are compacted with the published context (--context-url), whose prefixes may differ from the
    # ones of the ontologies (e.g. DI as 'devices' there, 'di' here). The prefixes the instances use are written
    # into context.jsonld too, so the instances resolve through the generated context as through the published one.
    instances_ns = utils.used_prefixes(jsonld.instances, utils.extract_namespaces(context_graph))
    # One prefix per namespace: a generated ns<N> goes where a proper prefix names the namespace (#1226).
    final_namespaces = utils.merge_namespaces(entities_ns, shacl_ns, instances_ns)
    jsonld.dump_context(contextname, final_namespaces)
    if bindingsg.len() > 0:
        bindingsg.serialize(destination=bindingsname)
