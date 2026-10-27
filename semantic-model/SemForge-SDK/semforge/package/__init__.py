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

"""Loading and saving a semantic package."""

from .discover import describe, explain, find, is_package, root
from .loader import Package, load
from .registry import (Dependency, assemble_knowledge, dependencies_from_config,
                       digest, resolve)

__all__ = ['Package', 'load', 'describe', 'explain', 'find',
           'is_package', 'root', 'Dependency', 'assemble_knowledge',
           'dependencies_from_config', 'digest', 'resolve']


# Every parse of a JSON-LD document goes through rdflib's context fetch; this
# makes it fetch a remote context once per machine instead of once per parse.
from .context import install_context_cache  # noqa: E402

install_context_cache()
