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

"""The LSP features of a document: diagnostics' fixes, hover, definition,
references, symbols, completion and formatting -- and the SPARQL
workbench's query documents."""

import os
import re

from lsprotocol import types

from . import session, validation
from .analysis import definition_at, hover_at, package_root, references_at
from .protocol import field, local, path_to_uri, server, uri_to_path


WORD = re.compile(r'[A-Za-z_][\w.-]*:?[\w.-]*')


# The term as written, prefix kept: an IRI, a prefixed name (the empty prefix
# included), or a bare JSON-LD term. WORD drops the prefix, which is all
# go-to-definition needs; references cannot, because the prefix is what tells
# iffBaseShacl:CartridgeShape from iffFilterShacl:CartridgeShape.
TOKEN = re.compile(r'<[^<>\s]*>|(?:[A-Za-z_][\w.-]*)?:[\w.-]+|[A-Za-z_@][\w.-]*')


def _word_at(document, position):
    try:
        line = document.lines[position.line]
    except IndexError:
        return ''
    for match in WORD.finditer(line):
        if match.start() <= position.character <= match.end():
            return match.group(0).rstrip(':').split(':')[-1] or match.group(0)
    return ''


def _token_at(document, position):
    try:
        line = document.lines[position.line]
    except IndexError:
        return ''
    for match in TOKEN.finditer(line):
        if match.start() <= position.character <= match.end():
            return match.group(0).rstrip('.')
    return ''


def _offset(document, position):
    from ..sparql.lexer import offset_of
    return offset_of(document.source, position.line, position.character)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        validation.publish_query(ls, params.text_document.uri)
        return
    session.rename_baseline(params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=params.text_document.uri, diagnostics=[]))


@server.feature(types.TEXT_DOCUMENT_COMPLETION,
                types.CompletionOptions(trigger_characters=[':', '?', '$']))
def completion(ls, params):
    from .sparqldocs import completion as complete_query, is_query

    if not is_query(params.text_document.uri):
        return None
    ctx = validation._query_context(params.text_document.uri)
    if ctx is None:
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    return complete_query(document.source, _offset(document, params.position), ctx)


@server.feature(types.TEXT_DOCUMENT_FORMATTING)
def formatting(ls, params):
    from ..sparql.format import FormatError
    from .sparqldocs import formatting as format_query, is_query

    if not is_query(params.text_document.uri):
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    try:
        return format_query(document.source)
    except FormatError as exc:
        ls.window_show_message(types.ShowMessageParams(
            type=types.MessageType.Warning, message=f'SemForge: {exc}'))
        return None


@server.feature('semforge/sparqlQuery')
def sparql_query_feature(ls, params):
    """One query's saved text: what a query document opens with."""
    from ..cooked.sparqlbench import holders

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        found = holders(session.package_for(root), str(field(params, 'shape', '') or ''))
        index = int(field(params, 'holder') or 0)
        if not 0 <= index < len(found):
            return {'ok': False, 'error': 'this shape has no such SPARQL query (any more)'}
        return dict(found[index], ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        validation.publish_query(ls, params.text_document.uri)
        return
    session.rename_baseline(params.text_document.uri)
    validation.publish(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        return
    validation.publish(ls, params.text_document.uri)
    root = package_root(uri_to_path(params.text_document.uri))
    if root is not None:
        _offer_renames(ls, root)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls, params):
    from .sparqldocs import hover as hover_query, is_query

    if is_query(params.text_document.uri):
        ctx = validation._query_context(params.text_document.uri)
        document = ls.workspace.get_text_document(params.text_document.uri)
        return hover_query(document.source, _offset(document, params.position), ctx) \
            if ctx else None
    root = package_root(uri_to_path(params.text_document.uri))
    if root is None:
        return None
    package = session.package_for(root)
    document = ls.workspace.get_text_document(params.text_document.uri)
    markdown = hover_at(package, _word_at(document, params.position))
    if not markdown:
        return None
    return types.Hover(contents=types.MarkupContent(
        kind=types.MarkupKind.Markdown, value=markdown))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(ls, params):
    root = package_root(uri_to_path(params.text_document.uri))
    if root is None:
        return None
    package = session.package_for(root)
    document = ls.workspace.get_text_document(params.text_document.uri)
    found = definition_at(package, _word_at(document, params.position))
    if found is None:
        return None
    path, line = found
    return types.Location(
        uri=path_to_uri(path),
        range=types.Range(types.Position(line - 1, 0),
                          types.Position(line - 1, 0)))


@server.feature(types.TEXT_DOCUMENT_REFERENCES)
def references(ls, params):
    path = uri_to_path(params.text_document.uri)
    if package_root(path) is None:
        return None
    package = session.package_for(package_root(path))
    document = ls.workspace.get_text_document(params.text_document.uri)
    found = references_at(package, _token_at(document, params.position), path,
                          include_declaration=params.context.include_declaration)
    return [types.Location(uri=path_to_uri(reference.path),
                           range=_range_of(reference))
            for reference in found]


def _range_of(reference):
    line = reference.line - 1
    return types.Range(types.Position(line, reference.column),
                       types.Position(line, reference.column + reference.length))


def _fixes_for(diagnostic, uri):
    """The quick fixes one sanity diagnostic offers, as client commands.

    Commands rather than workspace edits: "Declare it" needs the author's
    answers (which type carries it, what kind it is), and the removals are
    span edits only the server knows how to make safely. The data each needs
    rode along on the diagnostic when it was published.
    """
    data = diagnostic.data if isinstance(diagnostic.data, dict) else {}
    code = data.get('code', '')
    subject = data.get('subject', '')
    actions = []

    def action(title, command, argument, preferred=False):
        actions.append(types.CodeAction(
            title=title, kind=types.CodeActionKind.QuickFix,
            diagnostics=[diagnostic], is_preferred=preferred,
            command=types.Command(title=title, command=command,
                                  arguments=[argument])))

    if data.get('declare'):
        action(f'Declare {local(data["declare"])} in the knowledge',
               'semforge.newAttribute',
               {'packageUri': uri, 'iri': data['declare']}, preferred=True)
    if code == 'undeclared-path':
        action(f'Remove this property shape for {local(subject)}',
               'semforge.removeUse',
               {'uri': uri, 'kind': 'property', 'file': data.get('file'),
                'offset': data.get('offset'), 'label': local(subject)})
    elif code == 'undeclared-key':
        action(f'Remove {local(subject)} from this entity',
               'semforge.removeUse',
               {'uri': uri, 'kind': 'key', 'file': uri_to_path(uri),
                'line': diagnostic.range.start.line + 1, 'iri': subject,
                'label': local(subject)})
    elif code == 'stale-assert':
        # Left behind by a rename typed into the .ttl: the constraint it
        # meant first, when exactly one shape declares the same one.
        if data.get('suggest'):
            action(f'Rename the assert to {data["suggest"]}', 'semforge.removeUse',
                   {'uri': uri, 'kind': 'retarget', 'file': data.get('file'),
                    'case': data.get('case'), 'index': data.get('index'),
                    'constraint': data['suggest'], 'label': subject,
                    'said': f'the assert now names {data["suggest"]}'}, preferred=True)
        action('Remove this assert', 'semforge.removeUse',
               {'uri': uri, 'kind': 'assert', 'file': data.get('file'),
                'case': data.get('case'), 'index': data.get('index'),
                'label': subject}, preferred=not data.get('suggest'))
    elif code == 'model-violation':
        # The page that shows it with its entity, its value and what says so.
        action('Show it on the Main page', 'semforge.openModelPage',
               {'packageUri': uri, 'focus': data.get('entity'),
                'attribute': data.get('attribute') or None}, preferred=True)
    elif code == 'severity-unlinked':
        action(f'Declare {local(subject)} a kind of sh:Severity', 'semforge.linkSeverityClass',
               {'packageUri': uri, 'cls': subject}, preferred=True)
    elif code in ('observed-at-invalid', 'observed-at-format', 'observed-at-mixed'):
        where = {'packageUri': uri, 'entity': data.get('entity'),
                 'attributePath': data.get('attributePath'), 'file': data.get('file'),
                 'index': data.get('index')}
        if code == 'observed-at-format':
            action(f'Write it as {data.get("observedAt")}', 'semforge.setObservedAt',
                   dict(where, observedAt=data.get('observedAt')), preferred=True)
        else:
            action('Set its time…', 'semforge.setObservedAt', where, preferred=True)
    elif code == 'observed-at-order':
        action('Sort them by time', 'semforge.sortObservations',
               {'packageUri': uri, 'entity': data.get('entity'),
                'attributePath': data.get('attributePath'), 'file': data.get('file'),
                'datasetId': data.get('datasetId', '')}, preferred=True)
    elif code == 'unit-unknown':
        action('Choose the unit…', 'semforge.setUnitCode',
               {'packageUri': uri, 'entity': data.get('entity'),
                'attributePath': data.get('attributePath'), 'file': data.get('file'),
                'datasetId': data.get('datasetId', ''), 'current': data.get('unit')},
               preferred=True)
        action(f'Add {data.get("unit")} as a unit of this package…', 'semforge.newUnit',
               {'packageUri': uri, 'code': data.get('unit')})
    elif code == 'dataset-unregistered':
        action(f'Register a prefix for {data.get("namespace")}…', 'semforge.addNamespace',
               {'packageUri': uri, 'namespace': data.get('namespace')}, preferred=True)
        action('Change the datasetId…', 'semforge.setDatasetId',
               {'packageUri': uri, 'entity': data.get('entity'),
                'attributePath': data.get('attributePath'), 'file': data.get('file'),
                'old': data.get('old')})
    elif code in ('dataset-none', 'dataset-not-iri', 'dataset-duplicate'):
        where = {'packageUri': uri, 'entity': data.get('entity'),
                 'attributePath': data.get('attributePath'), 'file': data.get('file'),
                 'old': data.get('old')}
        if code == 'dataset-none':
            action('Remove "datasetId": "@none" (the default instance has none)',
                   'semforge.setDatasetId', dict(where, new='@none'), preferred=True)
        elif code == 'dataset-not-iri':
            action('Change the datasetId…', 'semforge.setDatasetId', where, preferred=True)
        else:
            action('Give this instance its own datasetId…', 'semforge.setDatasetId',
                   dict(where, index=data.get('index')), preferred=True)
    elif code == 'unused-attribute':
        action(f'Delete {local(subject)}…', 'semforge.deleteAttribute',
               {'packageUri': uri, 'raw': {'iri': subject}}, preferred=True)
    return actions


@server.feature(types.TEXT_DOCUMENT_CODE_ACTION)
def code_action(ls, params):
    from .sparqldocs import code_actions, is_query

    if is_query(params.text_document.uri):
        ctx = validation._query_context(params.text_document.uri)
        document = ls.workspace.get_text_document(params.text_document.uri)
        return code_actions(params.text_document.uri, document.source, ctx, params) \
            if ctx else None
    actions = []
    for diagnostic in params.context.diagnostics or []:
        if str(diagnostic.source or '').startswith('semforge'):
            actions += _fixes_for(diagnostic, params.text_document.uri)
    return actions or None


@server.feature('semforge/removeUse')
def remove_use_feature(ls, params):
    """Remove exactly one use, at the place a sanity finding marked."""
    from ..cooked.remove_use import remove_assert, remove_key_at, remove_property_at

    root = package_root(uri_to_path(field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        kind = field(params, 'kind')
        target = field(params, 'file')
        note = ''
        if kind == 'property':
            remove_property_at(target, int(field(params, 'offset')))
        elif kind == 'key':
            remove_key_at(session.package_for(root), target, int(field(params, 'line')),
                          field(params, 'iri'))
        elif kind == 'assert':
            note = remove_assert(target, field(params, 'case'),
                                 int(field(params, 'index')))
        elif kind == 'retarget':
            from ..expect.stale import retarget_assert
            note = retarget_assert(target, field(params, 'case'),
                                   int(field(params, 'index')), field(params, 'constraint'))
        else:
            return {'ok': False, 'error': f'nothing knows how to remove a {kind}'}
        session.forget(root)
        validation.publish(ls, path_to_uri(target))
        return {'ok': True, 'file': target, 'note': note}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls, params):
    from ..rdfio import index_file

    path = uri_to_path(params.text_document.uri)
    if not path.endswith('.ttl') or not os.path.exists(path):
        return None
    index = index_file(path)
    lines = index.source.splitlines()

    def width(number):
        return len(lines[number]) if 0 <= number < len(lines) else 0

    symbols = []
    for block in index.blocks:
        name = block.raw_subject.strip()
        if not name:
            continue               # a symbol with no name is rejected outright
        first, last = block.start_line - 1, block.end_line - 1
        # The range must CONTAIN the selection range, and a one-line statement
        # made both degenerate: (L,0)-(L,0) around (L,0)-(L,1). The client
        # rejects that and the whole request fails, so the Outline was empty and
        # the log said only "provider FAILED".
        whole = types.Range(types.Position(first, 0),
                            types.Position(last, width(last)))
        subject = types.Range(
            types.Position(first, 0),
            types.Position(first, min(len(name), width(first))))
        symbols.append(types.DocumentSymbol(
            name=name, kind=types.SymbolKind.Class,
            range=whole, selection_range=subject))
    return symbols


def _offer_renames(ls, root):
    """After a save: for each rename typed into the file, what still names
    the old shape, sent to the client to offer carrying it along."""
    from ..cooked.rename import follow_plan

    package = session.package_for(root)
    for old, new in session.take_renames(root):
        try:
            plan = follow_plan(package, old, new)
        except Exception:                          # noqa: BLE001
            continue
        if plan:
            shapes = package.files('shapes')
            ls.protocol.notify('semforge/shapeRenamed', dict(
                plan, uri=path_to_uri(shapes[0] if shapes else os.path.join(root, 'shacl.ttl'))))
