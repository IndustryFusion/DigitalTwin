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

"""Search: each view shows only what fits, and a file leads back to its page.

A text search of the workspace finds lines and opens files; the views and
pages, where a model is worked on, stay where they were. So a search is
answered in the views instead: `prune` keeps the rows that fit and the rows
they are under. A row fits by what it shows, or by what it stands for -- the
statement that declares it, a case's asserts -- so "Executing" finds the shape
whose sh:in lists it although its row only says its name; then the row says
what was found.

`page_at` is the way back: the page of what a line of a file is about.
"""

import os
import re

from ..validate.normalise import local

# Rows whose detail is a count ("3 attribute(s)"): not something they say.
COUNTED = {'group', 'type', 'suite', 'rules', 'violations', 'shape'}
TEXT = ('label', 'term', 'value', 'entity', 'datasetId')
# A count within a description ("12 entities · 2 violation(s)"): left out too.
COUNT = re.compile(r'\b\d+\s+(?:[a-z-]+\(s\)|(?:entities|instances|attributes|shapes|cases|'
                   r'files|units|values|members|terms|types|rules|violations)\b)', re.IGNORECASE)
# What an edit reads of the rows under the one it is on: see `all` in `prune`.
SIBLING = ('kind', 'label', 'shape', 'inheritedFrom', 'attributePath', 'datasetId', 'datasets', 'file')


def _said(node):
    parts = [str(node.get(key) or '') for key in TEXT]
    if node.get('kind') not in COUNTED:
        parts.append(COUNT.sub('', str(node.get('detail') or '')))
    # An entity is of its type; its attributes merely are of an entity of it.
    for key in ('iri', 'targetClass') + (('entityType',) if node.get('kind') == 'entity' else ()):
        if node.get(key):
            parts.append(local(str(node[key])))
    return ' '.join(parts).lower()


def _snippet(text, word):
    """The word of `text` the search was found in."""
    found = re.search(r'[^\s"\'\[\]();,]*' + re.escape(word) + r'[^\s"\'\[\]();,]*', text,
                      re.IGNORECASE)
    return found.group(0)[:60] if found else word


def prune(roots, text, extra=None):
    """(the rows that fit `text` with the rows they are under, how many fit).

    Every word of `text` must be in a row, in any order and case. A row with
    fitting rows under it keeps only those and is marked `expand`; a fitting
    row with none keeps its own rows, closed. A row that lost some of its own
    still names them in `all`: which instances an entity has, or which shape is
    a type's own, does not depend on what is shown.
    """
    words = str(text or '').lower().split()
    if not words:
        return roots, 0
    count = 0

    def walk(node, address):
        nonlocal count
        said = _said(node)
        fits = all(word in said for word in words)
        why = ''
        if not fits and extra is not None:
            hidden = extra(node)
            if hidden:
                low = f'{said} {hidden.lower()}'
                if all(word in low for word in words):
                    fits = True
                    why = _snippet(hidden, next(w for w in words if w not in said))
        below = [kept for kept in (
            walk(child, f'{address}.{index}')
            for index, child in enumerate(node.get('children') or [])) if kept is not None]
        if not fits and not below:
            return None
        out = dict(node, searchId=address)
        if fits:
            count += 1
            out['hit'] = True
            if why:
                out['detail'] = ' · '.join(p for p in (node.get('detail'), f'has {why}') if p)
        if below:
            children = node.get('children') or []
            if len(below) < len(children):
                out['all'] = [{key: child[key] for key in SIBLING if child.get(key)}
                              for child in children]
            out['children'] = below
            out['expand'] = True
        return out

    kept = [row for row in (walk(root, str(index)) for index, root in enumerate(roots))
            if row is not None]
    return kept, count


def _blocks(package, role):
    index = package.index(role)
    cache = {}

    def text_of(subject):
        if subject not in cache:
            path, block = index.block_for(_iri(subject))
            cache[subject] = '' if path is None or block is None else \
                index.source_of(path)[block.start:block.end]
        return cache[subject]
    return index, text_of


def _iri(subject):
    from rdflib import URIRef
    return URIRef(str(subject))


def extras(package, view):
    """extra(node) for a view: what a row stands for beyond what it shows."""
    from ..rdfio import find_block, property_blocks

    if view == 'model':
        from ..expect.store import examples_root, load_expectations

        root = examples_root(package.path)
        cases = {}
        for example in load_expectations(package.path).examples:
            cases[os.path.abspath(os.path.join(root, example.path))] = ' '.join(
                [example.description] + [f'{a.get("constraint", "")} {a.get("resource", "")}'
                                         for a in example.asserts])
        return lambda node: cases.get(os.path.abspath(node['file']), '') \
            if node.get('kind') == 'example' and node.get('file') else ''
    if view == 'knowledge':
        _, text_of = _blocks(package, 'knowledge')
        return lambda node: text_of(node['iri']) \
            if node.get('iri') and node.get('kind') in ('class', 'attribute', 'individual') else ''

    index, text_of = _blocks(package, 'shapes')

    groups = {}

    def extra(node):
        shape = node.get('shape')
        if not shape:
            return ''
        chain = list(node.get('path') or [])
        if not chain:
            return text_of(shape)
        # A row under a property (an attribute, and in full form each of its
        # parameters): that property's statement, not the whole shape's.
        path, block = index.block_for(_iri(shape))
        if path is None or block is None:
            return ''
        source = index.source_of(path)
        if shape not in groups:        # read once: a shape may have hundreds of rows
            groups[shape] = property_blocks(source, block)
        found = find_block(groups[shape], chain)
        return source[found.start:found.end] if found is not None else ''
    return extra


def searched(payload, text, view, load):
    """A view's payload, pruned to what fits `text` (none: as it is)."""
    text = str(text or '').strip()
    if not text or payload.get('error'):
        return payload
    roots, count = prune(payload.get('roots') or [], text, extras(load(), view))
    return dict(payload, roots=roots, search=text, matches=count)


# --- from a file back to its page --------------------------------------------------------

def page_at(package, path, line, token='', text=None):
    """What the 1-based `line` of a package's file is about, as a page:
    {'page': 'shape' | 'type' | 'vocabulary' | 'case' | 'model' | 'search', …}.
    `token` is the word at the cursor: what to search for when the line is
    about nothing that has a page. `text` is the file as the editor shows it,
    when it is not saved: the line is one of that."""
    given = os.path.abspath(path)
    path = os.path.realpath(path)
    if text is None:
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
    if path.endswith(('.yaml', '.yml')):
        # Its entries name cases from where the editor has it, a link or not.
        return _expectations_page(given, text, line) or _search(token)
    if path.endswith(('.jsonld', '.json')):
        return _data_page(package, path, text, line) or _search(token)
    for role in ('shapes', 'knowledge'):
        if path in [os.path.realpath(p) for p in package.files(role)]:
            found = _statement_at(text, line)
            if found:
                return (_shape_page if role == 'shapes' else _knowledge_page)(package, found) \
                    or _search(token or local(found))
    return _search(token)


def _search(token):
    text = str(token or '').strip('<>"').rstrip('/.;,')
    return {'page': 'search', 'text': re.split(r'[/#:]', text)[-1] if text else ''}


def _statement_at(text, line):
    from ..rdfio import TurtleIndex

    blocks = [b for b in TurtleIndex(text).blocks if b.start_line <= line]
    return str(blocks[-1].subject) if blocks else ''


def _shape_page(package, subject):
    from ..validate.shapes import every_node_shape

    if subject in {str(s) for s in every_node_shape(package.shapes)}:
        return {'page': 'shape', 'shape': subject}
    return _knowledge_page(package, subject)


def _knowledge_page(package, subject):
    from rdflib import RDF, RDFS
    from rdflib.namespace import OWL

    from ..cooked.choices import attribute_terms, entity_types

    types = {t.iri for t in entity_types(package)[0]}
    if subject in types:
        return {'page': 'type', 'targetClass': subject}
    if any(a.iri == subject for a in attribute_terms(package)):
        domain = next((str(d) for d in sorted(package.knowledge.objects(_iri(subject), RDFS.domain))
                       if str(d) in types), None)
        return {'page': 'type', 'targetClass': domain, 'focusNames': [local(subject)]} \
            if domain else None
    kinds = [k for k in package.knowledge.objects(_iri(subject), RDF.type)]
    if OWL.Class in kinds or RDFS.Class in kinds:
        return {'page': 'vocabulary', 'cls': subject}
    cls = next((str(k) for k in sorted(kinds) if not str(k).startswith(
        (str(OWL), str(RDF), str(RDFS))) and str(k) not in types), None)
    return {'page': 'vocabulary', 'cls': cls, 'focus': subject} if cls else None


def _data_page(package, path, text, line):
    import json

    from ..cooked.jsonloc import locate
    from ..expect.store import examples_root, load_expectations

    entity = None
    try:
        data = json.loads(text)
        if isinstance(data, list):
            starts = sorted((at, key[0]) for key, at in locate(text).items() if len(key) == 1)
            before = [index for at, index in starts if at <= line]
            data = data[before[-1]] if before else {}
        entity = data.get('id') or data.get('@id') if isinstance(data, dict) else None
    except ValueError:
        pass                           # half-typed: the page, at no entity
    if path in [os.path.realpath(p) for p in package.files('model')]:
        return {'page': 'model', 'focus': entity}
    root = examples_root(package.path)
    examples = load_expectations(package.path).examples
    own = next((e for e in examples if os.path.realpath(os.path.join(root, e.path)) == path), None)
    if own is None:
        # A file cases include: the first of them shows it.
        own = next((e for e in examples for i in e.include if path in (
            os.path.realpath(os.path.join(root, i)),
            os.path.realpath(os.path.join(package.path, i)))), None)
    return {'page': 'case', 'file': os.path.abspath(os.path.join(root, own.path)),
            'focus': entity} if own is not None else None


def _expectations_page(path, text, line):
    from ..expect.store import _yaml

    try:
        raw = _yaml().load(text) or {}
    except Exception:                              # noqa: BLE001
        return None
    entries = raw.get('examples') if isinstance(raw, dict) else None
    found = None
    for entry in entries or []:
        try:
            if entry.lc.line + 1 <= line:
                found = entry.get('path')
        except AttributeError:
            continue
    return {'page': 'case', 'file': os.path.normpath(os.path.join(os.path.dirname(path), found)),
            'focus': None} if found else None


# --- pins --------------------------------------------------------------------------------

def pins_exist(package, pins):
    """[bool] -- per pin ({'kind', 'id', 'names', 'file'}), is it still there?"""
    from rdflib import RDF
    from rdflib.namespace import SH

    from ..cooked.choices import attribute_terms, entity_types
    from ..expect.store import examples_root, load_expectations
    from ..rdfio.relative import as_written
    from ..validate.shapes import every_node_shape

    root = examples_root(package.path)
    types = {t.iri for t in entity_types(package)[0]}
    shapes = {str(s) for s in every_node_shape(package.shapes)}
    attributes = {a.label for a in attribute_terms(package)}
    cases = {os.path.abspath(os.path.join(root, e.path)) for e in load_expectations(package.path).examples}
    entities = {as_written(s) for s in package.model.subjects(RDF.type, None)}

    def there(pin):
        kind, name = pin['kind'], str(pin['id'] or '')
        if kind == 'type':
            return name in types
        if kind == 'attribute':
            return name in types and all(n in attributes for n in pin.get('names') or [])
        if kind in ('shape', 'query'):
            return name in shapes
        if kind == 'case':
            return os.path.abspath(name) in cases
        if kind == 'entity':
            # In its case's file when it names one; only otherwise in the model.
            return _written_in(pin['file'], name) if pin.get('file') else name in entities
        if kind == 'vocabulary':
            # sh:Severity's page is SHACL's own levels, whatever the knowledge says.
            return name in (str(SH.Severity), 'sh:Severity') or (_iri(name), None, None) in package.knowledge
        return True
    return [there(pin) for pin in pins]


def _written_in(path, entity):
    """Is the id written in this file -- a case's, or one it includes?"""
    import json

    try:
        with open(path or '', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    return any(isinstance(d, dict) and entity in (d.get('id'), d.get('@id'))
               for d in (data if isinstance(data, list) else [data]))
