import sys
import re
import argparse
import sqlite3
import statetime.sqlite_statetime_v1 as sqlite_udf_statetime
import hash.sqlite_hash_v1 as sqlite_udf_hash


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='sqlite3_udf.py \
                                                  <database> <sqlscript>')
    parser.add_argument('databasefile', help='Path to sqlite database file')
    parser.add_argument('sqlscript', help='Path to SQL script file')
    parsed_args = parser.parse_args(args)
    return parsed_args


def regexp(y, x, search=re.search):
    return 1 if search(y, x) else 0


def main(databasefile, sqlscript):

    with sqlite3.connect(databasefile) as conn:
        with open(sqlscript, 'r') as file:
            conn.enable_load_extension(True)
            conn.load_extension('/usr/lib/sqlite3/pcre.so')
            conn.create_aggregate('statetime', 2, sqlite_udf_statetime.Statetime)
            conn.create_function('hash', 1, sqlite_udf_hash.eval)
            cur = conn.cursor()
            data = file.read()
            cur.executescript(
                f"BEGIN;\n{data}\n COMMIT;")


if __name__ == '__main__':
    args = parse_args()
    databasefile = args.databasefile
    sqlscript = args.sqlscript
    main(databasefile, sqlscript)
