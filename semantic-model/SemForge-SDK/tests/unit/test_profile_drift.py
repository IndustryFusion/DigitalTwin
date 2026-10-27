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

"""The shacl2flink profile against shacl2flink itself.

semforge/target/profile.py hand-copies two facts about the compiler: how deep
sub-attributes may nest (MAX_SUBPROPERTY_DEPTH) and which SHACL constraint
types it compiles. A copy drifts silently -- the compiler changes, the SDK
keeps checking against the old facts. Until shacl2flink publishes a
capability descriptor the SDK reads, this test is the tripwire: it reads the
compiler's source and fails when the copy no longer matches.
"""

import glob
import os
import re

import pytest

from semforge.target.crosscheck import ALIASES
from semforge.target.profile import builtin_profile

SHACL2FLINK = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shacl2flink')
# The compiler's fallback name for an operator it does not recognise -- never
# emitted for a constraint a shape can declare.
INTERNAL = {'LogicalConstraintComponent'}
# Compiled, but never named: sh:node is inlined -- the compiler copies the
# referenced shape's constraints in and reports THEM.
INLINED = {'NodeConstraintComponent'}


def _sources():
    files = glob.glob(os.path.join(SHACL2FLINK, 'lib', '*.py'))
    if not files:
        pytest.skip('shacl2flink is not beside the SDK')
    return {path: open(path, encoding='utf-8').read() for path in files}


def emitted_components():
    """Every constraint type the compiler names in an alert: literal names,
    and the ones its SQL templates build (minmaxname= / validationname=)."""
    names = set()
    for text in _sources().values():
        names |= set(re.findall(r'\b([A-Z][A-Za-z]+ConstraintComponent)\b', text))
        names |= {f'{n}ConstraintComponent'
                  for n in re.findall(r'(?:minmaxname|validationname)="([A-Za-z]+)"', text)}
    return names - INTERNAL


def test_the_sub_attribute_depth_is_the_compiler_s():
    text = _sources()[os.path.join(SHACL2FLINK, 'lib', 'utils.py')]
    depth = int(re.search(r'^MAX_SUBPROPERTY_DEPTH\s*=\s*(\d+)', text, re.M).group(1))
    assert builtin_profile().max_subproperty_depth == depth


def test_every_constraint_type_the_compiler_emits_is_in_the_profile():
    profile = builtin_profile()
    known = profile.components | {ALIASES.get(c, c) for c in profile.components}
    missing = sorted(c for c in emitted_components() if c not in known)
    assert not missing, f'shacl2flink compiles {missing}; the SDK profile does not say so'


def test_every_constraint_type_the_profile_claims_is_compiled():
    emitted = emitted_components()
    claimed = sorted(c for c in builtin_profile().components - INLINED
                     if c not in emitted and ALIASES.get(c, c) not in emitted)
    assert not claimed, f'the SDK profile claims {claimed}; shacl2flink names none of them'
