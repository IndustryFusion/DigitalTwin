"""Actually activate the extension.

`node --check` parses; it cannot see a function that is CALLED and never
DEFINED. That is how `sdkDirectory` went missing in an edit and left the
extension throwing ReferenceError the moment VS Code activated it -- broken in
precisely the way that looks like "it finds nothing", which is the failure mode
this project keeps meeting.

So this runs `activate()` against a stub `vscode` and asserts the commands get
registered. It is the only test here that needs node; it skips if node is
absent rather than pretending to pass.
"""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
HARNESS = os.path.join(SDK, 'tests', 'harness', 'activate.js')
EXTENSION = os.path.join(SDK, 'vscode', 'src', 'extension.js')

EXPECTED = {
    'semforge.restart', 'semforge.revalidate', 'semforge.doctor',
    'semforge.editConstraint', 'semforge.removeConstraint',
    'semforge.refreshTree', 'semforge.goToDefinition', 'semforge.overrideHere',
    'semforge.editValue', 'semforge.refreshModel', 'semforge.addAttribute',
    'semforge.addEntity', 'semforge.addObservation', 'semforge.goToShape',
    'semforge.refreshKnowledge', 'semforge.showShapeForClass',
    'semforge.initPackage', 'semforge.newProject', 'semforge.selectPackage',
    'semforge.menu', 'semforge.editSetting', 'semforge.refreshProject',
    'semforge.addNamespace',
}


def _activate(corpus_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    result = subprocess.run(
        [node, HARNESS, os.path.abspath(corpus_path), EXTENSION],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (
        'activate() threw -- the extension would not load:\n'
        + result.stderr[-1500:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_activation_does_not_throw(corpus_path):
    _activate(corpus_path)


def test_every_command_is_registered(corpus_path):
    registered = set(_activate(corpus_path)['commands'])
    assert registered == EXPECTED, (
        f'missing: {sorted(EXPECTED - registered)}; '
        f'unexpected: {sorted(registered - EXPECTED)}')


def test_the_manifest_and_the_code_agree(corpus_path):
    """A command in one and not the other is dead either way."""
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        declared = {c['command']
                    for c in json.load(handle)['contributes']['commands']}
    registered = set(_activate(corpus_path)['commands'])
    assert declared == registered, (
        f'declared not registered: {sorted(declared - registered)}; '
        f'registered not declared: {sorted(registered - declared)}')


def test_a_usable_package_activates_without_an_error_popup(corpus_path):
    """The corpus has a working venv beside it, so nothing should be reported."""
    assert _activate(corpus_path)['errors'] == []


def test_every_view_has_an_onview_activation_event():
    """Clicking a contributed view has to activate the extension.

    Without `onView:`, VS Code renders the view with nothing behind it and says
    "There is no data provider registered that can provide view data" -- which
    reads as the extension being broken rather than asleep, and leaves no log
    entry at all because it never ran.
    """
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        manifest = json.load(handle)

    views = {view['id']
             for group in manifest['contributes']['views'].values()
             for view in group}
    events = set(manifest['activationEvents'])
    for view in views:
        assert f'onView:{view}' in events, \
            f'{view} can be shown without activating the extension'


def test_the_trees_anchor_to_the_folder_not_only_the_editor(corpus_path):
    """The common flow is "open the folder, click the icon" with no file open.

    Anchoring only to the active editor left the tree empty in exactly that
    case, with nothing to say why.
    """
    extension = open(os.path.join(SDK, 'vscode', 'src', 'extension.js')).read()
    # The session settles on a package BEFORE the views are built, so the
    # folder is the anchor and the editor is only the fallback.
    assert 'session.discover()' in extension
    assert extension.index('session.discover()') < extension.index('cookedTree.register')

    for name in ('tree.js', 'model.js', 'knowledge.js'):
        source = open(os.path.join(SDK, 'vscode', 'src', name)).read()
        # One resolver for all three. Each used to have its own copy, with a
        # different rule in knowledge.js -- so the three views could be showing
        # three different packages, and nothing on screen named any of them.
        assert 'provider.refresh(session.uri)' in source, \
            f'{name} does not take its package from the session'
        assert 'findPackageUri' not in source, \
            f'{name} still resolves a package of its own'

    shared = open(os.path.join(SDK, 'vscode', 'src', 'locate.js')).read()
    assert 'workspaceFolders' in shared


def test_the_active_package_is_shown_and_can_be_chosen(corpus_path):
    """"Which package is this?" must have an answer on screen.

    A window can hold several packages -- a model and a test project beside it
    is the ordinary case -- and the views picked one silently.
    """
    result = _activate(corpus_path)
    assert 'semforge.selectPackage' in result['commands']
    shown = ' '.join(result.get('statusBar', []))
    assert 'kms' in shown, f'the status bar does not name the package: {shown!r}'


def test_clicking_a_row_unfolds_it(corpus_path):
    """One click has to both show the row and leave it open.

    A click on a collapsible row toggles it, so the reveal that shows you the
    entity also closed it. Nothing but driving the handler catches that: the
    code parses either way.
    """
    result = _activate(corpus_path)
    assert 'semforgeModel' in result['views'], \
        'the examples view registered no selection handler'
    expanded = [r for r in result['revealed']
                if r['view'] == 'semforgeModel'
                and r['options'].get('expand')]
    assert expanded, (
        'selecting a row with children did not reveal it with expand; '
        f'reveals seen: {result["revealed"]}')
    # Revealing must not steal the selection or the focus back from the click.
    assert expanded[0]['options'].get('select') is False
    assert expanded[0]['options'].get('focus') is False


def test_every_menu_when_clause_names_a_context_value_that_exists():
    """An inline icon whose `when` matches nothing simply never appears.

    There is no error, no log line and no way to tell it apart from the command
    being broken -- so the contextValue strings in package.json are checked
    against the ones the trees actually set.
    """
    import re

    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    # Per view, because a contextValue the OTHER tree sets is no help: the
    # menu is matched against the tree named in the same `when`.
    sources = {}
    for view, name in (('semforgeProject', 'project.js'),
                       ('semforgeConstraints', 'tree.js'),
                       ('semforgeModel', 'model.js'),
                       ('semforgeKnowledge', 'knowledge.js')):
        with open(os.path.join(SDK, 'vscode', 'src', name)) as handle:
            sources[view] = handle.read()

    seen = 0
    for entry in menus:
        when = entry['when']
        view = re.search(r"view\s*==\s*(\w+)", when).group(1)
        source = sources[view]
        values = re.findall(r"viewItem\s*==\s*(\w+)", when)
        values += [v for group in re.findall(r"viewItem\s*=~\s*/([^/]+)/", when)
                   for v in re.findall(r"\w+", group)]
        assert values, f'no viewItem in {when!r}'
        for value in values:
            seen += 1
            assert f"'{value}'" in source, (
                f'{entry["command"]} is shown when viewItem == {value}, '
                f'which {view} never sets -- the icon would never appear')
    assert seen >= len(menus)


def test_the_context_value_table_covers_every_kind_the_server_sends(corpus):
    """A kind with no entry falls through to a bare label and loses its menu."""
    import re

    from semforge.cooked.examples import build_examples, flatten

    with open(os.path.join(SDK, 'vscode', 'src', 'model.js')) as handle:
        table = handle.read().split('CONTEXT_BY_KIND = {', 1)[1].split('};', 1)[0]
    known = set(re.findall(r"(\w+):", table))

    kinds = {node.kind for _, node in flatten(build_examples(corpus))}
    assert kinds <= known, f'no contextValue for {sorted(kinds - known)}'


def test_all_three_views_are_wired(corpus_path):
    """The project, then shapes, data and knowledge.

    A view contributed in package.json with no provider behind it renders "There
    is no data provider registered", which reads as the extension being broken.
    """
    result = _activate(corpus_path)
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        declared = [v['id']
                    for v in json.load(handle)['contributes']['views']['semforge']]
    assert declared == ['semforgeProject', 'semforgeConstraints',
                        'semforgeModel', 'semforgeKnowledge']
    # Every declared view got a provider and a selection handler at activation.
    assert set(declared) == set(result['views'])


def test_an_empty_view_offers_to_create_a_package():
    """A folder that is not a package needs an answer other than three empty
    trees, and it has to be reachable without knowing a command name."""
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        manifest = json.load(handle)

    welcome = manifest['contributes'].get('viewsWelcome') or []
    views = {entry['view'] for entry in welcome}
    declared = {v['id'] for v in manifest['contributes']['views']['semforge']}
    assert views == declared, 'a view can still be empty with nothing to do'
    for entry in welcome:
        assert 'command:semforge.initPackage' in entry['contents']
        assert 'command:semforge.doctor' in entry['contents']


def test_the_packaged_sources_include_the_new_module():
    """A required file missing from the vsix is a MODULE_NOT_FOUND at load."""
    with open(os.path.join(SDK, 'vscode', 'src', 'extension.js')) as handle:
        source = handle.read()
    assert "require('./init')" in source
    assert os.path.exists(os.path.join(SDK, 'vscode', 'src', 'init.js'))


def test_the_project_actions_live_in_one_submenu():
    """Creating a project is not a constraint action.

    The submenu sat in all four view title bars, so "New project" appeared
    inside Constraints -- one layer down from where it belongs. A project is a
    SemForge-level thing: it belongs to the Project view, to a folder in the
    Explorer, and to the SemForge menu, and to nothing below those.
    """
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        contributes = json.load(handle)['contributes']

    submenus = {entry['id'] for entry in contributes.get('submenus', [])}
    assert 'semforge.project' in submenus

    items = contributes['menus']['semforge.project']
    assert [entry['command'] for entry in items] == [
        'semforge.newProject', 'semforge.initPackage', 'semforge.doctor']
    declared = {c['command'] for c in contributes['commands']}
    assert {entry['command'] for entry in items} <= declared

    # A folder in the Explorer -- the classical gesture -- and the Project view.
    explorer = contributes['menus'].get('explorer/context', [])
    assert any(entry.get('submenu') == 'semforge.project'
               and 'explorerResourceIsFolder' in entry['when']
               for entry in explorer)
    hosting = {entry['when'] for entry in contributes['menus']['view/title']
               if entry.get('submenu') == 'semforge.project'}
    assert hosting == {'view == semforgeProject'}, hosting


def test_the_semforge_menu_is_the_level_above_the_views():
    """VS Code contributes no menu for a view container's header.

    Only per-view title bars exist, so the status bar item is the one place
    that is ABOVE all four views -- and project creation has to be reachable
    from it, not only from a view.
    """
    with open(os.path.join(SDK, 'vscode', 'src', 'packages.js')) as handle:
        source = handle.read()
    for command in ('semforge.newProject', 'semforge.initPackage',
                    'semforge.selectPackage'):
        assert command in source, f'{command} is not in the SemForge menu'


def test_every_submenu_entry_is_a_real_command(corpus_path):
    """A menu item whose command is not registered does nothing when clicked."""
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']
    registered = set(_activate(corpus_path)['commands'])
    for group, entries in menus.items():
        for entry in entries:
            if 'command' in entry:
                assert entry['command'] in registered, (group, entry['command'])
