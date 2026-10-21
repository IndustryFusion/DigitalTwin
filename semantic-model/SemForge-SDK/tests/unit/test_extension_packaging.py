"""Does the packaged extension carry what it requires at runtime?

This is the bug that reached a user and stayed invisible through three rounds of
fixes. `.vscodeignore` excluded `node_modules/**`, so `vscode-languageclient`
was never packaged -- and extension.js requires it at MODULE LOAD, before
anything else. The require threw MODULE_NOT_FOUND, the extension never
activated, and the only symptom was a view saying "There is no data provider
registered" with no log entry at all.

The activation harness could not see it: it stubs that module, which is right
for testing activation logic and exactly wrong for testing whether the module
ships. So completeness gets its own check.
"""

import json
import os
import re
import subprocess
import sys
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
VSCODE = os.path.join(SDK, 'vscode')
SOURCES = ('extension.js', 'tree.js', 'model.js', 'init.js')

REQUIRE = re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)")
BUILTIN = set(sys.builtin_module_names) | {
    'fs', 'path', 'child_process', 'os', 'util', 'url', 'events', 'stream',
    'crypto', 'http', 'https', 'net', 'zlib', 'assert', 'buffer',
}


def runtime_requires():
    """Bare module names the extension requires, excluding vscode and builtins.

    `vscode` is provided by the host, never packaged.
    """
    found = set()
    for name in SOURCES:
        with open(os.path.join(VSCODE, 'src', name)) as handle:
            for target in REQUIRE.findall(handle.read()):
                if target.startswith('.') or target == 'vscode':
                    continue
                root = target.split('/')[0]
                if root not in BUILTIN:
                    found.add(root)
    return found


def test_the_extension_has_runtime_dependencies_at_all():
    assert 'vscode-languageclient' in runtime_requires()


def test_every_runtime_require_is_declared_as_a_dependency():
    with open(os.path.join(VSCODE, 'package.json')) as handle:
        declared = set(json.load(handle).get('dependencies') or {})
    missing = runtime_requires() - declared
    assert not missing, f'required but not declared: {sorted(missing)}'


def test_node_modules_is_not_excluded_from_the_package():
    """Excluding it is what broke this, so the exclusion itself is asserted away."""
    ignore = os.path.join(VSCODE, '.vscodeignore')
    with open(ignore) as handle:
        lines = [line.strip() for line in handle if not line.strip().startswith('#')]
    assert not any(line.startswith('node_modules') for line in lines), \
        'node_modules must ship: extension.js requires vscode-languageclient ' \
        'at module load'


def test_the_installed_extension_carries_its_dependencies():
    """The copy VS Code actually loads, not just the source tree."""
    candidates = []
    for base in ('.vscode-server', '.vscode', '.vscode-server-insiders'):
        directory = os.path.join(os.path.expanduser('~'), base, 'extensions')
        if os.path.isdir(directory):
            candidates += [os.path.join(directory, name)
                           for name in os.listdir(directory)
                           if name.startswith('industryfusion.semforge')]
    if not candidates:
        pytest.skip('the extension is not installed in this environment')

    for installed in candidates:
        modules = os.path.join(installed, 'node_modules')
        assert os.path.isdir(modules), \
            f'{installed} has no node_modules; the extension cannot load'
        for required in runtime_requires():
            assert os.path.isdir(os.path.join(modules, required)), \
                f'{installed} is missing {required}'


def test_the_built_package_carries_them_too():
    vsix = os.path.join(VSCODE, 'semforge-0.1.0.vsix')
    if not os.path.exists(vsix):
        pytest.skip('no packaged vsix to inspect')

    with zipfile.ZipFile(vsix) as archive:
        names = archive.namelist()
    for required in runtime_requires():
        assert any(f'node_modules/{required}/' in name for name in names), \
            f'the vsix does not contain {required}'


def test_the_entry_point_resolves_its_requires_for_real():
    """Resolve each dependency from the INSTALLED entry point.

    Asking node to resolve them is the same question the extension host asks,
    and it needs no stub at all.
    """
    installed = None
    for base in ('.vscode-server', '.vscode'):
        directory = os.path.join(os.path.expanduser('~'), base, 'extensions')
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                if name.startswith('industryfusion.semforge'):
                    installed = os.path.join(directory, name)
    if installed is None:
        pytest.skip('the extension is not installed in this environment')

    import shutil
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')

    entry = os.path.join(installed, 'src', 'extension.js')
    for required in sorted(runtime_requires()):
        result = subprocess.run(
            [node, '-e', f'require.resolve({required!r}, '
                         f'{{paths: [{os.path.dirname(entry)!r}]}})'],
            capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, \
            f'{required} does not resolve from the installed extension:\n' \
            f'{result.stderr[-400:]}'
