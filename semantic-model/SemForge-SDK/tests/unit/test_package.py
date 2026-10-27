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

"""Package loading, and invariant P1."""

import pytest
from rdflib.compare import isomorphic

from semforge.errors import PackageError
from semforge.package import load


def test_loads_the_kms_triple(corpus):
    assert len(corpus.knowledge) > 0
    assert len(corpus.shapes) > 0
    assert len(corpus.model) > 0


def test_missing_artifact_names_what_is_missing(tmp_path):
    with pytest.raises(PackageError) as exc:
        load(str(tmp_path))
    message = str(exc.value)
    assert 'knowledge' in message and 'shapes' in message and 'model' in message


def test_p1_roundtrip_is_isomorphic(corpus, tmp_path):
    """P1: load then save with no edits yields an isomorphic dataset.

    Byte-identity is a separate property (H5, deterministic export) and is not
    claimed here. Isomorphism is what says no statement was lost or invented.
    """
    for role in ('knowledge', 'shapes'):
        original = getattr(corpus, role)
        out = tmp_path / f'{role}.ttl'
        original.serialize(destination=str(out), format='turtle')

        reloaded = type(original)()
        reloaded.parse(str(out), format='turtle')
        assert isomorphic(original, reloaded), f'{role} did not round-trip'
