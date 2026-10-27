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

"""NGSI-LD semantics: the data views validation runs against."""

from .views import (DataView, ViewStats, build_view, collapse_updates,
                    normalise_empty_lists)
from .build import KINDS, attribute, coerce, entity, kind_for_shape, payload_key

__all__ = ['DataView', 'ViewStats', 'build_view', 'collapse_updates',
           'normalise_empty_lists', 'KINDS', 'attribute', 'coerce', 'entity',
           'kind_for_shape', 'payload_key']
