"""The end-to-end suite (vscode/test/e2e) from pytest, when asked for.

It starts a real VS Code, so it is opt-in: `SEMFORGE_E2E=1 pytest -k e2e`, or
`make test-e2e`. Off by default because it needs a display and a one-time
download, not because it is optional to keep green.
"""

import os
import shutil
import subprocess

import pytest

SDK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.skipif(not os.environ.get('SEMFORGE_E2E'),
                    reason='a real VS Code run; set SEMFORGE_E2E=1 to include it')
def test_the_extension_in_a_real_vscode():
    npm = shutil.which('npm')
    if npm is None:
        pytest.skip('npm is not installed')
    result = subprocess.run([npm, 'run', 'test:e2e'], cwd=os.path.join(SDK, 'vscode'),
                            capture_output=True, text=True, timeout=900)
    tail = '\n'.join(line for line in result.stdout.splitlines()
                     if 'passing' in line or 'failing' in line or ') ' in line)
    assert result.returncode == 0, (tail or result.stdout[-3000:]) + result.stderr[-2000:]
