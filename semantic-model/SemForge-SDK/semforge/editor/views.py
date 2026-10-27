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

"""Requests that read: the trees, the pages, the choices a picker offers.

Nothing here writes a file. Views are served from the disk cache while the
package is unchanged (session.view); pages that show verdicts never wait for
them (validation.verdict_page).
"""

import os
import re

from . import session, validation
from .. import __version__
from .analysis import package_root
from .protocol import field, holder_index, local, serialise, server, uri_to_path


def _type_hierarchy(package):
    """[{iri, label, parent}] for every entity type, parent '' at the root."""
    from rdflib import URIRef
    from rdflib.namespace import RDFS

    from ..cooked.choices import entity_types

    entries = entity_types(package)[0]
    known = {entry.iri for entry in entries}
    out = []
    for entry in entries:
        parents = sorted(str(p) for p in package.knowledge.objects(
            URIRef(entry.iri), RDFS.subClassOf) if str(p) in known)
        out.append({'iri': entry.iri, 'label': entry.label,
                    'parent': parents[0] if parents else ''})
    return out


@server.feature('semforge/tree')
def cooked_tree(ls, params):
    """The cooked constraint tree for a package."""
    from ..cooked import build_tree

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        def compute():
            package = session.package_for(root)
            return {'root': root,
                    'roots': [serialise(node) for node in build_tree(package)],
                    # The hierarchy the summary (Types) tree is drawn as.
                    'types': _type_hierarchy(package)}
        return session.view(root, 'constraints', compute, params)
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/choices')
def constraint_choices(ls, params):
    """Candidate values for a parameter at one address.

    Computed here rather than in the extension because which classes are
    offerable is an ontology question -- entity types on one side of the
    NGSI-LD encoding, vocabulary classes on the other -- and a hard-coded list
    in JavaScript would drift from the model the moment somebody adds a class.
    """
    from ..cooked.choices import SEARCH_THRESHOLD, choices_for

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'choices': [], 'note': 'not a SemForge package', 'total': 0}
    try:
        package = session.package_for(root)
        limit = field(params, 'limit') or SEARCH_THRESHOLD
        # Fetch the whole ranked set once and cap it here, so `total` is exact
        # without asking twice. total > len(choices) is what tells the client
        # that local filtering is not enough and it must come back as the user
        # types.
        found, note = choices_for(package, list(field(params, 'path') or []),
                                  field(params, 'parameter'),
                                  search=field(params, 'search'))
        total = len(found)
        if total > limit:
            found = found[:limit]
            note = f'showing {limit} of {total}; keep typing to narrow'
        return {'choices': found, 'note': note, 'total': total}
    except Exception as exc:                       # noqa: BLE001
        return {'choices': [], 'note': str(exc), 'total': 0}


def _serialise_example(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'entity': node.entity, 'path': list(node.path), 'value': node.value,
        'editable': node.editable, 'severity': node.severity,
        'messages': list(node.messages),
        'datasetId': node.dataset_id, 'observations': node.observations,
        'datasets': list(node.datasets),
        'attributePath': list(node.attribute_path), 'file': node.file,
        'entityType': node.entity_type,
        # Which cases include this file. The row is editable either way; this is
        # what lets the edit say how far it reaches before making it.
        'sharedBy': list(node.shared_by),
        # Without this the client has no location and selection reveals
        # nothing -- which is how the examples tree looked inert.
        'definedAt': node.defined_at,
        'children': [_serialise_example(child) for child in node.children],
    }


@server.feature('semforge/model')
def model(ls, params):
    """The model as a tree: the declared cases and the scratchpad, annotated
    with what validation says about them."""
    from ..cooked.examples import build_suite

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    from ..cooked.typepage import PENDING
    from .slim import SLIM

    def build(verdicts):
        return {'root': root,
                'roots': [_serialise_example(n)
                          for n in build_suite(session.package_for(root), verdicts=verdicts)]}

    try:
        verdicts, state = validation.verdicts_for(root)
        if state.state == 'ready':
            payload = session.view(root, 'model', lambda: build(verdicts), params)
        else:
            # Not cached: the tree comes back for the verdicts when they are in.
            payload = dict(build(verdicts if verdicts is not None else PENDING), cached=False)
            if field(params, 'detail') == 'summary' and 'model' in SLIM:
                payload['roots'] = SLIM['model'](payload['roots'], payload)
                payload['detail'] = 'summary'
        return dict(payload, verdicts=state.as_dict())
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


def _serialise_knowledge(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'iri': node.iri, 'definedAt': node.defined_at,
        'shape': node.shape, 'shapeName': node.shape_name,
        'shapeAt': node.shape_at,
        'entity': node.entity, 'entityType': node.entity_type,
        'file': node.file, 'role': node.role,
        'severity': node.severity, 'messages': list(node.messages),
        'children': [_serialise_knowledge(child) for child in node.children],
    }


@server.feature('semforge/methods')
def methods(ls, params):
    """What this server can answer, and where its code lives.

    An extension newer than the server is invisible otherwise: the new icon is
    there, the request comes back "method not found", and the click does
    nothing. This makes that one line in the doctor.
    """
    import semforge

    try:
        registered = sorted(
            name for name in server.protocol.fm.features
            if name.startswith('semforge/'))
    except Exception:                              # noqa: BLE001
        registered = []
    return {'methods': registered,
            'module': os.path.dirname(os.path.abspath(semforge.__file__)),
            'version': __version__}


@server.feature('semforge/knowledge')
def knowledge(ls, params):
    """The ontology: entity hierarchy and vocabularies, with their joins.

    The third of the three views. What it adds over reading knowledge.ttl is
    where it meets the other two -- which class a shape judges, which terms the
    examples actually use -- so the rows carry both locations.
    """
    from ..cooked.knowledge import build_knowledge

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        return session.view(root, 'knowledge', lambda: {
            'root': root,
            'roots': [_serialise_knowledge(n)
                      for n in build_knowledge(session.package_for(root))]}, params)
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


def _serialise_project(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'value': node.value, 'key': node.key, 'doc': node.doc,
        'editable': node.editable, 'definedAt': node.defined_at,
        'severity': node.severity,
        'children': [_serialise_project(child) for child in node.children],
    }


def _cache_row(root):
    from .cache import status

    state = status(root)
    views = len(state['entries'])
    if not views:
        value = 'empty -- the next scan fills it'
    else:
        kib = max(1, round(state['bytes'] / 1024))
        fresh = ('all current' if state['current'] == views
                 else f"{state['current']} of {views} current")
        value = f'{views} view(s) · {kib} KB · {fresh}'
    return {'kind': 'cache', 'label': 'Cache', 'detail':
            'What the views and the Problems panel show, stored per package '
            'and reused while no file of the package (and no SDK file) has '
            'changed. Rescan rebuilds it; deleting it costs only the next '
            'scan.', 'value': value, 'key': '', 'doc': state['path'],
            'editable': False, 'definedAt': '', 'severity': '',
            'children': []}


@server.feature('semforge/cacheStatus')
def cache_status_feature(ls, params):
    from .cache import status

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    return dict(status(root), ok=True, root=root)


@server.feature('semforge/project')
def project(ls, params):
    """What this package IS: its identity, its settings, what it holds.

    The other three views answer what the package SAYS. Two directories called
    `test` are not the same project, and until this there was nowhere to see
    which one you had open, nor to change anything about it.
    """
    from ..cooked.project import build_project

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        payload = session.view(root, 'project', lambda: {
            'root': root,
            'roots': [_serialise_project(n)
                      for n in build_project(session.package_for(root))]})
        # Added after the cache is read: a row about the cache must never be
        # served FROM it.
        payload['roots'] = payload['roots'] + [_cache_row(root)]
        return payload
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/valueChoices')
def value_choices_feature(ls, params):
    """What the shape allows as a value for one example attribute.

    Separate from `semforge/choices`: that one answers "what may this SHACL
    parameter say", this one answers "what may this datum be". A sh:class on
    the value slot means the value is an individual of that class, so the
    options are individuals -- or, for a relationship, entity ids.
    """
    from ..cooked.shapelink import other_entities, value_choices

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'choices': [], 'note': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        found, note = value_choices(package,
                                    field(params, 'entityType') or '',
                                    field(params, 'attribute') or '',
                                    limit=field(params, 'limit') or 200,
                                    search=field(params, 'search'))
        answer = {'choices': found, 'note': note}
        if field(params, 'relationship'):
            # Any entity may be the target; the shape's are listed first.
            file = field(params, 'file') or None
            inside = file and os.path.abspath(file).startswith(os.path.abspath(root) + os.sep)
            answer['others'] = other_entities(package, [c['value'] for c in found],
                                              file if inside else None)
        return answer
    except Exception as exc:                       # noqa: BLE001
        return {'choices': [], 'note': str(exc)}


@server.feature('semforge/entityTypes')
def entity_types_feature(ls, params):
    """Every type an entity may be given, as the KNOWLEDGE declares it.

    The editor offers these and nothing else. A type typed by hand is the
    quietest way to break a model -- no shape targets it, so every constraint
    stays silent and the entity reads as validated.
    """
    from ..cooked.choices import entity_types
    from ..cooked.constrain import own_shape

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'types': [], 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        found, hierarchy = entity_types(package)
        if hierarchy is None:
            return {'types': [], 'root': '',
                    'error': 'this package has no entity hierarchy: no shape '
                             'declares an sh:targetClass and semforge.yaml '
                             'declares no entityRoot.'}
        return {'root': hierarchy,
                'types': [{'iri': t.iri, 'term': t.term, 'label': t.label,
                           'parent': t.parent, 'shape': t.shape,
                           # `shape` is the nearest judging shape, inherited
                           # or not; a NEW attribute belongs in its own one.
                           'ownShape': own_shape(package, t.iri) or '',
                           'instances': t.instances, 'isRoot': t.is_root}
                          for t in found]}
    except Exception as exc:                       # noqa: BLE001
        return {'types': [], 'error': str(exc)}


@server.feature('semforge/attributes')
def attributes_feature(ls, params):
    """The attributes an entity of this type may carry, as the knowledge says.

    `rdfs:domain` is the join, and it is inherited: a Plasmacutter carries what
    a Cutter carries and what a Machine carries. Attributes the package
    declares without a domain come back separately rather than being hidden --
    a package may simply not have said.

    With `parent`, it answers the other question instead: which attributes may
    nest INSIDE that one. Sub-attributes are excluded from the entity answer,
    because an entity does not carry them -- `hasTrust` belongs inside
    `hasFilter`, and offering it on a Filter would put it where no shape looks.
    """
    from ..cooked.choices import attributes_for, sub_attributes_for

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'attributes': [], 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)

        def out(entry, scoped):
            return {'iri': entry.iri, 'term': entry.term, 'label': entry.label,
                    'kind': entry.kind, 'domain': entry.domain,
                    'parents': list(entry.parents),
                    'carrierKind': entry.carrier_kind,
                    'comment': entry.comment, 'constrained': entry.constrained,
                    'definedAt': entry.defined_at, 'scoped': scoped}

        # A sub-attribute hangs off an ATTRIBUTE, so it is asked for by naming
        # that attribute rather than an entity type -- and where it may appear
        # is read from the shapes, which is the only place that says it.
        parent = field(params, 'parent', '')
        if parent:
            return {'parent': parent,
                    'attributes': [out(e, True)
                                   for e in sub_attributes_for(package, parent)]}

        if field(params, 'all'):
            from ..cooked.choices import attribute_terms
            return {'attributes': [out(e, bool(e.domain_iri))
                                   for e in attribute_terms(package)
                                   if e.ngsild]}
        mine, open_ended = attributes_for(package,
                                          field(params, 'entityType', ''))
        return {'attributes': [out(e, True) for e in mine] +
                              [out(e, False) for e in open_ended]}
    except Exception as exc:                       # noqa: BLE001
        return {'attributes': [], 'error': str(exc)}


@server.feature('semforge/attributeNamespaces')
def attribute_namespaces_feature(ls, params):
    """Where a new attribute may live; the carrying type's namespace first."""
    from ..cooked.knowledge import attribute_namespaces

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'namespaces': [], 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        return {'namespaces': attribute_namespaces(
            package, field(params, 'domain', ''))}
    except Exception as exc:                       # noqa: BLE001
        return {'namespaces': [], 'error': str(exc)}


@server.feature('semforge/kinds')
def kinds(ls, params):
    from ..ngsild.build import KINDS

    return {'kinds': list(KINDS)}


@server.feature('semforge/attributeOptions')
def attribute_options_feature(ls, params):
    """The attributes that may be added to a shape, each with its state.

    `free` ones can be added; `here` and `inherited` ones are listed anyway, so
    the picker can say WHY an attribute the author expected is not offered
    rather than leaving them to wonder whether it was declared at all.
    """
    from ..cooked.constrain import (attribute_options, shape_targets,
                                    sub_attribute_options)

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'options': [], 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        shape = field(params, 'shape')
        parent_path = list(field(params, 'parentPath') or [])
        if parent_path:
            # Inside an attribute: what may nest there, and the attribute
            # itself as the carrier a NEW sub-attribute is declared for.
            return {'options': sub_attribute_options(package, shape, parent_path),
                    'targets': [parent_path[-1]], 'carrier': parent_path[-1]}
        # The targets let the picker's "New attribute..." declare the new term
        # for the type this shape judges, without asking again.
        return {'options': attribute_options(package, shape),
                'targets': shape_targets(package, shape)}
    except Exception as exc:                       # noqa: BLE001
        return {'options': [], 'error': str(exc)}


@server.feature('semforge/attributePlaces')
def attribute_places_feature(ls, params):
    """Where an attribute is constrained: each shape and sh:path chain."""
    from ..cooked.constrain import attribute_places

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'places': [], 'error': 'not a SemForge package'}
    try:
        return {'places': attribute_places(session.package_for(root),
                                           field(params, 'attribute'))}
    except Exception as exc:                       # noqa: BLE001
        return {'places': [], 'error': str(exc)}


@server.feature('semforge/typePage')
def type_page_feature(ls, params):
    """Everything about one entity type, for the type page. Cached per type."""
    from ..cooked.typepage import build_type_page

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    entity_type = str(field(params, 'entityType', '') or '')
    key = 'type-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', entity_type)[-120:]
    try:
        return validation.verdict_page(root, key, lambda verdicts: build_type_page(
            session.package_for(root), entity_type, verdicts))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/shapePage')
def shape_page_feature(ls, params):
    """Everything about one shape, whatever it targets. Cached per shape."""
    from ..cooked.shapepage import build_shape_page

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    shape = str(field(params, 'shape', '') or '')
    key = 'shape-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', shape)[-120:]
    try:
        return validation.verdict_page(root, key, lambda verdicts: build_shape_page(
            session.package_for(root), shape, verdicts))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/vocabularyPage')
def vocabulary_page_feature(ls, params):
    """One vocabulary class: its values, their uses, what draws from it."""
    from ..cooked.vocabulary import build_vocabulary_page

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    cls = str(field(params, 'cls', '') or '')
    key = 'vocab-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', cls)[-120:]
    try:
        page = session.view(root, key, lambda: {
            'page': build_vocabulary_page(session.package_for(root), cls)})
        return dict(page['page'], ok=True, root=root, cached=page['cached'])
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/vocabularyClasses')
def vocabulary_classes_feature(ls, params):
    """Every vocabulary class, for a picker."""
    from rdflib import URIRef

    from ..cooked.vocabulary import vocabulary_classes
    from ..validate.normalise import curie, local

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'classes': [], 'error': 'not a SemForge package'}
    package = session.package_for(root)
    return {'classes': [{'iri': c, 'label': local(c),
                         'term': curie(package.knowledge, URIRef(c))}
                        for c in sorted(vocabulary_classes(package),
                                        key=lambda c: local(c).lower())]}


@server.feature('semforge/vocabularyNamespaces')
def vocabulary_namespaces_feature(ls, params):
    """Where a new vocabulary term may live; the usual place first. `near` is
    the class it belongs to or derives from, if any."""
    from ..cooked.vocabulary import vocabulary_namespaces

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'namespaces': [], 'error': 'not a SemForge package'}
    try:
        return {'namespaces': vocabulary_namespaces(
            session.package_for(root), field(params, 'near', '') or None)}
    except Exception as exc:                       # noqa: BLE001
        return {'namespaces': [], 'error': str(exc)}


@server.feature('semforge/attributeTestOptions')
def attribute_test_options_feature(ls, params):
    """What a test for one attribute of a type can prove."""
    from ..expect.attributecase import attribute_test_options

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        found = attribute_test_options(session.package_for(root),
                                       field(params, 'entityType', ''),
                                       list(field(params, 'path', []) or []))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(found, ok=True)


@server.feature('semforge/testCaseOptions')
def test_case_options_feature(ls, params):
    """What New test case… can offer: suites, shapes, cases, entities, files."""
    from ..expect.addcase import case_options

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(case_options(session.package_for(root)), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/units')
def units_feature(ls, params):
    """Every unit the package can say -- the curated Rec 20 set and its own --
    matching `query` when given, and the quantities they measure. With `shape`
    and `path`, also the units that attribute's shape allows; with
    `entityType` and `attribute`, those of the attribute on that type."""
    from ..cooked.units import attribute_units, quantities, search_units

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        answer = {'ok': True, 'units': search_units(package, field(params, 'query', '') or ''),
                  'quantities': quantities(package), 'allowed': [], 'required': False}
        shape, path = field(params, 'shape'), list(field(params, 'path') or [])
        entity_type, attribute = field(params, 'entityType'), field(params, 'attribute')
        if shape and path:
            allowed = attribute_units(package, shape, path)
            answer.update(allowed=allowed['codes'], required=allowed['required'])
        elif entity_type and attribute:
            from ..cooked.typepage import build_type_page

            page = build_type_page(package, entity_type)
            row = next((r for r in page.get('attributes', []) if attribute in
                        (r['term'], r['attribute'], r['label'])), None)
            if row is not None:
                answer.update(allowed=row.get('units', []),
                              required=row.get('unitRequired', False))
        return answer
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/severityLevels')
def severity_levels_feature(ls, params):
    """The severity levels a constraint may name, and the classes they come from."""
    from ..cooked.severity import levels, severity_classes

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        return {'ok': True, 'levels': levels(package), 'classes': severity_classes(package)}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/modelPage')
def model_page_feature(ls, params):
    """The model data as cards, each entity with its violations; edited like
    a case. Cached like every view, so a reopen is cheap."""
    from ..cooked.casepage import build_model_page

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return validation.verdict_page(root, 'model-page', lambda verdicts: build_model_page(
            session.package_for(root), verdicts))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlBench')
def sparql_bench_feature(ls, params):
    """The SPARQL workbench: one query of a shape, the data it runs over.
    Not cached: it is opened to be changed."""
    from ..cooked.sparqlbench import MAIN, bench_page

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        page = bench_page(session.package_for(root), str(field(params, 'shape', '') or ''),
                          field(params, 'index'), field(params, 'source') or MAIN,
                          field(params, 'query'), field(params, 'kind'))
        return dict(page, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlRun')
def sparql_run_feature(ls, params):
    """Run an edited query the way validation would. Writes nothing."""
    from ..cooked.sparqlbench import MAIN, run_query

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return run_query(session.package_for(root), str(field(params, 'shape', '') or ''),
                         field(params, 'index') or 0, field(params, 'source') or MAIN,
                         str(field(params, 'query', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlInspect')
def sparql_inspect_feature(ls, params):
    """The query taken apart, text untouched: every variable of every row its
    WHERE makes, and which FILTER part dropped the rows it dropped."""
    from ..cooked.sparqlbench import MAIN, inspect

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return inspect(session.package_for(root), str(field(params, 'shape', '') or ''),
                       field(params, 'index') or 0, field(params, 'source') or MAIN,
                       str(field(params, 'query', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlRemovalPlan')
def sparql_removal_plan_feature(ls, params):
    """What removing one SPARQL query would take with it: asked first."""
    from ..cooked.sparqlbench import removal_plan

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        shape = str(field(params, 'shape', '') or '')
        return dict(removal_plan(package, shape, holder_index(package, shape, params)), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/shapeAt')
def shape_at_feature(ls, params):
    """The node shape whose name is under the cursor -- what F2 renames.

    The range is the name's local part (`StateOnCutterShape` of
    `iffBaseShacl:StateOnCutterShape`, the whole `<IRI>` when written out),
    so the rename box shows what is being renamed. A term inside a string --
    a SPARQL body -- is not offered: the rename carries those along anyway.
    """
    from rdflib import URIRef
    from rdflib.namespace import RDF, SH

    from ..rdfio.turtle_index import terms

    uri = field(params, 'uri', '')
    root = package_root(uri_to_path(uri))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        document = ls.workspace.get_text_document(uri)
        text = document.source
    except Exception:                              # noqa: BLE001 -- not open: read it
        with open(uri_to_path(uri), encoding='utf-8') as handle:
            text = handle.read()
    line, character = int(field(params, 'line', 0)), int(field(params, 'character', 0))
    package = session.package_for(root)
    for term in terms(text):
        if term.quoted or term.line - 1 != line or \
                not term.column <= character <= term.column + len(term.raw):
            continue
        if (URIRef(term.iri), RDF.type, SH.NodeShape) not in package.shapes:
            break
        start = term.column + (term.raw.index(':') + 1 if not term.raw.startswith('<') else 0)
        return {'ok': True, 'shape': term.iri, 'placeholder': local(term.iri),
                'range': {'start': {'line': line, 'character': start},
                          'end': {'line': line, 'character': term.column + len(term.raw)}}}
    return {'ok': False, 'error': 'F2 renames a shape: put the cursor on its name'}


@server.feature('semforge/shapes')
def shapes_feature(ls, params):
    """Every named shape with its target in words, for the SHACL Shapes view."""
    from ..cooked.shapes import build_shapes

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        return session.view(root, 'shapes', lambda: {
            'root': root, 'roots': build_shapes(session.package_for(root))}, params)
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/valueForms')
def value_forms_feature(ls, params):
    """What an attribute's value may be: its forms, each with its conditions
    (cooked/valueforms.py) -- the value editor."""
    from rdflib import URIRef

    from ..cooked.valueforms import read_value, to_payload
    from ..errors import PackageError

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        shape, chain = field(params, 'shape'), list(field(params, 'path') or [])
        holder = package.index('shapes').file_for(URIRef(shape))
        if holder is None:
            raise PackageError(f'{shape} is not in any shapes file')
        with open(holder, encoding='utf-8') as handle:
            value = read_value(package, handle.read(), shape, chain)
        return dict(to_payload(value), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/casePage')
def case_page_feature(ls, params):
    """One test case: its claims, whether they hold, its data. Cached."""
    from ..cooked.casepage import build_case_page

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    case = str(field(params, 'case', '') or '')
    key = 'case-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', case)[-120:]
    try:
        return validation.verdict_page(root, key, lambda verdicts: build_case_page(
            session.package_for(root), case, verdicts))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/health')
def health_feature(ls, params):
    """The package health page: figures, and what needs attention first."""
    from ..cooked.health import build_health

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        page = session.view(root, 'health', lambda: {'page': build_health(session.package_for(root))})
        result = dict(page['page'], ok=True, root=root, cached=page['cached'])
        # The cache figures are read live: a page about the cache must not be
        # served from it.
        from .cache import status
        state = status(root)
        result['tiles'] = dict(result['tiles'], cacheViews=len(state['entries']),
                               cacheCurrent=state['current'])
        return result
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
