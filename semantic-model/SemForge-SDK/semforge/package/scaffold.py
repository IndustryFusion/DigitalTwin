"""Create a package that already works.

An empty directory with three empty files is not a starting point: the first
thing an author needs is a package that LOADS, validates clean, and has an
example on each side of one constraint -- because that is the shape every later
addition copies, and the NGSI-LD encoding is not something to re-derive from
the spec on day one.

So the skeleton is small but complete and honest about the conventions that are
easy to get wrong:

  * an attribute is a BLANK NODE carrying `ngsild:hasValue` or `hasObject`, so
    the shapes are two-layer and the value constraints sit on the inner layer;
  * a Property whose value is an IRI (`{"@id": …}`) is how a vocabulary term is
    referenced -- `{"object": …}` would be a Relationship and means an entity;
  * every case says what it is FOR, and the suite has a good and a bad one, so
    the constraint is proven to fire as well as to be satisfiable.

`semforge init` writes it; `semforge validate` and `semforge test` pass on it
immediately, which the tests here assert rather than assume.
"""

import json
import os
import re

from ..errors import PackageError

LAYOUTS = ('grouped', 'flat')


def _slug(name):
    cleaned = re.sub(r'[^A-Za-z0-9]+', ' ', name).strip()
    if not cleaned:
        raise PackageError('a package needs a name with letters or digits in it')
    parts = cleaned.split()
    return parts[0].lower() + ''.join(p.capitalize() for p in parts[1:])


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return path


def _context(prefixes, published):
    """The local context: the NGSI-LD core context plus this package's names."""
    terms = {name: {'@id': namespace, '@prefix': True}
             for name, namespace in prefixes.items()}
    terms.update({
        'xsd': {'@id': 'http://www.w3.org/2001/XMLSchema#', '@prefix': True},
        'owl': {'@id': 'http://www.w3.org/2002/07/owl#', '@prefix': True},
        'rdfs': {'@id': 'http://www.w3.org/2000/01/rdf-schema#', '@prefix': True},
    })
    document = {'@context': [
        'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld',
        terms,
    ]}
    return json.dumps(document, indent=4) + '\n'


def _config(name, prefixes, published, layout):
    lines = [
        f'# {name}',
        '#',
        '# Written by `semforge init`. Everything here is editable; the comments',
        '# say what each part decides.',
        '',
        '# The package\'s name. Two directories called `test` are not the same',
        '# project, so this is what the editor shows rather than the folder.',
        f'name: {name}',
        '',
        '# The context this package resolves against.',
        '#',
        '# Locally the LOCAL file answers, so a term is usable the moment it is',
        '# agreed rather than after it is published, and no build depends on the',
        '# network. `semforge export` points the model at the PUBLISHED url and',
        '# checks that it declares everything the model uses -- shipping values',
        '# that will not expand is the failure that check exists to prevent.',
        'context:',
        '  local: context.jsonld',
        f'  published: {published}',
        '',
        '# The package\'s agreed name for each namespace. One name per namespace:',
        '# rdflib binds a single prefix per namespace, so a second name evicts',
        '# the first and a term copied between artifacts changes meaning.',
        'namespaces:',
    ]
    for prefix, namespace in prefixes.items():
        lines.append(f'  {prefix}: {namespace}')
    lines += [
        '  ngsild: https://uri.etsi.org/ngsi-ld/',
        '',
        '# The class every entity type descends from. Declared rather than',
        '# guessed, so a value picker can tell an entity type (the target of a',
        '# Relationship) from a vocabulary class (the value of a Property).',
        f'entityRoot: {list(prefixes)[0]}:Entity',
        '',
        f'# Layout: {layout}.',
    ]
    return '\n'.join(lines) + '\n'


def _knowledge(entities, knowledge):
    return f'''@prefix {entities[0]}: <{entities[1]}> .
@prefix {knowledge[0]}: <{knowledge[1]}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .

# The entity hierarchy. Everything a shape targets descends from Entity, which
# is what tells an entity type from a vocabulary class.
{entities[0]}:Entity a owl:Class .

{entities[0]}:Machine a owl:Class ;
    rdfs:subClassOf {entities[0]}:Entity ;
    rdfs:label "Machine" .

# The attributes. An attribute must be declared BEFORE it is used: the name is
# what a shape's sh:path matches, so one spelled wrong is not a broken document
# but an invisible one -- no constraint selects it and the entity reads as
# validated. Declaring it is also what makes go-to-definition work, and what a
# reader consults to find out what the attribute is.
#
# `rdfs:domain` says which entity type carries it, and is inherited down the
# hierarchy. `rdfs:range` says which HALF of the NGSI-LD encoding it is: a
# Property carries ngsild:hasValue, a Relationship ngsild:hasObject. Which
# VALUES are allowed is the shapes' business (sh:class), not this file's.
{entities[0]}:hasState a owl:ObjectProperty ;
    rdfs:domain {entities[0]}:Machine ;
    rdfs:range ngsild:Property ;
    rdfs:label "the state the machine reports" .

{entities[0]}:hasTemperature a owl:DatatypeProperty ;
    rdfs:domain {entities[0]}:Machine ;
    rdfs:range ngsild:Property ;
    rdfs:label "degrees Celsius" .

# A vocabulary: a class whose INDIVIDUALS are the allowed values. A Property
# whose value is one of these carries it as {{"@id": ...}} -- an IRI, not a
# string, and not a Relationship.
{knowledge[0]}:MachineState a owl:Class ;
    rdfs:label "MachineState" .

{knowledge[0]}:state_ON a owl:NamedIndividual,
        {knowledge[0]}:MachineState ;
    rdfs:label "ON" .

{knowledge[0]}:state_OFF a owl:NamedIndividual,
        {knowledge[0]}:MachineState ;
    rdfs:label "OFF" .
'''


def _shapes(entities, knowledge, shapes):
    return f'''@prefix {shapes[0]}: <{shapes[1]}> .
@prefix {entities[0]}: <{entities[1]}> .
@prefix {knowledge[0]}: <{knowledge[1]}> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# In NGSI-LD-in-RDF an attribute is a BLANK NODE hanging off the entity, and
# the value hangs off that: entity -hasTemperature-> [] -ngsild:hasValue-> 21.5
#
# So every constraint here is two layers. The outer sh:property says the
# attribute is there (and is a blank node); the inner one constrains the value.
# A datatype or a range written on the outer layer constrains the blank node
# itself and can never be satisfied.
{shapes[0]}:MachineShape a sh:NodeShape ;
    sh:targetClass {entities[0]}:Machine ;
    sh:property [ sh:path {entities[0]}:hasState ;
            sh:minCount 1 ;
            sh:maxCount 1 ;
            sh:nodeKind sh:BlankNode ;
            sh:property [ sh:path ngsild:hasValue ;
                    sh:minCount 1 ;
                    sh:maxCount 1 ;
                    # The value IS one of the vocabulary's individuals, so it
                    # arrives as an IRI rather than as a string.
                    sh:nodeKind sh:IRI ;
                    sh:class {knowledge[0]}:MachineState ] ] ;
    sh:property [ sh:path {entities[0]}:hasTemperature ;
            sh:minCount 1 ;
            sh:maxCount 1 ;
            sh:nodeKind sh:BlankNode ;
            sh:property [ sh:path ngsild:hasValue ;
                    sh:minCount 1 ;
                    sh:maxCount 1 ;
                    sh:datatype xsd:double ;
                    sh:minInclusive 0.0 ;
                    sh:maxInclusive 120.0 ] ] .
'''


def _entity(identifier, entities, knowledge, published, state='state_ON',
            temperature=21.5):
    return {
        'id': identifier,
        'type': f'{entities}:Machine',
        f'{entities}:hasState': {
            'type': 'Property',
            'value': {'@id': f'{knowledge}:{state}'},
            'observedAt': '2026-01-01T00:00:00.000Z',
        },
        f'{entities}:hasTemperature': {
            'type': 'Property',
            'value': temperature,
            'observedAt': '2026-01-01T00:00:00.000Z',
        },
        '@context': published,
    }


def create_package(path, name=None, namespace=None, published=None,
                   layout='grouped'):
    """Write a working package into `path`. Returns the files written.

    Refuses a directory that already holds an artifact rather than merging into
    it: a half-overwritten package is worse than no package, and the author can
    see for themselves what is there.
    """
    if layout not in LAYOUTS:
        raise PackageError(f'layout must be one of {", ".join(LAYOUTS)}')

    name = name or os.path.basename(os.path.abspath(path)) or 'model'
    slug = _slug(name)
    namespace = (namespace or f'https://example.org/{slug}/').rstrip('/') + '/'
    published = published or f'{namespace}context.jsonld'

    existing = [n for n in ('knowledge.ttl', 'shacl.ttl', 'model-instance.jsonld',
                            'main.jsonld', 'knowledge', 'shacl', 'model',
                            'model-instance', 'main',
                            'semforge.yaml', 'context.jsonld')
                if os.path.exists(os.path.join(path, n))]
    if existing:
        raise PackageError(
            f'{path} already holds {", ".join(sorted(existing))}. '
            f'`semforge init` writes a new package and will not merge into an '
            f'existing one.')

    entities = (f'{slug}Entities', f'{namespace}entities/')
    knowledge = (f'{slug}Knowledge', f'{namespace}knowledge/')
    shapes = (f'{slug}Shacl', f'{namespace}shapes/')
    prefixes = {entities[0]: entities[1], knowledge[0]: knowledge[1],
                shapes[0]: shapes[1]}

    # `main` is what the tree calls it, so that is what a new package gets.
    # `model-instance.jsonld` still loads -- the kms uses it.
    if layout == 'grouped':
        instance = os.path.join(path, 'model', 'main.jsonld')
        examples = os.path.join(path, 'model', 'examples')
    else:
        instance = os.path.join(path, 'main.jsonld')
        examples = os.path.join(path, 'examples')

    written = [
        _write(os.path.join(path, 'semforge.yaml'),
               _config(name, prefixes, published, layout)),
        _write(os.path.join(path, 'context.jsonld'),
               _context(prefixes, published)),
        _write(os.path.join(path, 'knowledge.ttl'),
               _knowledge(entities, knowledge)),
        _write(os.path.join(path, 'shacl.ttl'),
               _shapes(entities, knowledge, shapes)),
    ]

    def dump(where, document):
        return _write(where, json.dumps(document, indent=2) + '\n')

    written.append(dump(instance, [
        _entity(f'urn:{slug}:machine:1', entities[0], knowledge[0], published)]))

    suite = os.path.join(examples, 'test_MachineShape')
    written.append(dump(
        os.path.join(suite, 'good', 'running.jsonld'),
        [_entity(f'urn:{slug}:machine:1', entities[0], knowledge[0], published,
                 temperature=21.5)]))
    written.append(_write(
        os.path.join(suite, 'good', 'expectations.yaml'),
        'examples:\n'
        '  - path: running.jsonld\n'
        '    description: A machine in a state the vocabulary allows, within\n'
        '      the temperature range.\n'
        '    expect: valid\n'
        '    conformance: full\n'))

    written.append(dump(
        os.path.join(suite, 'bad', 'too-hot.jsonld'),
        [_entity(f'urn:{slug}:machine:1', entities[0], knowledge[0], published,
                 temperature=180.0)]))
    written.append(_write(
        os.path.join(suite, 'bad', 'expectations.yaml'),
        'examples:\n'
        '  - path: too-hot.jsonld\n'
        '    description: >-\n'
        '      180 against a maximum of 120. A constraint with no example that\n'
        '      makes it FIRE is indistinguishable from one that is satisfied,\n'
        '      so every constraint deserves a case like this one.\n'
        '    expect: invalid\n'
        '    asserts:\n'
        f'      - constraint: {shapes[0]}:MachineShape/hasTemperature/'
        'MaxInclusiveConstraintComponent\n'
        f'        resource: urn:{slug}:machine:1\n'))

    grouped_tree = (
        'model/\n'
        '├── main.jsonld   the scratchpad: try a violation here\n'
        '└── examples/     the suite: each case says what it is for')
    flat_tree = (
        'main.jsonld   the scratchpad: try a violation here\n'
        'examples/     the suite: each case says what it is for')
    layout_tree = grouped_tree if layout == 'grouped' else flat_tree
    written.append(_write(os.path.join(path, 'README.md'), f'''# {name}

A SemForge package: knowledge, constraints and the data they judge.

```text
knowledge.ttl        the ontology -- classes, attributes, vocabularies
shacl.ttl            the constraints, in the NGSI-LD two-layer encoding
{layout_tree}
```

```bash
semforge validate .        # what the shapes say about the scratchpad
semforge test .            # the declared cases, with their expectations
semforge test . --coverage # which constraints no example makes fire
```

Any of `knowledge.ttl`, `shacl.ttl` and the model instance may be a directory of
documents instead of a single file, once one file stops being enough.
'''))
    return written
