from pyflink.table import TableEnvironment, EnvironmentSettings
import json
import pathlib
import os
import sys


JARDIR = '/opt/gateway/jars'

with open('data/SQL-structures.json') as f:
    d = json.load(f)

    env_settings = EnvironmentSettings.in_streaming_mode()
    table_env = TableEnvironment.create(env_settings)

    # Get all jars from /opt/gateway/jar
    jars = ';'.join(list(map(lambda x: "file://"+str(x),
                             pathlib.Path(JARDIR).glob('*.jar'))))

    table_env.get_config().set("pipeline.classpaths", jars)

    # Register udf models
    for file in os.scandir('udf'):
        if file.name.endswith('.py') and file.name != '__init__.py':
            try:
                print(f"Executing {file.name}")
                f = open('udf/' + file.name).read()
                exec(f)
                register(table_env)  # noqa: F821
            except Exception as error:
                print(error)

    # Create SETs
    if 'sqlsettings' in d:
        sets = d['sqlsettings']
        for set in sets:
            keys = list(set.keys())
            key = keys[0]
            value = set[key]
            print(f'SET: {key}, {value}')
            table_env.get_config().set(key, value)

    # Create Tables
    if 'tables' in d:
        tables = d['tables']
        for table in tables:
            table_env.execute_sql(table)

    # Create Views
    if 'views' in d:
        views = d['views']
        for view in views:
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
