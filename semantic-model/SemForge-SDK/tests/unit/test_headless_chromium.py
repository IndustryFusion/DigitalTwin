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

"""How the page tests find their browser: skipped locally without one, failed
when CI requires one (SEMFORGE_REQUIRE_CHROME)."""

import pytest

import headless_chromium


@pytest.fixture
def no_browser(monkeypatch, tmp_path):
    """No SEMFORGE_CHROME and an empty home, so no Playwright Chromium either."""
    monkeypatch.delenv('SEMFORGE_CHROME', raising=False)
    monkeypatch.delenv('SEMFORGE_REQUIRE_CHROME', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))


def _fake_browser(tmp_path, *parts):
    path = tmp_path.joinpath(*parts)
    path.parent.mkdir(parents=True)
    path.write_text('')
    return str(path)


def test_without_a_browser_the_page_test_is_skipped(no_browser):
    with pytest.raises(pytest.skip.Exception, match=r'no headless Chromium \(set SEMFORGE_CHROME\)'):
        headless_chromium.chrome()


@pytest.mark.parametrize('flag', ['1', 'true', 'yes'])
def test_without_a_browser_a_required_page_test_fails(no_browser, monkeypatch, flag):
    monkeypatch.setenv('SEMFORGE_REQUIRE_CHROME', flag)
    with pytest.raises(pytest.fail.Exception, match='SEMFORGE_REQUIRE_CHROME is set'):
        headless_chromium.chrome()


@pytest.mark.parametrize('flag', ['', '0', 'false', 'no'])
def test_a_flag_that_says_no_still_skips(no_browser, monkeypatch, flag):
    monkeypatch.setenv('SEMFORGE_REQUIRE_CHROME', flag)
    with pytest.raises(pytest.skip.Exception):
        headless_chromium.chrome()


def test_a_required_browser_that_is_not_there_fails(no_browser, monkeypatch, tmp_path):
    monkeypatch.setenv('SEMFORGE_REQUIRE_CHROME', '1')
    monkeypatch.setenv('SEMFORGE_CHROME', str(tmp_path / 'no-such-chrome'))
    with pytest.raises(pytest.fail.Exception, match='no-such-chrome'):
        headless_chromium.chrome()


def test_semforge_chrome_names_the_browser(no_browser, monkeypatch, tmp_path):
    browser = _fake_browser(tmp_path, 'bin', 'google-chrome')
    _fake_browser(tmp_path, '.cache', 'ms-playwright', 'chromium-1', 'chrome-linux64', 'chrome')
    monkeypatch.setenv('SEMFORGE_CHROME', browser)
    monkeypatch.setenv('SEMFORGE_REQUIRE_CHROME', '1')
    assert headless_chromium.chrome() == browser


def test_otherwise_playwrights_chromium_is_used(no_browser, tmp_path):
    browser = _fake_browser(tmp_path, '.cache', 'ms-playwright', 'chromium-1', 'chrome-linux64',
                            'chrome')
    assert headless_chromium.chrome() == browser
