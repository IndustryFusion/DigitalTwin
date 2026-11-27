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

"""SemForge SDK: offline authoring and validation of semantic packages."""

__version__ = '0.1.0'

# Every SPARQL query in a SemForge process -- workbench, Inspect, pyshacl in
# `semforge test`, the spawned verdict worker -- picks its join order as it
# goes; rdflib's fixed order turns NGSI-LD chains into cross products.
# `import semforge` stays free of dependencies: the extension asks an
# interpreter whether it has SemForge by importing it, and one without rdflib
# runs no query to order.
try:
    from .sparql import order as _order  # noqa: E402
except ImportError:                          # pragma: no cover -- no rdflib
    _order = None
else:
    _order.install()
