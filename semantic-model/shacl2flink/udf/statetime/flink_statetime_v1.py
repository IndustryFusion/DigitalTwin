from pyflink.common import Row
from pyflink.table import AggregateFunction, DataTypes
from pyflink.table.udf import udaf
from enum import IntEnum


class Index(IntEnum):
    """SQL Job states as defined by Flink"""
    STATETIME = 0
    LAST_STATE = 1
    LAST_TIME = 2
    FIRST_STATE = 3
    FIRST_TIME = 4
    BUFFER_ACCUM = 5
    BUFFER_RETRACT = 6


class Statetime(AggregateFunction):

    def create_accumulator(self):
        # statetime, last_state, last_timeInMs, first_state, first_timeInMs
        return Row(None, None, None, None, None, {}, {})

    def get_value(self, accumulator):
        self.calc_buffer(accumulator)
        return accumulator[Index.STATETIME]

    def accumulate(self, accumulator, state, timeInMs):
        if state is None or timeInMs is None:
            return
        if timeInMs in accumulator[Index.BUFFER_RETRACT]:
            del accumulator[Index.BUFFER_RETRACT][timeInMs]
        else:
            accumulator[Index.BUFFER_ACCUM][timeInMs] = state

    def retract(self, accumulator, state, timeInMs):
        if state is None or timeInMs is None:
            return
        if timeInMs in accumulator[Index.BUFFER_ACCUM]:
            del accumulator[Index.BUFFER_ACCUM][timeInMs]
        else:
            accumulator[Index.BUFFER_RETRACT][timeInMs] = state

    def get_result_type(self):
        return DataTypes.BIGINT()

    def get_accumulator_type(self):
        return DataTypes.ROW([
                             DataTypes.FIELD("f0", DataTypes.INT()),
                             DataTypes.FIELD("f1", DataTypes.BIGINT())])

    def calc_buffer(self, accumulator):
        abuffer = accumulator[Index.BUFFER_ACCUM]
        rbuffer = accumulator[Index.BUFFER_RETRACT]

        if abuffer:
            if accumulator[Index.LAST_STATE] is None or accumulator[Index.LAST_TIME] is None or \
                    accumulator[Index.FIRST_STATE] is None or accumulator[Index.FIRST_TIME] is None:
                ts = min(abuffer)
                accumulator[Index.LAST_STATE] = abuffer[ts]
                accumulator[Index.LAST_TIME] = ts
                accumulator[Index.FIRST_STATE] = abuffer[ts]
                accumulator[Index.FIRST_TIME] = ts
            sorted_high = filter(lambda x: x > accumulator[Index.LAST_TIME], sorted(abuffer))
            sorted_low = filter(lambda x: x < accumulator[Index.FIRST_TIME], sorted(abuffer, reverse=True))
            for ts in list(sorted_low) + list(sorted_high):
                if ts > accumulator[Index.LAST_TIME]:
                    if accumulator[Index.STATETIME] is None and accumulator[Index.LAST_STATE] == 1:
                        accumulator[Index.STATETIME] = ts - accumulator[Index.LAST_TIME]
                    elif accumulator[Index.LAST_STATE] == 1:
                        accumulator[Index.STATETIME] += ts - accumulator[Index.LAST_TIME]
                    accumulator[Index.LAST_STATE] = abuffer[ts]
                    accumulator[Index.LAST_TIME] = ts
                elif ts < accumulator[Index.FIRST_TIME]:
                    if accumulator[Index.STATETIME] is None and abuffer[ts] == 1:
                        accumulator[Index.STATETIME] = accumulator[Index.FIRST_TIME] - ts
                    elif abuffer[ts] == 1:
                        accumulator[Index.STATETIME] += accumulator[Index.FIRST_TIME] - ts
                    accumulator[Index.FIRST_STATE] = abuffer[ts]
                    accumulator[Index.FIRST_TIME] = ts

        if accumulator[Index.LAST_STATE] is not None and accumulator[Index.LAST_TIME] is not None \
            and accumulator[Index.FIRST_STATE] is not None and accumulator[Index.FIRST_TIME] is not None \
                and rbuffer:
            sorted_buffer = sorted(rbuffer)
            while sorted_buffer:
                min_ts = sorted_buffer[0]
                max_ts = sorted_buffer[-1]
                if min_ts < accumulator[Index.FIRST_TIME]:
                    sorted_buffer.pop(0)
                    continue
                if max_ts > accumulator[Index.LAST_TIME]:
                    sorted_buffer.pop()
                    continue
                if accumulator[Index.LAST_TIME] - max_ts > min_ts - accumulator[Index.FIRST_TIME]:
                    # assuming retracting from FIRST_TIME up
                    # Heuristic: It is closer to FIRST_TIME
                    if accumulator[Index.FIRST_STATE] == 1:
                        accumulator[Index.STATETIME] -= min_ts - accumulator[Index.FIRST_TIME]
                    accumulator[Index.FIRST_STATE] = rbuffer[min_ts]
                    accumulator[Index.FIRST_TIME] = min_ts
                    sorted_buffer.pop(0)
                else:
                    # retract from LAST_TIME
                    if rbuffer[max_ts] == 1:
                        accumulator[Index.STATETIME] -= accumulator[Index.LAST_TIME] - max_ts
                    accumulator[Index.LAST_STATE] = rbuffer[max_ts]
                    accumulator[Index.LAST_TIME] = max_ts
                    sorted_buffer.pop()

        accumulator[Index.BUFFER_ACCUM] = {}
        accumulator[Index.BUFFER_RETRACT] = {}


def register(table_env):
    statetime = udaf(Statetime())
    table_env.create_temporary_function("statetime", statetime)
