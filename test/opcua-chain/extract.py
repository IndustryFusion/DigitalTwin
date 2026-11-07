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

"""Prints the command blocks of the tutorial which are marked with <!-- chain-test: NAME -->.

The test runs the tutorial's own commands, so a change which breaks a marked command fails the test.
Usage: extract.py TUTORIAL NAME [NAME ...]"""

import re
import sys

MARK = re.compile(r'^<!-- chain-test: ([a-z0-9-]+) -->\n```bash\n(.*?)^```$', re.MULTILINE | re.DOTALL)


def main(tutorial, names):
    blocks = {name: body for name, body in MARK.findall(open(tutorial).read())}
    missing = [name for name in names if name not in blocks]
    if missing:
        sys.exit(f'{tutorial} has no block marked {", ".join(missing)}')
    for name in names:
        print(f'# --- {name}')
        print(blocks[name], end='')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
