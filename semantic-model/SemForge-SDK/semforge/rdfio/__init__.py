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

"""Reading and writing artifact text without losing what is not modelled."""

from .turtle_index import Block, PackageIndex, Term, TurtleIndex, index_file, terms
from .writer import add_property_constraint
from .blocks import (PropertyBlock, add_parameter, find_block, property_blocks,
                     remove_parameter, set_parameter)

__all__ = ['Block', 'PackageIndex', 'Term', 'TurtleIndex', 'index_file', 'terms',
           'add_property_constraint',
           'PropertyBlock', 'property_blocks', 'find_block', 'set_parameter',
           'add_parameter', 'remove_parameter']
