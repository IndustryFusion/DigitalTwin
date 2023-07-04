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

import statetime.sqlite_statetime_v1 as sqlite_statetime


def test_statetime_init():
    statetime = sqlite_statetime.Statetime()
    assert statetime.accum == [None, None, None, None, None, {}, {}]
    assert statetime.flink_statetime is not None


def test_statetime_init_step():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 10)
    assert statetime.accum == [None, None, None, None, None, {10: 1}, {}]


def test_statetime_true_step():
    statetime = sqlite_statetime.Statetime()
    statetime.accum = [10, 1, 10, None, 10, {}, {}]
    statetime.step(1, 17)
    assert statetime.accum == [10, 1, 10, None, 10, {17: 1}, {}]
    statetime.accum = [None, 1, 10, None, None, {}, {}]
    statetime.step(1, 15)
    assert statetime.accum == [None, 1, 10, None, None, {15: 1}, {}]
    statetime.accum = [None, 0, 10, 0, 10, {}, {}]
    statetime.step(1, 15)
    statetime.finalize()
    assert statetime.accum == [None, 1, 15, 0, 10, {}, {}]
    statetime.accum = [11, 0, 10, None, None, {}, {}]
    statetime.step(1, 13)
    statetime.finalize()
    assert statetime.accum == [11, 1, 13, 1, 13, {}, {}]


def test_statetime_false_step():
    statetime = sqlite_statetime.Statetime()
    statetime.accum = [10, 0, 10, None, None, {}, {}]
    statetime.step(0, 17)
    statetime.finalize()
    assert statetime.accum == [10, 0, 17, 0, 17, {}, {}]
    statetime.accum = [None, 1, 10, 1, 10, {}, {}]
    statetime.step(0, 15)
    statetime.finalize()
    assert statetime.accum == [5, 0, 15, 1, 10, {}, {}]
    statetime.accum = [2, 0, 3318, 1, 3316, {}, {}]
    statetime.step(0, 3325)
    statetime.finalize()
    assert statetime.accum == [2, 0, 3325, 1, 3316, {}, {}]


def test_inverse_all_true():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 11)
    statetime.step(1, 13)
    statetime.step(1, 17)
    statetime.inverse(1, 11)
    statetime.inverse(1, 13)
    result = statetime.finalize()
    assert result is None
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 11)
    statetime.step(1, 13)
    statetime.step(1, 17)
    statetime.inverse(1, 17)
    result = statetime.finalize()
    assert result == 2


def test_inverse_all_false():
    statetime = sqlite_statetime.Statetime()
    statetime.step(0, 11)
    statetime.step(0, 13)
    statetime.step(0, 17)
    statetime.inverse(0, 11)
    statetime.inverse(0, 13)
    result = statetime.finalize()
    assert result is None
    statetime = sqlite_statetime.Statetime()
    statetime.step(0, 11)
    statetime.step(0, 13)
    statetime.step(0, 17)
    statetime.inverse(0, 11)
    result = statetime.finalize()
    assert result is None


def test_inverse_all_mixed():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 1100)
    statetime.step(0, 1300)
    statetime.step(1, 1700)
    statetime.step(0, 1900)
    statetime.step(0, 2300)
    statetime.step(1, 2900)
    statetime.step(1, 3100)
    result = statetime.finalize()
    assert result == 600
    statetime.inverse(1, 1100)
    statetime.inverse(0, 1300)
    result = statetime.finalize()
    assert result == 400
    statetime.inverse(1, 1700)
    result = statetime.finalize()
    assert result == 400
    statetime.inverse(0, 1900)
    result = statetime.finalize()
    assert result == 200
    statetime.inverse(0, 2300)
    result = statetime.finalize()
    assert result == 200
    statetime.inverse(1, 2900)
    result = statetime.finalize()
    assert result == 0
    statetime.inverse(1, 3100)
    result = statetime.finalize()
    assert result == 0


def test_flow():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 10000)
    statetime.step(1, 20000)
    statetime.step(1, 23000)
    statetime.step(0, 28000)
    statetime.step(1, 30000)
    statetime.step(0, 32000)
    result = statetime.finalize()
    assert result == 20000


def test_extend():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 1100)
    statetime.step(0, 1300)
    statetime.step(1, 1700)
    statetime.step(0, 1900)
    statetime.step(0, 2300)
    statetime.step(1, 2900)
    statetime.step(1, 3100)
    result = statetime.finalize()
    assert result == 600
    statetime.step(0, 3101)
    statetime.step(1, 3102)
    statetime.step(1, 1050)
    statetime.step(0, 1000)
    result = statetime.finalize()
    assert result == 651


def test_shrink():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 1100)
    statetime.step(0, 1300)
    statetime.step(1, 1700)
    statetime.step(0, 1900)
    statetime.step(0, 2300)
    statetime.step(1, 2900)
    statetime.step(1, 3100)
    statetime.step(1, 3101)
    statetime.step(0, 3102)
    statetime.step(1, 1050)
    statetime.step(0, 1000)
    result = statetime.finalize()
    assert result == 652
    statetime.inverse(0, 1000)
    statetime.inverse(1, 1050)
    statetime.inverse(1, 3101)
    statetime.inverse(0, 3102)
    result = statetime.finalize()
    assert result == 651


def test_shrink_extend():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 1100)
    statetime.step(0, 1300)
    statetime.step(1, 1700)
    statetime.step(0, 1900)
    statetime.step(0, 2300)
    statetime.step(1, 2900)
    statetime.step(1, 3100)
    statetime.step(1, 1050)
    statetime.step(0, 1000)
    result = statetime.finalize()
    assert result == 650
    statetime.inverse(0, 1000)
    statetime.inverse(1, 1050)
    statetime.step(1, 3101)
    statetime.step(0, 3102)
    result = statetime.finalize()
    assert result == 652


def test_extend_shrink():
    statetime = sqlite_statetime.Statetime()
    statetime.step(1, 1100)
    statetime.step(0, 1300)
    statetime.step(1, 1700)
    statetime.step(0, 1900)
    statetime.step(0, 2300)
    statetime.step(1, 2900)
    statetime.step(1, 3100)
    statetime.step(1, 3101)
    statetime.step(0, 3102)
    result = statetime.finalize()
    assert result == 602
    statetime.step(0, 1000)
    statetime.step(1, 1050)
    statetime.inverse(1, 3101)
    statetime.inverse(0, 3102)
    result = statetime.finalize()
    assert result == 651
