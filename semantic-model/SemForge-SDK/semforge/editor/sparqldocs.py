"""The SPARQL workbench's query documents, as the language server sees them.

A query is opened as `semforge-sparql:/<Shape>.rq?<ref>`: a real editor
document whose `<ref>` (base64url JSON) names the package, the shape and
which of its queries it is. Saving it writes the query into shacl.ttl (the
extension's file system provider does that); here is everything an editor
asks while it is being typed -- diagnostics, completion, hover, formatting,
quick fixes -- translated between LSP and semforge.sparql.
"""

import base64
import json
from urllib.parse import unquote, urlparse

from lsprotocol import types

SCHEME = 'semforge-sparql'
SOURCE = 'semforge-sparql'
SEVERITY = {'error': types.DiagnosticSeverity.Error,
            'warning': types.DiagnosticSeverity.Warning,
            'info': types.DiagnosticSeverity.Information}
KINDS = {'class': types.CompletionItemKind.Class,
         'property': types.CompletionItemKind.Property,
         'enum': types.CompletionItemKind.EnumMember,
         'keyword': types.CompletionItemKind.Keyword,
         'module': types.CompletionItemKind.Module,
         'variable': types.CompletionItemKind.Variable,
         'function': types.CompletionItemKind.Function,
         'snippet': types.CompletionItemKind.Snippet,
         'text': types.CompletionItemKind.Text}


# Quick fix titles per finding; {replace} is the text it writes.
TITLES = {
    'skipped-layer': 'Read the value: {replace}',
    'constant-object': 'Put it inside the instance: {replace}',
    'explicit-node': 'Write the instance as {replace}',
    'variable-node': 'Read the instance: {replace}',
    'path': 'Write it as {replace}',
    'plain-bracket': 'Read it directly: {replace}',
}


def is_query(uri):
    return str(uri).startswith(SCHEME + ':')


def reference(uri):
    """{package (uri), shape, holder, kind} from a query document's URI."""
    query = unquote(urlparse(uri).query)
    padded = query + '=' * (-len(query) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    return {'package': data.get('p', ''), 'shape': data.get('s', ''),
            'holder': int(data.get('h', 0)), 'kind': data.get('k', 'constraint')}


class Context:
    """What a query document is about: its package, shape, kind and view."""

    def __init__(self, package, shape, kind, view, prefix_lines, terms):
        self.package, self.shape, self.kind = package, shape, kind
        self.view, self.prefix_lines, self.terms = view, prefix_lines, terms


def context(uri, package_for, package_root, uri_to_path):
    from rdflib import URIRef

    from ..cooked.sparqlbench import _holder_node, _prefix_lines, holders
    from ..sparql.terms import terms_for
    from ..validate import shapes as shape_views

    ref = reference(uri)
    root = package_root(uri_to_path(ref['package']))
    if root is None:
        return None
    package = package_for(root)
    found = holders(package, ref['shape'])
    holder = found[min(ref['holder'], len(found) - 1)] if found else None
    kind = holder['kind'] if holder else ref['kind']
    prefix_lines = _prefix_lines(package, _holder_node(package, ref['shape'], kind,
                                                       holder['query'])) if holder else []
    view = shape_views.view_of(package.shapes, URIRef(ref['shape'])).value
    return Context(package, ref['shape'], kind, view, prefix_lines, terms_for(package))


def _range(text, start, end):
    from ..sparql.lexer import position

    a, b = position(text, start), position(text, end)
    return types.Range(types.Position(*a), types.Position(*b))


def diagnostics(text, ctx):
    from ..sparql.check import check

    out = []
    for finding in check(text, ctx.terms, ctx.kind, ctx.view, ctx.prefix_lines):
        out.append(types.Diagnostic(
            range=_range(text, finding.start, finding.end), message=finding.message,
            severity=SEVERITY[finding.severity], source=SOURCE, code=finding.code,
            data=dict(finding.data, code=finding.code)))
    return out


def completion(text, offset, ctx):
    from ..sparql.complete import complete

    items = []
    for item in complete(text, offset, ctx.terms):
        edits = [types.TextEdit(range=_range(text, a, b), new_text=t)
                 for a, b, t in item['edits']]
        documentation = types.MarkupContent(kind=types.MarkupKind.Markdown,
                                            value=item['documentation']) \
            if item['documentation'] else None
        items.append(types.CompletionItem(
            label=item['label'], kind=KINDS.get(item['kind'], types.CompletionItemKind.Text),
            detail=item['detail'] or None, documentation=documentation,
            sort_text=item['sort'], filter_text=item['filter'],
            insert_text_format=(types.InsertTextFormat.Snippet if item['snippet']
                                else types.InsertTextFormat.PlainText),
            text_edit=types.TextEdit(range=_range(text, item['start'], item['end']),
                                     new_text=item['insert']),
            additional_text_edits=edits or None,
            command=types.Command(title='suggest', command='editor.action.triggerSuggest')
            if item['retrigger'] else None))
    return types.CompletionList(is_incomplete=False, items=items)


def hover(text, offset, ctx):
    from ..sparql.complete import hover as hover_text

    said = hover_text(text, offset, ctx.terms)
    if not said:
        return None
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown,
                                                    value=said))


def formatting(text):
    """[TextEdit] replacing the whole query, or raises FormatError."""
    from ..sparql.format import format_query

    formatted = format_query(text)
    if formatted == text:
        return []
    return [types.TextEdit(range=_range(text, 0, len(text)), new_text=formatted)]


def code_actions(uri, text, ctx, params):
    """Quick fixes for the findings, and two refactorings at the cursor:
    a prefixed name written out as its IRI, and an IRI shortened to one."""
    from ..sparql.lexer import at, declared_prefixes, offset_of, prologue_end

    actions = []

    def edit(title, edits, kind=types.CodeActionKind.QuickFix, diagnostic=None,
             preferred=False):
        actions.append(types.CodeAction(
            title=title, kind=kind, is_preferred=preferred,
            diagnostics=[diagnostic] if diagnostic else None,
            edit=types.WorkspaceEdit(changes={uri: edits})))

    for diagnostic in params.context.diagnostics or []:
        if diagnostic.source != SOURCE or not isinstance(diagnostic.data, dict):
            continue
        data = diagnostic.data
        if data.get('code') == 'undeclared-prefix' and data.get('namespace'):
            spot = prologue_end(text)
            edit(f'Add PREFIX {data["prefix"]}: <{data["namespace"]}>',
                 [types.TextEdit(range=_range(text, spot, spot),
                                 new_text=f'PREFIX {data["prefix"]}: <{data["namespace"]}>\n')],
                 diagnostic=diagnostic, preferred=True)
        elif data.get('code') == 'not-compiled' and data.get('domain'):
            title = 'Add a shape so shacl2flink reads it as NGSI-LD'
            actions.append(types.CodeAction(
                title=title, kind=types.CodeActionKind.QuickFix, diagnostics=[diagnostic],
                command=types.Command(title=title, command='semforge.nestForFlink', arguments=[{
                    'packageUri': reference(uri)['package'], 'attribute': data['attribute'],
                    'kind': data.get('kind', ''), 'entityType': data['domain']}])))
        elif data.get('replace'):
            span = data.get('span')
            target = _range(text, span[0], span[1]) if span else diagnostic.range
            edits = [types.TextEdit(range=target, new_text=data['replace'])]
            for start, end in data.get('remove') or []:
                # The statement and the line it leaves empty.
                while end < len(text) and text[end] in ' \t':
                    end += 1
                if end < len(text) and text[end] == '\n':
                    end += 1
                    while start > 0 and text[start - 1] in ' \t':
                        start -= 1
                edits.append(types.TextEdit(range=_range(text, start, end), new_text=''))
            edit(TITLES.get(data.get('code'), 'Change to {replace}').format(**data), edits,
                 diagnostic=diagnostic, preferred=True)
            if data.get('alternative'):
                edit(f'Only test that it is there: {data["alternative"]}',
                     [types.TextEdit(range=target, new_text=data['alternative'])],
                     diagnostic=diagnostic)

    cursor = offset_of(text, params.range.start.line, params.range.start.character)
    token = at(text, cursor)
    declared = declared_prefixes(text)
    if token is not None and token.kind == 'pname':
        prefix, _, local = token.text.partition(':')
        namespace = declared.get(prefix) or ctx.terms.namespaces.get(prefix)
        if namespace and local:
            edit(f'Write out as <{namespace}{local}>',
                 [types.TextEdit(range=_range(text, token.start, token.end),
                                 new_text=f'<{namespace}{local}>')],
                 kind=types.CodeActionKind.RefactorRewrite)
    elif token is not None and token.kind == 'iri':
        iri = token.text[1:-1]
        mine = next(((p, n) for p, n in declared.items() if iri.startswith(n) and iri != n), None)
        known = mine or ctx.terms.prefix_for(iri)
        if known and iri != known[1]:
            prefix, namespace = known
            edits = [types.TextEdit(range=_range(text, token.start, token.end),
                                    new_text=f'{prefix}:{iri[len(namespace):]}')]
            if prefix not in declared:
                spot = prologue_end(text)
                edits.insert(0, types.TextEdit(range=_range(text, spot, spot),
                                               new_text=f'PREFIX {prefix}: <{namespace}>\n'))
            edit(f'Shorten to {prefix}:{iri[len(namespace):]}', edits,
                 kind=types.CodeActionKind.RefactorRewrite)
    return actions or None
