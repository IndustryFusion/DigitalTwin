// The case page's own script on a minimal DOM (test_page_scripts.py): click a time link,
// set a time in the picker, press Set -- and see what the page posts.
const Module = require('module');
const path = require('path');
const original = Module._load;
Module._load = function (request, ...rest) {
  if (request === 'vscode') {
    return { QuickPickItemKind: { Separator: -1 }, window: {}, commands: {}, workspace: {} };
  }
  return original.call(this, request, ...rest);
};
const { renderCasePage } = require(path.resolve(process.argv[2]));
const page = { kind: 'case', name: 'x.jsonld', case: 'x.jsonld', expect: 'valid', group: '',
  suite: '', description: '', passed: true, failures: [], claims: [], unasserted: [],
  residuePinned: false, file: '/x.jsonld', files: [{ role: 'case', path: '/x.jsonld',
    relative: 'x.jsonld', sharedBy: [], cards: [{ id: 'urn:x:1', type: 'X', file: '/x.jsonld',
      violations: [], attributes: [{ name: 'hasX', term: 'e:hasX', kind: 'Property', value: '1',
        dataset: '', instances: 1, line: 1, violations: [], children: [],
        observedAt: '2026-01-01T00:00:00.000Z', stamp: { attributePath: ['e:hasX'], index: 0 },
        latestAt: '2026-01-01T00:00:00.000Z', superseded: false,
        node: { editable: true }, attributeNode: {} }] }] }] };
const html = renderCasePage(page, { nonce: 'n' });
const script = html.split('<script nonce="n">')[1].split('</script>')[0];
const at = html.match(/data-stamp="([^"]+)"/)[1];

function element(tag) {
  const el = { tag, children: [], listeners: {}, dataset: {}, value: '', className: '',
    classList: { contains: (c) => el.className.split(' ').includes(c) },
    append: (...kids) => { el.children.push(...kids); },
    addEventListener: (type, fn) => { el.listeners[type] = fn; },
    remove: () => { el.removed = true; },
    focus: () => {},
    closest: () => null };
  return el;
}
const posted = [];
const row = element('div');
row.className = 'attr';
row.nextElementSibling = null;
row.after = (box) => { row.inserted = box; };
const link = element('a');
link.dataset = { stamp: at, current: '2026-01-01T00:00:00.000Z', latest: '2026-01-01T00:00:00.000Z' };
link.nextElementSibling = null;
link.after = (box) => { link.inserted = box; };
link.closest = (selector) => (selector === '[data-stamp]' ? link
  : selector === '.attr' ? row : null);
const listeners = {};
const document = {
  addEventListener: (type, fn) => { listeners[type] = fn; },
  getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
  createElement: element
};
const window = { addEventListener: () => {}, scrollTo: () => {} };
const acquireVsCodeApi = () => ({ postMessage: (m) => posted.push(m), getState: () => ({}),
  setState: () => {} });
new Function('document', 'window', 'acquireVsCodeApi', script)(document, window, acquireVsCodeApi);
listeners.click({ target: link, preventDefault: () => {} });
const box = row.inserted;
if (!box) { console.log('NO PICKER OPENED'); process.exit(1); }
const input = box.children.find((c) => c.tag === 'input');
console.log('picker:', box.tag, box.className, '|', input.type, input.value, '|',
  box.children.filter((c) => c.tag === 'button').map((b) => b.textContent).join(' | '));
input.value = '2026-03-04T05:06:07.890';
box.children.find((c) => c.textContent === 'Set').listeners.click(
  { preventDefault: () => {}, stopPropagation: () => {} });
console.log('posted:', JSON.stringify(posted));
