import os
import sys

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import flink_hash_v1 as flink_hash  # noqa: E402


flink = flink_hash.HashCode()


def eval(value):
    try:
        return flink.eval(value)
    except Exception as err:
        print(f"Statetime finalize: {err}")
