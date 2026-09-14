"""One name per namespace, across every artifact in a package.

The kms did not have this, and the failure is worse than untidiness: the SAME
prefix denoted DIFFERENT namespaces in two files.

    :          base_shacl/      in shacl.ttl      base_entities/   in knowledge.ttl
    default1:  filter_shacl/    in shacl.ttl      base_knowledge/  in knowledge.ttl

So `:CartridgeShape` means one thing in one file and another in the other, and a
term copied between them changes meaning silently. The `default1..5` names come
from `make ontology2kms` merging modules with rdfpipe, which invents a prefix
whenever the source did not supply one.

The context is the source of truth, because it is the one artifact all three
already share: `context.jsonld` declares terms with `"@prefix": true`, and
`model-instance.jsonld` is written against them. This reads that map, reports
where the Turtle files disagree with it, and rewrites them to match.

What it will not do is invent a name for a namespace the context does not
declare. Those are reported so somebody adds them to the context, which is the
only place a name can be agreed.
"""

import json
import os
import re
from dataclasses import dataclass, field

from .registry import CACHE  # noqa: F401  (keeps the module's role obvious)

PREFIX_LINE = re.compile(
    r'^([ \t]*)@prefix[ \t]+([A-Za-z_][\w.-]*)?:[ \t]*<([^>]*)>[ \t]*\.[ \t]*$',
    re.MULTILINE)


@dataclass
class PrefixFinding:
    code: str
    severity: str
    message: str
    namespace: str = ''
    files: list = field(default_factory=list)


# The names nobody should have to declare.
#
# rdf, rdfs, owl, xsd and sh are the vocabularies every Turtle file in this
# world binds, and ngsild is the encoding the SDK ships a vocabulary for. They
# are not a package's business: a package that had to list them would carry
# five lines of boilerplate that can only drift, and one that forgot would be
# told its shapes file had invented "sh:".
#
# Lowest precedence. A package that has a reason to call one of these something
# else says so in semforge.yaml and that wins.
STANDARD = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'owl': 'http://www.w3.org/2002/07/owl#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
    'sh': 'http://www.w3.org/ns/shacl#',
    'ngsild': 'https://uri.etsi.org/ngsi-ld/',
}


def context_prefixes(package_path, filename='context.jsonld'):
    """{prefix: namespace} declared by the package's JSON-LD context."""
    path = os.path.join(package_path, filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    entries = document.get('@context', document)
    if not isinstance(entries, list):
        entries = [entries]

    found = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for name, value in entry.items():
            if isinstance(value, dict) and value.get('@prefix') and '@id' in value:
                found[name] = value['@id']
            elif isinstance(value, str) and value.endswith(('/', '#')):
                found[name] = value
    return found


def declared_prefixes(package_path):
    """`namespaces:` from semforge.yaml, which overrides the context."""
    config = os.path.join(package_path, 'semforge.yaml')
    if not os.path.exists(config):
        return {}
    from ruamel.yaml import YAML

    with open(config) as handle:
        data = YAML().load(handle) or {}
    return dict(data.get('namespaces') or {})


def canonical_map(package_path):
    """The agreed name for each namespace.

    Three layers, narrowest first: what the package declares in semforge.yaml,
    then what its context says, then the standard names every package uses and
    none should have to write down.
    """
    found = dict(STANDARD)
    found.update(context_prefixes(package_path))
    found.update(declared_prefixes(package_path))
    return found


def names_by_namespace(package_path):
    """{namespace: agreed name}, with the package's own declaration winning.

    Two names for one namespace is legal and happens -- the context calls
    base_knowledge `base` while this package calls it `iffBaseKnowledge`. The
    package's declaration is the deliberate one, so it is applied first and the
    context only fills namespaces the package says nothing about.
    """
    declared = declared_prefixes(package_path)
    by_namespace = {}
    for name, namespace in declared.items():
        by_namespace.setdefault(namespace, name)
    for name, namespace in context_prefixes(package_path).items():
        by_namespace.setdefault(namespace, name)
    # Last, so anything the package or its context says about one of these
    # wins -- and so a package never has to say anything about them at all.
    for name, namespace in STANDARD.items():
        by_namespace.setdefault(namespace, name)
    return by_namespace


def file_prefixes(path):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    return {(match.group(2) or ''): match.group(3)
            for match in PREFIX_LINE.finditer(text)}, text


PREFIXED = re.compile(r'^([A-Za-z_][\w.-]*):[\w.-]+$')


def model_prefixes(path):
    """{prefix: count} used in a JSON-LD model's keys and @id values.

    The model instance is the third artifact, and leaving it out of the check
    would let the two Turtle files agree with each other while the data spoke a
    different language.
    """
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)

    found = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                for candidate in (key, value if key == '@id' else None):
                    if isinstance(candidate, str) and not candidate.startswith(
                            ('http', 'urn', '@')):
                        match = PREFIXED.match(candidate)
                        if match:
                            name = match.group(1)
                            found[name] = found.get(name, 0) + 1
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return found


def check(package):
    """Findings for every disagreement between the artifacts and the context."""
    by_namespace = names_by_namespace(package.path)

    artifacts = [(role, path) for role in ('shapes', 'knowledge')
                 for path in package.files(role)]
    seen = {}
    findings = []

    for role, path in artifacts:
        prefixes, _ = file_prefixes(path)
        for name, namespace in prefixes.items():
            seen.setdefault(name, {}).setdefault(namespace, []).append(role)

    # The dangerous one: one prefix, two meanings.
    for name, namespaces in sorted(seen.items()):
        if len(namespaces) > 1:
            findings.append(PrefixFinding(
                code='SF-PFX-001', severity='error',
                message=(f'"{name or "(default)"}:" denotes '
                         + ' and '.join(f'{ns} in {", ".join(roles)}'
                                        for ns, roles in sorted(namespaces.items()))
                         + '. A term copied between them changes meaning.'),
                files=[role for roles in namespaces.values() for role in roles]))

    for role, path in sorted(artifacts):
        prefixes, _ = file_prefixes(path)
        for name, namespace in sorted(prefixes.items()):
            agreed = by_namespace.get(namespace)
            if agreed is None:
                # Names are a PACKAGE-wide table, not a per-file convenience.
                # A file that binds a prefix the package has not defined has
                # invented a name: nothing else in the package knows it, the
                # model cannot expand it, and a term copied out of that file
                # means nothing where it lands. So it is an error, not taste.
                findings.append(PrefixFinding(
                    code='SF-PFX-003', severity='error', namespace=namespace,
                    message=(f'{role}: <{namespace}> is used as "{name or "(default)"}:" '
                             f'but the package defines no name for it. Prefixes '
                             f'are defined once, for the whole package: add it '
                             f'to context.jsonld or to `namespaces:` in '
                             f'semforge.yaml.'),
                    files=[role]))
            elif agreed != name:
                findings.append(PrefixFinding(
                    code='SF-PFX-002', severity='warning', namespace=namespace,
                    message=(f'{role}: <{namespace}> is "{name or "(default)"}:" here '
                             f'but "{agreed}:" in the context.'),
                    files=[role]))

    findings.extend(_check_model(package, by_namespace))
    return findings


PREFIX_NAME = re.compile(r'^[A-Za-z_][\w.-]*$')


def add_namespace(package_path, prefix, namespace):
    """Define a namespace name for the whole package.

    The table is global on purpose: one name per namespace, agreed once, and
    every artifact bound to it. A file that invents its own is the failure
    `check` reports -- rdflib binds a single prefix per namespace, so a second
    name evicts the first and a term copied between artifacts changes meaning.

    Writes `namespaces:` in semforge.yaml, which is the half a package owns;
    context.jsonld is a snapshot of a published url and diverging from what
    that url serves is the reproducibility problem in another form.
    """
    from . import config
    from ..errors import PackageError

    name = (prefix or '').strip().rstrip(':')
    target = (namespace or '').strip()
    if not PREFIX_NAME.match(name):
        raise PackageError(
            f'{prefix!r} is not usable as a prefix: a letter or underscore, '
            f'then letters, digits, dots, underscores or hyphens')
    if not target.startswith(('http://', 'https://', 'urn:')):
        raise PackageError(
            f'{target!r} is not a namespace IRI: it should be an http(s) url '
            f'or a urn')
    if not target.endswith(('/', '#', ':')):
        raise PackageError(
            f'{target!r} does not end in "/", "#" or ":", so a term appended '
            f'to it would run into the last segment')

    declared = canonical_map(package_path)
    if declared.get(name) == target:
        raise PackageError(f'{name}: is already {target}')
    if name in declared:
        whose = ' (a standard name the SDK knows)' if STANDARD.get(name) == \
            declared[name] else ''
        raise PackageError(
            f'{name}: already means <{declared[name]}>{whose}. One name per '
            f'namespace, and one namespace per name.')
    existing = names_by_namespace(package_path).get(target)
    if existing:
        raise PackageError(
            f'<{target}> is already named "{existing}:". rdflib binds one '
            f'prefix per namespace, so a second name would evict the first.')

    where, line = config.set_value(package_path, f'namespaces.{name}', target)
    return {'prefix': name, 'namespace': target, 'file': where, 'line': line}


def namespace_usage(package, namespace):
    """Where a namespace is actually used: files that bind it, terms in it.

    Both halves matter. A file's `@prefix` says this artifact speaks the name;
    a term in the namespace says something would stop resolving. Either one
    makes the declaration load-bearing.
    """
    from rdflib import URIRef

    files, terms = [], 0
    for role in ('shapes', 'knowledge'):
        for path in package.files(role):
            bound, _ = file_prefixes(path)
            if namespace in bound.values():
                files.append(os.path.relpath(path, package.path))
    for graph in (package.knowledge, package.shapes, package.model):
        for triple in graph:
            for node in triple:
                if isinstance(node, URIRef) and str(node).startswith(namespace):
                    terms += 1
    return {'files': sorted(set(files)), 'terms': terms}


def plan_removal(package_path, prefix, package=None):
    """What removing this name would do, before anything is written.

    Three answers, and they are not the same thing:

      * not removable -- the package does not declare it, so it is not the
        package's to remove;
      * removable and load-bearing -- the namespace loses its only name and
        every term in it becomes undefined;
      * removable and safe -- the name survives, because the context declares
        it too or it is one the SDK knows.

    The last one is still worth asking about when the namespace is IN USE. A
    line that changes nothing is still a line somebody wrote on purpose, and
    "it is used in three files" is what the person clicking is thinking about.
    """
    name = (prefix or '').strip().rstrip(':')
    declared = declared_prefixes(package_path)
    if name not in declared:
        return {'prefix': name, 'removable': False, 'in_use': False,
                'reason': (f'{name}: is not declared in semforge.yaml. The '
                           f'package\'s table is the only one it owns -- a '
                           f'name from the context or from the standard set '
                           f'is not this package\'s to remove.')}
    namespace = declared[name]

    survives_as, survives_via = '', ''
    from_context = context_prefixes(package_path)
    for other, target in from_context.items():
        if target == namespace:
            survives_as, survives_via = other, 'context.jsonld'
            break
    if not survives_as:
        for other, target in STANDARD.items():
            if target == namespace:
                survives_as, survives_via = other, 'the standard set'
                break

    if package is None:
        from . import load
        package = load(package_path)
    usage = namespace_usage(package, namespace)
    in_use = bool(usage['files'] or usage['terms'])
    where = ', '.join(usage['files']) or 'the model'

    if not survives_as:
        if in_use:
            return {
                'prefix': name, 'namespace': namespace, 'removable': False,
                'in_use': True, 'usage': usage,
                'reason': (f'{name}: cannot be removed -- it is in use. '
                           f'<{namespace}> is bound in {where} and names '
                           f'{usage["terms"]} term(s), and nothing else in the '
                           f'package gives it a name. Removing it would leave '
                           f'every one of them undefined.')}
        return {'prefix': name, 'namespace': namespace, 'removable': True,
                'in_use': False, 'usage': usage, 'survives_as': '',
                'survives_via': '', 'reason': 'nothing uses it'}

    return {
        'prefix': name, 'namespace': namespace, 'removable': True,
        'in_use': in_use, 'usage': usage, 'survives_as': survives_as,
        'survives_via': survives_via,
        'reason': (f'{name}: is in use -- <{namespace}> is bound in {where} '
                   f'and names {usage["terms"]} term(s). Removing this line is '
                   f'safe anyway: {survives_via} names it "{survives_as}:", so '
                   f'the table does not change.') if in_use else
                  (f'{survives_via} names it "{survives_as}:" as well, so this '
                   f'line changes nothing.')}


def remove_namespace(package_path, prefix, package=None, force=False):
    """Drop a name from the package's table, unless something needs it.

    `force` only covers the case the plan calls safe-but-in-use: a name that
    would actually lose its definition is never removed, whatever is passed.
    """
    from . import config
    from ..errors import PackageError

    plan = plan_removal(package_path, prefix, package=package)
    if not plan['removable']:
        raise PackageError(plan['reason'])
    if plan['in_use'] and not force:
        raise PackageError(plan['reason'])

    path, line = config.remove_value(package_path,
                                     f'namespaces.{plan["prefix"]}')
    return dict(plan, file=path, line=line)


def _check_model(package, by_namespace):
    """The model instance has to speak the same language as the shapes.

    Its prefixes resolve through the CONTEXT rather than through an @prefix
    header, so a name here is only usable once the context declares it. That
    makes the ordering matter: switching the data to a new name before the
    published context carries it leaves the value unexpanded -- a plain string
    where an IRI was meant, which sh:class then correctly refuses.
    """
    context = context_prefixes(package.path)
    findings = []
    used = {}
    for document in package.files('model'):
        for name, count in model_prefixes(document).items():
            used[name] = used.get(name, 0) + count
    for name, count in sorted(used.items()):
        namespace = context.get(name)
        if namespace is None:
            findings.append(PrefixFinding(
                code='SF-PFX-005', severity='error', files=['model'],
                message=(f'model: "{name}:" is used {count} time(s) but the '
                         f'context does not declare it, so it will not expand '
                         f'to an IRI.')))
            continue
        agreed = by_namespace.get(namespace)
        if agreed and agreed != name:
            findings.append(PrefixFinding(
                code='SF-PFX-004', severity='warning', namespace=namespace,
                files=['model'],
                message=(f'model: <{namespace}> is written as "{name}:" '
                         f'({count} use(s)) but the package calls it '
                         f'"{agreed}:". Safe to switch once every context the '
                         f'data is loaded against declares "{agreed}:".')))
    return findings


def _rewrite(text, renames):
    """Rename prefixes in a Turtle document, headers and usages alike.

    Strings, comments and IRIs are stepped over. That matters most for the
    SPARQL bodies in shacl.ttl: they carry their own PREFIX declarations inside
    a triple-quoted literal and are a separate namespace scope, so rewriting
    into them would break queries that are currently correct.
    """
    from ..rdfio.turtle_index import _skip_string

    out = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == '#':
            end = text.find('\n', i)
            end = len(text) if end == -1 else end
            out.append(text[i:end])
            i = end
            continue
        if char in '"\'':
            end = _skip_string(text, i)
            out.append(text[i:end])
            i = end
            continue
        if char == '<':
            closing = text.find('>', i)
            newline = text.find('\n', i)
            if closing != -1 and (newline == -1 or closing < newline):
                out.append(text[i:closing + 1])
                i = closing + 1
                continue
        match = re.compile(r'([A-Za-z_][\w.-]*)?:').match(text, i)
        if match and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in '_-.:')):
            name = match.group(1) or ''
            if name in renames:
                out.append(renames[name] + ':')
                i = match.end()
                continue
        out.append(char)
        i += 1
    return ''.join(out)


def align(package, dry_run=False):
    """Rewrite the Turtle artifacts to the agreed names. Returns {role: renames}."""
    by_namespace = names_by_namespace(package.path)

    applied = {}
    for role, path in [(role, path) for role in ('shapes', 'knowledge')
                       for path in package.files(role)]:
        prefixes, text = file_prefixes(path)
        renames = {name: by_namespace[namespace]
                   for name, namespace in prefixes.items()
                   if namespace in by_namespace and by_namespace[namespace] != name}
        if not renames:
            continue
        applied[role] = renames
        if dry_run:
            continue

        updated = _rewrite(text, renames)
        from rdflib import Graph
        from rdflib.compare import isomorphic

        before, after = Graph(), Graph()
        before.parse(data=text, format='turtle')
        after.parse(data=updated, format='turtle')
        if not isomorphic(before, after):
            raise ValueError(
                f'{role}: renaming prefixes changed the graph; refusing to write')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(updated)
    return applied
