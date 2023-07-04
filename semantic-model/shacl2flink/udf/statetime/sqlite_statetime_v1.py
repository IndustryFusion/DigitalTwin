import os
import sys

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import flink_statetime_v1 as flink_statetime  # noqa: E402


class Statetime:
    """ Maximum value in a range of cells. """

    def __init__(self):
        try:
            self.accum = [None, None, None, None, None, {}, {}]
            self.flink_statetime = flink_statetime.Statetime()
        except Exception as err:
            print(f"Statetime init: {err}")

    def step(self, state, timesInMs):
        try:
            self.flink_statetime.accumulate(self.accum, state, timesInMs)
        except Exception as err:
            print(f"Statetime step: {err}")

    def value(self):
        try:
            return self.flink_statetime.get_value(self.accum)
        except Exception as err:
            print(f"Statetime value: {err}")

    def finalize(self):
        try:
            return self.flink_statetime.get_value(self.accum)
        except Exception as err:
            print(f"Statetime finalize: {err}")

    def inverse(self, state, timesInMs):
        try:
            self.flink_statetime.retract(self.accum, state, timesInMs)
        except Exception as err:
            print(f"Statetime inverse: {err}")
