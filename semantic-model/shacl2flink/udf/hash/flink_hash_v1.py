from pyflink.table import DataTypes
from pyflink.table.udf import ScalarFunction, udf


class HashCode(ScalarFunction):
    def __init__(self):
        self.factor = 12

    def eval(self, s):
        return hash(s) * self.factor


def register(table_env):
    hashcode = udf(HashCode(), result_type=DataTypes.BIGINT())
    table_env.create_temporary_function("hash", hashcode)
