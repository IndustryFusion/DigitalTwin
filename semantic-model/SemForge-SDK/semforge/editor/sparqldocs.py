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
    'variable-node': 'Read the instance: {replace}',
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
    if not any(d.severity == types.DiagnosticSeverity.Error for d in out):
        # A query the checks above refuse needs no second opinion.
        out.extend(_not_deployable(text, ctx))
    return out


def _not_deployable(text, ctx):
    """What keeps the query from being compiled to Flink SQL, at the line that
    has most of the pattern the compiler names."""
    import re

    from ..sparql.lexer import code_tokens
    from ..target.deploy import query_problem

    try:
        problem = query_problem(ctx.package, ctx.shape, ctx.kind, text)
    except Exception:                                # noqa: BLE001 -- never cost the squiggles
        return []
    if problem is None:
        return []
    # Names of the pattern (or of the reason): an IRI by what it expands to,
    # however the query or the compiler writes it; keywords and functions in
    # any case, as the query may spell them.
    prefixes = dict(re.findall(r'(?i)PREFIX\s+([\w-]*):\s*<([^>]*)>', text))

    def name(word):
        word = word.lstrip('?$')
        prefix, colon, rest = word.partition(':')
        if colon and prefix in prefixes and not rest.startswith('//'):
            word = f'<{prefixes[prefix]}{rest}>'
        return word.lower()

    named = problem.pattern or problem.reason
    words = {name(word) for word in re.findall(r'<[^>\s]*>|[?$\w:-]+', named)}
    code = list(code_tokens(text))
    head = next((i for i, t in enumerate(code) if t.kind == 'name' and t.upper in ('SELECT', 'CONSTRUCT')), -1)
    # Only the WHERE group: a projection or a CONSTRUCT template repeats the
    # names of the patterns but is never what the compiler refused.
    where = next((i for i in range(head + 1, len(code)) if code[i].kind == 'name' and code[i].upper == 'WHERE'), None)
    if where is None and head >= 0 and code[head].upper == 'SELECT':
        where = next((i for i in range(head + 1, len(code)) if code[i].text == '{'), None)
    first = (where if where is not None else head) + 1
    tokens = [t for t in code[first:] if t.kind in ('var', 'pname', 'name', 'iri')]
    lines = {}
    for token in tokens:
        lines.setdefault(text.count('\n', 0, token.start), []).append(token)
    best = max(lines.values(), default=tokens[:1],
               key=lambda found: sum(1 for t in found if name(t.text) in words))
    start, end = (best[0].start, best[-1].end) if best else (0, len(text))
    said = f' ({problem.pattern})' if problem.pattern else ''
    return [types.Diagnostic(
        range=_range(text, start, end), severity=types.DiagnosticSeverity.Error, source=SOURCE,
        code='not-deployable', data={'code': 'not-deployable'},
        message=f'Validation runs this query, but it cannot be deployed: {problem.reason}{said}')]


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
    # Offered prefixes are only the way to their terms: VS Code must ask again
    # at the colon. Told the list is complete, it goes on filtering it, and
    # after `ex:` shows the prefix alone -- Ctrl+Space then only toggles it.
    return types.CompletionList(is_incomplete=any(i.command for i in items), items=items)


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
        elif data.get('replace'):
            target = diagnostic.range
            edits = [types.TextEdit(range=target, new_text=data['replace'])]
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
