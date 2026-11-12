"""Deploy a statement set -- or validate it.

The request is what the operator posts: `sqlsettings` (single-key maps),
`tables` and `views` (DDL) and `sqlstatementset` (INSERT statements).

    job.py                          deploy data/SQL-structures.json
                                    (run by `flink run --python`)
    job.py --validate FILE...       validate requests without deploying
           [--udf-dir DIR]          (openspec gh-955-flink-sql-validation)

Validation runs everything a deployment runs up to the job -- UDFs, settings,
table and view DDL, the statement set -- with the same Flink, and has Flink
plan the statement set with `explain` instead of executing it: nothing is
submitted, and no connector opens a connection. For each file it prints one
line `VALIDATION <json>` -- the prefix keeps it apart from what Flink logs to
stdout -- with {"file", "valid"} plus, when a request is rejected, the
rejected item ("kind": udf, setting, table, view, statement or statementset,
its "index" and "text") and Flink's "message". It exits with 1 if any request
is rejected.
"""
from pyflink.table import TableEnvironment, EnvironmentSettings
import json
import pathlib
import os
import sys


JARDIR = '/opt/gateway/jars'
RESULT_PREFIX = 'VALIDATION '
# Lines of a Java stack trace in an error message: dropped from what
# validation reports, which is Flink's message, not where it was raised.
STACK_PREFIXES = ('\tat ', 'at ', '\t... ', '... ')
# The line Py4J puts before a Java exception's message.
PY4J_PREFIX = 'An error occurred while calling '
MAX_MESSAGE_LINES = 20


def create_table_env():
    env_settings = EnvironmentSettings.in_streaming_mode()
    table_env = TableEnvironment.create(env_settings)
    # Get all jars from /opt/gateway/jar
    jars = ';'.join(list(map(lambda x: "file://"+str(x),
                             pathlib.Path(JARDIR).glob('*.jar'))))
    table_env.get_config().set("pipeline.classpaths", jars)
    return table_env


def udf_files(udfdir):
    return sorted(file.name for file in os.scandir(udfdir)
                  if file.name.endswith('.py') and file.name != '__init__.py')


def register_udf(table_env, path):
    # In this module's namespace, as the deployment has always run them.
    with open(path) as f:
        exec(f.read(), globals())
    globals()['register'](table_env)


def settings_of(d):
    """(key, value) pairs of the request's settings: single-key maps, or --
    how the operator adds a savepoint path -- a string `SET key=value`."""
    for setting in d.get('sqlsettings', []):
        if isinstance(setting, str):
            text = setting.strip().rstrip(';')
            if text.upper().startswith('SET '):
                text = text[4:]
            key, _, value = text.partition('=')
            yield key.strip().strip("'`"), value.strip().strip("'")
            continue
        keys = list(setting.keys())
        key = keys[0]
        yield key, setting[key]


def message_of(error):
    """Flink's message: the outermost exception, without Py4J's call line,
    the Java stack trace or the causes, which repeat it."""
    lines = []
    for line in str(error).splitlines():
        if line.startswith(PY4J_PREFIX):
            continue
        if line.startswith('Caused by:'):
            break
        if line.strip() and not line.lstrip().startswith(STACK_PREFIXES):
            lines.append(line[2:] if line.startswith(': ') else line)
    return '\n'.join(lines[:MAX_MESSAGE_LINES])


def rejected(kind, index, text, error):
    return {'kind': kind, 'index': index, 'text': text,
            'message': message_of(error)}


def validate(d, udfdir='udf'):
    """None when Flink parses and plans the whole request, else the first
    rejected item and Flink's message (see `rejected`)."""
    table_env = create_table_env()
    for index, name in enumerate(udf_files(udfdir) if os.path.isdir(udfdir)
                                 else []):
        try:
            register_udf(table_env, os.path.join(udfdir, name))
        except Exception as error:
            return rejected('udf', index, name, error)
    for index, (key, value) in enumerate(settings_of(d)):
        try:
            table_env.get_config().set(key, value)
        except Exception as error:
            return rejected('setting', index, f'{key}={value}', error)
    for kind in ('tables', 'views'):
        for index, ddl in enumerate(d.get(kind, [])):
            try:
                table_env.execute_sql(ddl)
            except Exception as error:
                return rejected(kind[:-1], index, ddl, error)
    statements = d.get('sqlstatementset', [])
    statement_set = table_env.create_statement_set()
    for index, statement in enumerate(statements):
        try:
            statement_set.add_insert_sql(statement)
        except Exception as error:
            return rejected('statement', index, statement, error)
    if not statements:
        return None
    try:
        statement_set.explain()
    except Exception as error:
        # Planned together, the statements failed: find the one that fails on
        # its own, if any; otherwise it is the statement set as a whole.
        for index, statement in enumerate(statements):
            single = table_env.create_statement_set()
            single.add_insert_sql(statement)
            try:
                single.explain()
            except Exception as single_error:
                return rejected('statement', index, statement, single_error)
        return rejected('statementset', None, None, error)
    return None


def validate_files(files, udfdir):
    all_valid = True
    for path in files:
        with open(path) as f:
            d = json.load(f)
        problem = validate(d, udfdir)
        result = {'file': path, 'valid': problem is None}
        if problem is not None:
            all_valid = False
            result.update(problem)
        print(RESULT_PREFIX + json.dumps(result), flush=True)
    return all_valid


def deploy():
    with open('data/SQL-structures.json') as f:
        d = json.load(f)

    table_env = create_table_env()

    # Register udf models
    for name in udf_files('udf'):
        try:
            print(f"Executing {name}")
            register_udf(table_env, 'udf/' + name)
        except Exception as error:
            print(error)

    # Create SETs
    for key, value in settings_of(d):
        print(f'SET: {key}, {value}')
        table_env.get_config().set(key, value)

    # Create Tables
    for table in d.get('tables', []):
        table_env.execute_sql(table)

    # Create Views
    for view in d.get('views', []):
        table_env.execute_sql(view)

    # CREATE SQL Statement SET

    statement_set = table_env.create_statement_set()
    for statement in d["sqlstatementset"]:
        statement_set.add_insert_sql(statement)

    try:
        jobresult = statement_set.execute()
        print(f'JobID=[{jobresult.get_job_client().get_job_id()}]')
    except Exception as e:
        print(f'Error executing statement set: {e}')
        sys.exit(1)


def main(argv):
    if len(argv) > 1 and argv[1] == '--validate':
        args = argv[2:]
        udfdir = 'udf'
        if '--udf-dir' in args:
            position = args.index('--udf-dir')
            udfdir = args[position + 1]
            args = args[:position] + args[position + 2:]
        sys.exit(0 if validate_files(args, udfdir) else 1)
    deploy()


if __name__ == '__main__':
    main(sys.argv)
