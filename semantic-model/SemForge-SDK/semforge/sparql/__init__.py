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

"""SPARQL as an editor reads it: tokens with positions, the package's terms,
and the language features built on them -- formatting, diagnostics,
completion, hover -- for the SPARQL workbench's query documents.

Everything here works on the query TEXT, and never changes what a query
means: the formatter checks that the tokens it emits are the tokens it read.
"""
