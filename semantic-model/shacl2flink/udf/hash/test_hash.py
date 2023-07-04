#
# Copyright (c) 2022 Intel Corporation
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

import hash.sqlite_hash_v1 as sqlite_hash


def test_hash_value():
    result = sqlite_hash.eval(10)
    assert result == 120
    result = sqlite_hash.eval("hello world")
    assert result == hash("hello world") * 12
    result = sqlite_hash.eval(12.34)
    assert result == hash(12.34) * 12
