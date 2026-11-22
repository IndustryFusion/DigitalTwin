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

"""The headless Chromium the page tests run the pages' scripts in.

A test that needs one asks `chrome()`: SEMFORGE_CHROME if it names a file,
otherwise Playwright's Chromium under ~/.cache/ms-playwright. Without either
the test is skipped -- unless SEMFORGE_REQUIRE_CHROME is set (CI sets it), and
then it fails, so a missing browser can't turn the page tests into skips.
"""

import glob
import os

import pytest

SKIP_REASON = 'no headless Chromium (set SEMFORGE_CHROME)'


def required():
    """True when SEMFORGE_REQUIRE_CHROME asks for a browser ('', '0', 'false'
    and 'no' don't)."""
    return os.environ.get('SEMFORGE_REQUIRE_CHROME', '').strip().lower() not in (
        '', '0', 'false', 'no')


def find():
    """The browser's path, or None."""
    candidates = [os.environ.get('SEMFORGE_CHROME', '')] + sorted(glob.glob(
        os.path.expanduser('~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome')))
    return next((c for c in candidates if c and os.path.exists(c)), None)


def chrome():
    """The browser's path; skips the test without one, or fails it when one is
    required."""
    found = find()
    if found is None:
        if required():
            pytest.fail('no headless Chromium, and SEMFORGE_REQUIRE_CHROME is set '
                        '(SEMFORGE_CHROME=%r)' % os.environ.get('SEMFORGE_CHROME', ''),
                        pytrace=False)
        pytest.skip(SKIP_REASON)
    return found
