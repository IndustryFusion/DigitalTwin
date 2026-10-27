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

"""Requests that write: every change to a package's files, and the plans
that say what one would do before it is made.

Each writes through cooked/, then tells the session the package changed
(session.forget) and publishes the changed file's diagnostics again.
"""

import os

from . import session, validation
from ..validate import validate_package
from .analysis import package_root
from .protocol import field, holder_index, path_to_uri, server, uri_to_path


@server.feature('semforge/init')
def init_package(ls, params):
    """Create a package in a directory, and say what was written.

    The editor asks for this rather than shelling out to the CLI: the scaffold
    is the SDK's business, and a package created by a different code path would
    drift from the one `semforge init` produces.
    """
    from ..package.scaffold import create_package

    target = uri_to_path(field(params, 'uri', '')) or field(params, 'path')
    if not target:
        return {'ok': False, 'error': 'no directory given'}
    try:
        os.makedirs(target, exist_ok=True)
        written = create_package(
            target, name=field(params, 'name'),
            namespace=field(params, 'namespace'),
            layout=field(params, 'layout') or 'grouped')
        package = session.package_for(target)
        report = validate_package(package, strict=False)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    session.forget(target)
    return {'ok': True, 'root': target, 'files': written,
            'open': package.sources['shapes'],
            'constraints': len(report.results),
            'violations': len(report.violations)}


@server.feature('semforge/rescan')
def rescan_feature(ls, params):
    """Throw away everything known about the package and analyse it again.

    The escape hatch for the case the fingerprint cannot see -- a change it
    does not track, or a cache somebody distrusts. The views recompute on
    their next request, which the client makes right after.
    """
    from .cache import clear

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    clear(root)
    session.forget(root)
    validation.publish(ls, path_to_uri(root))
    return {'ok': True, 'root': root}


@server.feature('semforge/clearCache')
def clear_cache_feature(ls, params):
    """Delete the package's cache; with `contexts`, the downloaded ones too."""
    from .cache import clear

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    freed = clear(root, contexts=bool(field(params, 'contexts', False)))
    return {'ok': True, 'root': root, 'bytes': freed}


@server.feature('semforge/setSetting')
def set_setting(ls, params):
    """Write one setting into semforge.yaml, keeping the file's comments.

    Line-based rather than a YAML round-trip: the comments are most of that
    file -- a paragraph above each key saying what it decides -- and a
    round-trip drops every one of them.
    """
    from ..package import config

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    key = field(params, 'key', '')
    if key not in {entry[0] for entry in config.SPEC}:
        return {'ok': False, 'error': f'{key} is not an editable setting'}
    try:
        where, line = config.set_value(root, key, field(params, 'value', ''))
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}
    session.forget(root)                      # it must be re-read
    return {'ok': True, 'key': key, 'file': where, 'line': line,
            'uri': path_to_uri(where)}


@server.feature('semforge/shapeFor')
def shape_for_attribute(ls, params):
    """Where the shape that judges this attribute is declared.

    With `create` set, an absent one is written as an empty property shape: the
    point of the jump is to change the constraint, and there is nothing to
    change when no shape mentions the attribute. The stub is reported as
    created so the client can say so -- it constrains nothing yet, and the
    capability check will call that out.
    """
    from ..cooked.shapelink import ensure_property_shape, find_property_shape

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    entity_type = field(params, 'entityType') or ''
    attribute = field(params, 'attribute') or ''
    if not entity_type or not attribute:
        return {'ok': False,
                'error': 'need both an entity type and an attribute name'}
    try:
        package = session.package_for(root)
        if field(params, 'create'):
            found, how = ensure_property_shape(package, entity_type, attribute)
            if how == 'created':
                session.forget(root)
                validation.publish(ls, path_to_uri(package.sources['shapes']))
        else:
            found, how = find_property_shape(package, entity_type,
                                             attribute), 'found'
            if found is None:
                return {'ok': False, 'exists': False,
                        'error': f'no shape constrains {attribute} '
                                 f'on {entity_type}'}
        return {'ok': True, 'how': how, **found}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/setValue')
def set_example_value(ls, params):
    """Change one value in the example, then re-validate.

    Re-publishing afterwards is the point: the reason to edit data here rather
    than in the JSON is to watch the verdict move.
    """
    from ..cooked.examples import set_value

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        path, old, new = set_value(package, field(params, 'entity'),
                                   list(field(params, 'path') or []),
                                   field(params, 'value'),
                                   file=field(params, 'file'))
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'old': old, 'new': new}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addObservation')
def add_observation_feature(ls, params):
    """Append an observation to one attribute's series."""
    from ..cooked.examples import add_observation

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        path, count = add_observation(
            package, field(params, 'entity'),
            list(field(params, 'attributePath') or []),
            field(params, 'datasetId'), field(params, 'value'),
            field(params, 'observedAt'), file=field(params, 'file'))
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'count': count}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


def _instance_write(ls, params, write):
    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        made = write(package)
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addInstance')
def add_instance_feature(ls, params):
    """Another instance of an attribute, under a new datasetId."""
    from ..cooked.examples import add_instance

    return _instance_write(ls, params, lambda package: add_instance(
        package, field(params, 'entity'), list(field(params, 'attributePath') or []),
        field(params, 'datasetId'), file=field(params, 'file')))


@server.feature('semforge/setObservedAt')
def set_observed_at_feature(ls, params):
    """One instance's observedAt -- set, changed, or (empty) removed."""
    from ..cooked.examples import set_observed_at

    return _instance_write(ls, params, lambda package: set_observed_at(
        package, field(params, 'entity'), list(field(params, 'attributePath') or []),
        field(params, 'index', 0) or 0, field(params, 'observedAt', '') or '',
        file=field(params, 'file')))


@server.feature('semforge/sortObservations')
def sort_observations_feature(ls, params):
    """One datasetId's observations in time order, the latest last."""
    from ..cooked.examples import sort_observations

    return _instance_write(ls, params, lambda package: sort_observations(
        package, field(params, 'entity'), list(field(params, 'attributePath') or []),
        field(params, 'datasetId', '') or '', file=field(params, 'file')))


@server.feature('semforge/setDatasetId')
def set_dataset_id_feature(ls, params):
    """Change one instance's datasetId (every observation of it)."""
    from ..cooked.examples import set_dataset_id

    return _instance_write(ls, params, lambda package: set_dataset_id(
        package, field(params, 'entity'), list(field(params, 'attributePath') or []),
        field(params, 'old'), field(params, 'new'), file=field(params, 'file'),
        index=field(params, 'index', None)))


@server.feature('semforge/addAttribute')
def add_attribute_feature(ls, params):
    """Add an attribute, with the kind the shapes say it should be."""
    from ..cooked.examples import add_attribute

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        path, kind = add_attribute(
            package, field(params, 'entity'), field(params, 'name'),
            kind=field(params, 'kind'), value=field(params, 'value'),
            file=field(params, 'file'),
            # A sub-attribute: the address of the attribute instance it hangs
            # off, as the Model-view row carries it.
            under=list(field(params, 'under') or []) or None,
            dataset=field(params, 'underDataset') or None,
            observedAt=field(params, 'observedAt'),
            datasetId=field(params, 'datasetId'),
            unitCode=field(params, 'unitCode') or None)
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'kind': kind}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addEntity')
def add_entity_feature(ls, params):
    """Append a legal NGSI-LD entity to an example file."""
    from ..cooked.examples import add_entity

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        path, count = add_entity(
            package, field(params, 'id'), field(params, 'entityType'),
            file=field(params, 'file'))
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'count': count}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addEntityType')
def add_entity_type_feature(ls, params):
    """Declare a new entity type in the knowledge, beneath an existing one.

    The way a missing type becomes usable: it is added to the ontology first,
    and the entity is typed with it afterwards.
    """
    from ..cooked.knowledge import add_entity_type

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        made = add_entity_type(package, field(params, 'name'),
                               field(params, 'parent'))
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return dict(made, ok=True, uri=path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addNamespace')
def add_namespace_feature(ls, params):
    """Define a namespace name for the whole package.

    Prefixes are a package-wide table, agreed once. Until this there was no way
    to add to it from the editor at all -- you found semforge.yaml and typed.
    """
    from ..package.prefixes import add_namespace

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_namespace(root, field(params, 'prefix'),
                             field(params, 'namespace'))
        session.forget(root)
        validation.publish(ls, path_to_uri(session.package_for(root).sources['shapes']))
        return dict(made, ok=True, uri=path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/removeNamespace')
def remove_namespace_feature(ls, params):
    """Drop a name from the package's table, unless something needs it.

    A name that is IN USE is not removed on the first ask, even when removing
    it is safe: the answer comes back as a question, with what binds it and
    why it is safe, and the editor asks before trying again with `force`.
    """
    from ..package.prefixes import plan_removal, remove_namespace

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        force = bool(field(params, 'force', False))
        plan = plan_removal(root, field(params, 'prefix'), package=package)
        if not plan['removable']:
            return {'ok': False, 'error': plan['reason']}
        if plan['in_use'] and not force:
            return {'ok': False, 'confirm': True, 'detail': plan['reason'],
                    'prefix': plan['prefix'],
                    'files': plan.get('usage', {}).get('files', []),
                    'terms': plan.get('usage', {}).get('terms', 0)}
        gone = remove_namespace(root, field(params, 'prefix'),
                                package=package, force=True)
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return {'ok': True, 'prefix': gone['prefix'],
                'namespace': gone['namespace'], 'file': gone['file'],
                'line': gone['line'], 'survivesAs': gone.get('survives_as', ''),
                'survivesVia': gone.get('survives_via', ''),
                'uri': path_to_uri(gone['file'])}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/deletionPlan')
def deletion_plan_feature(ls, params):
    """What deleting this package would take with it. Deletes nothing.

    The editor does the deleting, because it can move a directory to the trash
    rather than unlinking it. What it cannot do is read the package: which of
    those files are the package, which are somebody's, and whether git has any
    of them.
    """
    from ..package.removal import plan_deletion

    target = uri_to_path(field(params, 'uri', '')) or field(params, 'path', '')
    root = package_root(target) or target
    plan = plan_deletion(root)
    return {
        'ok': not plan.error, 'error': plan.error, 'path': plan.path,
        'name': plan.name, 'files': plan.files, 'bytes': plan.bytes,
        'strangers': plan.strangers, 'nested': plan.nested,
        'inGit': plan.in_git, 'tracked': plan.tracked,
        'untracked': plan.untracked, 'warnings': plan.warnings,
    }


@server.feature('semforge/addAttributeTerm')
def add_attribute_term_feature(ls, params):
    """Declare a new attribute in the knowledge, carried by an entity type."""
    from ..cooked.knowledge import add_attribute_term

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        made = add_attribute_term(package, field(params, 'name'),
                                  field(params, 'kind'),
                                  field(params, 'domain'),
                                  label=field(params, 'label', ''),
                                  namespace=field(params, 'namespace') or None)
        session.forget(root)
        validation.publish(ls, path_to_uri(package.sources['shapes']))
        return dict(made, ok=True, uri=path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/attributeRemovalPlan')
def attribute_removal_plan_feature(ls, params):
    """Everything deleting an attribute would touch. Writes nothing."""
    from ..cooked.remove_attribute import plan_attribute_removal

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        plan = plan_attribute_removal(package, field(params, 'attribute'))
        return dict(plan.as_dict(root), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/removeAttribute')
def remove_attribute_feature(ls, params):
    """Delete an attribute and its removable dependents, all or nothing.

    `force` is the author's yes to the plan they were shown; without it an
    attribute in use is refused, so a client that skipped the plan cannot
    delete more than it displayed.
    """
    from ..cooked.remove_attribute import remove_attribute, remove_declaration

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        # `declarationOnly`: the declaration goes, every use stays.
        remove = remove_declaration if field(params, 'declarationOnly') \
            else remove_attribute
        plan, notes = remove(package, field(params, 'attribute'),
                             force=bool(field(params, 'force', False)))
        session.forget(root)
        for path in package.files('shapes'):
            validation.publish(ls, path_to_uri(path))
        return dict(plan.as_dict(root), ok=True, notes=notes)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/setConstraint')
def set_constraint(ls, params):
    """Apply one cooked edit, then re-analyse so diagnostics follow it."""
    from ..cooked import apply_edit, remove_constraint

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        shape = field(params, 'shape')
        chain = list(field(params, 'path') or [])
        parameter = field(params, 'parameter')
        if field(params, 'add'):
            # Add a constraint the attribute does not carry yet (or replace one
            # it does), on the attribute node or on its value.
            from ..cooked.tree import add_constraint

            done = add_constraint(package, shape, chain, parameter,
                                  # An sh:in list arrives as a list of items.
                                  field(params, 'value') if isinstance(
                                      field(params, 'value'), list)
                                  else str(field(params, 'value')),
                                  field(params, 'layer', 'value') or 'value')
            session.forget(root)
            validation.publish(ls, path_to_uri(done['file']))
            return dict(done, ok=True)
        if field(params, 'remove'):
            path, changed = remove_constraint(package, shape, chain, parameter)
        else:
            path, changed = apply_edit(package, shape, chain, parameter,
                                       str(field(params, 'value')))
        session.forget(root)                  # the file changed underneath
        validation.publish(ls, path_to_uri(path))
        return {'ok': True, 'file': path, 'bytesChanged': changed}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addAttributeConstraint')
def add_attribute_constraint_feature(ls, params):
    """Add an attribute to a shape as a complete two-layer property shape.

    `shape` names the shape; `entityType` instead means that type's OWN shape,
    which is what a flow that starts from a type rather than a tree row has.
    """
    from ..cooked.constrain import (add_attribute_constraint,
                                    add_sub_attribute_constraint, own_shape)

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        shape = field(params, 'shape')
        entity_type = field(params, 'entityType', '') or ''
        if not shape:
            shape = own_shape(package, entity_type)
            if shape is None:
                return {'ok': False,
                        'error': f'no shape targets {entity_type} itself, so '
                                 f'there is nowhere to constrain it'}
        # Whose page shows it: the client opens it there, the new row marked.
        target = entity_type or _target_class(package, shape)
        parent_path = list(field(params, 'parentPath') or [])
        if parent_path:
            made = add_sub_attribute_constraint(
                package, shape, parent_path, field(params, 'attribute'),
                required=bool(field(params, 'required', False)),
                datatype=field(params, 'datatype') or None,
                value_class=field(params, 'valueClass') or None)
            session.forget(root)
            validation.publish(ls, path_to_uri(made['file']))
            return dict(made, ok=True, uri=path_to_uri(made['file']), targetClass=target)
        made = add_attribute_constraint(
            package, shape, field(params, 'attribute'),
            required=bool(field(params, 'required', False)),
            datatype=field(params, 'datatype') or None,
            value_class=field(params, 'valueClass') or None,
            extend_domain=bool(field(params, 'extendDomain', False)))
        session.forget(root)                  # the file changed underneath
        validation.publish(ls, path_to_uri(made['file']))
        if made.get('domainAdded'):
            for path in session.package_for(root).files('knowledge'):
                validation.publish(ls, path_to_uri(path))
        return dict(made, ok=True, uri=path_to_uri(made['file']), targetClass=target)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


def _target_class(package, shape):
    """The class a shape targets, '' when none: the type whose page shows it."""
    from rdflib import URIRef

    from ..validate.shapes import class_targets

    found = sorted(str(c) for c in class_targets(package.shapes, URIRef(shape)))
    return found[0] if found else ''


def _vocabulary_write(params, write):
    """Run one vocabulary write; the views re-read it from the changed files."""
    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        result = write(session.package_for(root))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(result, ok=True)


@server.feature('semforge/addVocabularyClass')
def add_vocabulary_class_feature(ls, params):
    from ..cooked.vocabulary import add_vocabulary_class

    return _vocabulary_write(params, lambda package: add_vocabulary_class(
        package, field(params, 'name', ''), field(params, 'namespace', None),
        field(params, 'parent', None), field(params, 'label', '') or ''))


@server.feature('semforge/addVocabularyValue')
def add_vocabulary_value_feature(ls, params):
    from ..cooked.vocabulary import add_value

    return _vocabulary_write(params, lambda package: add_value(
        package, field(params, 'cls', ''), field(params, 'name', ''),
        field(params, 'label', '') or '', field(params, 'namespace', None) or None))


@server.feature('semforge/setValueLabel')
def set_value_label_feature(ls, params):
    from ..cooked.vocabulary import set_value_label

    return _vocabulary_write(params, lambda package: set_value_label(
        package, field(params, 'value', ''), field(params, 'label', '') or ''))


@server.feature('semforge/removeVocabularyValue')
def remove_vocabulary_value_feature(ls, params):
    from ..cooked.vocabulary import remove_value

    return _vocabulary_write(params, lambda package: remove_value(
        package, field(params, 'value', ''), bool(field(params, 'force', False))))


@server.feature('semforge/newAttributeTest')
def new_attribute_test_feature(ls, params):
    """Write a test for one attribute: valid, or one constraint firing."""
    from ..expect.attributecase import new_attribute_test

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = new_attribute_test(session.package_for(root), field(params, 'entityType', ''),
                                  list(field(params, 'path', []) or []),
                                  str(field(params, 'purpose', '') or ''),
                                  str(field(params, 'name', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(made, ok=True)


@server.feature('semforge/addTestCase')
def add_test_case_feature(ls, params):
    """Write and declare a test case, then run it once."""
    from ..expect.addcase import add_test_case

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_test_case(session.package_for(root), field(params, 'suite', ''),
                             field(params, 'expect', 'valid'),
                             field(params, 'start', 'empty'),
                             str(field(params, 'source', '') or ''),
                             str(field(params, 'name', '') or ''),
                             str(field(params, 'description', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(made, ok=True)


@server.feature('semforge/addUnit')
def add_unit_feature(ls, params):
    """A unit of the package's own, in its knowledge."""
    from ..cooked.units import add_unit

    return _package_write(ls, params, lambda package: add_unit(
        package, field(params, 'code', ''), field(params, 'name', ''),
        field(params, 'quantity', ''), field(params, 'symbol', '') or '',
        field(params, 'namespace', None) or None))


@server.feature('semforge/setUnits')
def set_units_feature(ls, params):
    """Which units an attribute's instances may say, in its shape."""
    from ..cooked.units import set_units

    return _package_write(ls, params, lambda package: set_units(
        package, field(params, 'shape'), list(field(params, 'path') or []),
        list(field(params, 'codes') or []), bool(field(params, 'required', False))))


@server.feature('semforge/setUnitCode')
def set_unit_code_feature(ls, params):
    """One instance's unitCode in the data -- every observation of it."""
    from ..cooked.units import set_unit_code

    return _instance_write(ls, params, lambda package: set_unit_code(
        package, field(params, 'entity'), list(field(params, 'attributePath') or []),
        field(params, 'datasetId', '') or '', field(params, 'code', '') or '',
        file=field(params, 'file')))


@server.feature('semforge/setSeverity')
def set_severity_feature(ls, params):
    """Set (or clear) sh:severity on an attribute constraint or a SPARQL constraint."""
    from ..cooked.severity import set_severity

    holder = field(params, 'holder', None)
    query = field(params, 'query', '')

    def write(package):
        index = holder
        if index is None and query:
            # The shape page knows its queries by their text, not their place.
            from ..cooked.sparqlbench import holders
            index = next((h['index'] for h in holders(package, field(params, 'shape', ''))
                          if h['query'].strip() == str(query).strip()), None)
            if index is None:
                raise ValueError('that SPARQL query is not on the shape any more')
        return set_severity(
            package, field(params, 'shape', ''), list(field(params, 'path', []) or []) or None,
            int(index) if index is not None else None, field(params, 'severity', '') or None)

    return _package_write(ls, params, write)


@server.feature('semforge/addSeverityLevel')
def add_severity_level_feature(ls, params):
    """A new severity level: an individual of sh:Severity or a class derived from it."""
    from ..cooked.severity import add_level

    return _package_write(ls, params, lambda package: add_level(
        package, field(params, 'cls', ''), field(params, 'name', ''),
        field(params, 'label', ''), field(params, 'namespace', None) or None))


@server.feature('semforge/addSeverityClass')
def add_severity_class_feature(ls, params):
    """A new severity class, derived from sh:Severity or a class derived from it."""
    from ..cooked.severity import add_class

    return _package_write(ls, params, lambda package: add_class(
        package, field(params, 'name', ''), field(params, 'parent', '') or None,
        field(params, 'namespace', None) or None))


@server.feature('semforge/linkSeverityClass')
def link_severity_class_feature(ls, params):
    """Declare a class already used for severities a kind of sh:Severity."""
    from ..cooked.severity import link_class

    return _package_write(ls, params, lambda package: link_class(
        package, field(params, 'cls', '')))


@server.feature('semforge/removeCaseValue')
def remove_case_value_feature(ls, params):
    """Remove an attribute -- or one instance, observation or metadata key of
    it -- from an entity in a case or the model."""
    from ..cooked.examples import remove_value

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = remove_value(session.package_for(root), field(params, 'entity', ''),
                            list(field(params, 'path', []) or []),
                            field(params, 'file', '') or None,
                            field(params, 'dataset', None))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    session.forget(root)
    validation.publish(ls, path_to_uri(done['file']))
    return dict(done, ok=True)


@server.feature('semforge/deleteCasePlan')
def delete_case_plan_feature(ls, params):
    """What deleting a case (or a whole suite) removes, and the evidence it costs."""
    from ..expect.deletecase import delete_plan

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(delete_plan(session.package_for(root), field(params, 'case', ''),
                                field(params, 'suite', '')), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/deleteCase')
def delete_case_feature(ls, params):
    """Delete a case (its file and its entry), or a whole suite."""
    from ..expect.deletecase import delete_cases

    return _package_write(ls, params, lambda package: delete_cases(
        package, field(params, 'case', ''), field(params, 'suite', '')))


@server.feature('semforge/cloneCase')
def clone_case_feature(ls, params):
    """A copy of a case in its suite -- expecting the opposite, or the same --
    then run once."""
    from ..expect.addcase import clone_case

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = clone_case(session.package_for(root), field(params, 'case', ''),
                          field(params, 'expect', 'opposite'),
                          str(field(params, 'name', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    session.forget(root)
    return dict(made, ok=True)


@server.feature('semforge/newCase')
def new_case_feature(ls, params):
    """Start a case that makes a shape fire (the shape page's New case…)."""
    from ..expect.newcase import new_case

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = new_case(session.package_for(root), str(field(params, 'shape', '') or ''),
                        str(field(params, 'name', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(made, ok=True)


@server.feature('semforge/addShape')
def add_shape_feature(ls, params):
    """Write a new node shape with one target; constraints come from its page."""
    from ..cooked.shapes import add_shape

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_shape(session.package_for(root), field(params, 'name', ''),
                         field(params, 'targetKind', ''), field(params, 'target', ''),
                         field(params, 'namespace', None))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    session.forget(root)
    validation.publish(ls, path_to_uri(made['file']))
    return dict(made, ok=True)


def _target_write(ls, params, write):
    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = write(session.package_for(root))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    session.forget(root)
    validation.publish(ls, path_to_uri(done['file']))
    return dict(done, ok=True)


@server.feature('semforge/sparqlSave')
def sparql_save_feature(ls, params):
    """Write the edited query over the one the workbench opened."""
    from ..cooked.sparqlbench import save_query

    return _target_write(ls, params, lambda package: save_query(
        package, str(field(params, 'shape', '') or ''), field(params, 'index') or 0,
        str(field(params, 'query', '') or ''), str(field(params, 'expected', '') or '')))


@server.feature('semforge/sparqlRemove')
def sparql_remove_feature(ls, params):
    """Remove one SPARQL constraint or rule -- and, when asked, the asserts
    no remaining query could satisfy."""
    from ..cooked.sparqlbench import remove_holder

    shape = str(field(params, 'shape', '') or '')
    return _target_write(ls, params, lambda package: remove_holder(
        package, shape, holder_index(package, shape, params),
        str(field(params, 'expected', '') or ''), bool(field(params, 'dropAsserts'))))


@server.feature('semforge/addSparqlConstraint')
def add_sparql_constraint_feature(ls, params):
    """+ SPARQL constraint: a skeleton that fires on nothing, to be written in
    the workbench."""
    from ..cooked.sparqlbench import add_constraint

    return _target_write(ls, params, lambda package: add_constraint(
        package, str(field(params, 'shape', '') or ''), str(field(params, 'message', '') or '')))


@server.feature('semforge/addTarget')
def add_target_feature(ls, params):
    """One more thing a shape selects (the shape page's + Target)."""
    from ..cooked.shapes import add_target

    return _target_write(ls, params, lambda package: add_target(
        package, field(params, 'shape', ''), field(params, 'targetKind', ''),
        field(params, 'target', '')))


@server.feature('semforge/removeTarget')
def remove_target_feature(ls, params):
    """One target off a shape (the shape page's Remove)."""
    from ..cooked.shapes import remove_target

    return _target_write(ls, params, lambda package: remove_target(
        package, field(params, 'shape', ''), field(params, 'targetKind', ''),
        field(params, 'value', '')))


@server.feature('semforge/mergePlan')
def merge_plan_feature(ls, params):
    """The shapes one may be merged into, and -- given one -- what it would do."""
    from ..cooked.merge import candidates, plan

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = session.package_for(root)
        shape = field(params, 'shape', '')
        into = field(params, 'into', '')
        if not into:
            return {'ok': True, 'candidates': candidates(package, shape)}
        found = plan(package, shape, into)
        return {'ok': True, 'said': found['said'], 'asserts': found['asserts'],
                'name': found['name'], 'intoName': found['intoName']}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/mergeShape')
def merge_shape_feature(ls, params):
    """Fold one shape into another with the same targets."""
    from ..cooked.merge import merge_shape

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = merge_shape(session.package_for(root), field(params, 'shape', ''),
                           field(params, 'into', ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    session.forget(root)
    for path in session.package_for(root).files('shapes'):
        validation.publish(ls, path_to_uri(path))
    return dict(done, ok=True)


@server.feature('semforge/renameShapePlan')
def rename_shape_plan_feature(ls, params):
    """What renaming a shape would change, or why it cannot be renamed so."""
    from ..cooked.rename import rename_plan

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(rename_plan(session.package_for(root), field(params, 'shape', ''),
                                field(params, 'name', '')), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


def _package_write(ls, params, write):
    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = write(session.package_for(root))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    # SemForge's own rename carried everything along, as asked: the shapes
    # it changed are the new baseline, not a rename to offer again.
    session.forget(root, renames=True)
    for path in session.package_for(root).files('shapes'):
        validation.publish(ls, path_to_uri(path))
    return dict(done, ok=True)


@server.feature('semforge/followRename')
def follow_rename_feature(ls, params):
    """Carry along what a shape renamed in the .ttl left behind: its asserts,
    residues pinned under the old name, and (asked) its suite folder."""
    from ..cooked.rename import follow_rename

    return _package_write(ls, params, lambda package: follow_rename(
        package, field(params, 'shape', ''), field(params, 'newIri', ''),
        suite=bool(field(params, 'suite', False))))


@server.feature('semforge/renameShape')
def rename_shape_feature(ls, params):
    """Rename a shape everywhere it is named: .ttl, asserts, residues, suite."""
    from ..cooked.rename import rename_shape

    return _package_write(ls, params, lambda package: rename_shape(
        package, field(params, 'shape', ''), field(params, 'name', ''),
        suite=bool(field(params, 'suite', False))))


@server.feature('semforge/renameCase')
def rename_case_feature(ls, params):
    """Rename a test case's file, and the entries that name it."""
    from ..cooked.rename import rename_case

    return _package_write(ls, params, lambda package: rename_case(
        package, field(params, 'case', ''), field(params, 'name', '')))


@server.feature('semforge/deleteShapePlan')
def delete_shape_plan_feature(ls, params):
    """What deleting a shape would remove, or why it cannot be deleted."""
    from ..cooked.shapedelete import delete_plan

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(delete_plan(session.package_for(root), field(params, 'shape', '')), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/deleteShape')
def delete_shape_feature(ls, params):
    """Delete a shape; with `asserts`, the asserts naming it; with `cases`,
    the cases that assert nothing else."""
    from ..cooked.shapedelete import delete_shape

    return _package_write(ls, params, lambda package: delete_shape(
        package, field(params, 'shape', ''), asserts=bool(field(params, 'asserts', False)),
        cases=bool(field(params, 'cases', False))))


@server.feature('semforge/renameSuite')
def rename_suite_feature(ls, params):
    """Rename a suite folder, and the includes that reach into it."""
    from ..cooked.rename import rename_suite

    return _package_write(ls, params, lambda package: rename_suite(
        package, field(params, 'suite', ''), field(params, 'name', '')))


@server.feature('semforge/editValueForms')
def edit_value_forms_feature(ls, params):
    """One change to a value's forms, or to what one form must be."""
    from ..cooked.valueforms import edit_value

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        action = field(params, 'action')
        made = edit_value(session.package_for(root), field(params, 'shape'),
                          list(field(params, 'path') or []),
                          dict({k: field(action, k) for k in (
                              'op', 'node', 'parameter', 'value', 'connective', 'form', 'kind')},
                              conditions=[{'parameter': field(c, 'parameter'),
                                           'value': field(c, 'value')}
                                          for c in (field(action, 'conditions') or [])]))
        session.forget(root)
        validation.publish(ls, path_to_uri(made['file']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/editAttribute')
def edit_attribute_feature(ls, params):
    """Change an attribute's presence or what its value must be (type page)."""
    from ..cooked.constrain import edit_attribute

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        counts, value = field(params, 'counts'), field(params, 'value')
        made = edit_attribute(session.package_for(root), field(params, 'shape'),
                              list(field(params, 'path') or []),
                              presence=field(params, 'presence') or None,
                              value={k: field(value, k) for k in ('kind', 'datatype', 'valueClass')
                                     if field(value, k) is not None} if value else None,
                              # A nested object arrives as pygls's Object too.
                              counts={'min': field(counts, 'min'), 'max': field(counts, 'max')}
                              if counts else None)
        session.forget(root)
        validation.publish(ls, path_to_uri(made['file']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/removeProperty')
def remove_property_feature(ls, params):
    """Take one attribute's property shape out of one shape."""
    from ..cooked.constrain import remove_property_group

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = remove_property_group(session.package_for(root), field(params, 'shape'),
                                     list(field(params, 'path') or []))
        session.forget(root)
        validation.publish(ls, path_to_uri(made['file']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addAssert')
def add_assert_feature(ls, params):
    """Assert a firing a case did not claim (the case page's "Assert it")."""
    from ..expect.store import add_assert

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_assert(session.package_for(root), field(params, 'case'),
                          field(params, 'constraint'),
                          field(params, 'resource', '') or '')
        session.forget(root)
        validation.publish(ls, path_to_uri(made['file']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/override')
def override(ls, params):
    """Declare an inherited constraint explicitly on the subtype's own shape.

    Reports the EFFECT before doing anything, because SHACL has no override:
    the new constraint is conjoined with the inherited one, so it can tighten
    and cannot relax. `check` alone returns the verdict without writing.
    """
    from ..cooked.tree import override_constraint, override_effect

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}

    parameter = field(params, 'parameter')
    value = str(field(params, 'value'))
    effect = override_effect(parameter, field(params, 'inheritedValue'), value)
    if field(params, 'check'):
        return {'ok': True, 'effect': effect}
    if effect in ('weaker', 'same') and not field(params, 'force'):
        return {'ok': False, 'effect': effect,
                'error': ('SHACL conjoins constraints, so this would be '
                          'evaluated alongside the inherited one rather than '
                          'instead of it -- it cannot relax it.')}
    try:
        package = session.package_for(root)
        path, how = override_constraint(
            package, field(params, 'targetShape'),
            list(field(params, 'path') or []), parameter, value)
        session.forget(root)
        validation.publish(ls, path_to_uri(path))
        return {'ok': True, 'effect': effect, 'file': path, 'how': how}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'effect': effect, 'error': str(exc)}
