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
"""
Compose the SQL Gateway requests of the statement sets in rendered manifests
(openspec gh-955-flink-sql-validation), with the operator's own code -- the
requests the operator would send for those resources -- so that they can be
validated before anything is deployed.

    python3 compose_requests.py RENDERED.yaml... OUTDIR [--namespace NS]

reads the manifests of all RENDERED files (a statement set's tables may come
from another chart, e.g. the core tables of sql-core) and writes
OUTDIR/requests/<namespace>_<name>.json for every BeamSqlStatementSet and
OUTDIR/udf/<filename>_<version>.py for every FlinkPythonUdf (the newest
version of each, as the SQL Gateway uses them). A statement set that cannot
be composed -- a missing table, view or ConfigMap -- is reported and makes it
exit with 1.
"""
import json
import logging
import os
import re
import sys

import kopf
import yaml

import beamsqlstatementsetoperator as operator


class Resource(dict):
    """A manifest with the attribute access the operator's code uses on kopf
    bodies (`body.spec.get(...)`)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def resource(value):
    """`value` with Resource for every mapping in it."""
    if isinstance(value, dict):
        return Resource({k: resource(v) for k, v in value.items()})
    if isinstance(value, list):
        return [resource(v) for v in value]
    return value


def safe(name):
    """A file name for a namespace or resource name."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(name))


def documents(paths):
    """The manifests of all files."""
    for path in paths:
        with open(path, encoding='utf-8') as stream:
            yield from yaml.safe_load_all(stream)


def load(paths, namespace):
    """The indexes kopf keeps -- tables, views, ConfigMaps by (namespace,
    name) -- the statement sets and the UDFs of the rendered manifests."""
    tables, views, configmaps, statementsets, udfs = {}, {}, {}, [], []
    for document in documents(paths):
        if not isinstance(document, dict) or 'kind' not in document:
            continue
        body = resource(document)
        body.setdefault('metadata', Resource())
        body['metadata'].setdefault('namespace', namespace)
        body.setdefault('status', Resource())
        key = (body['metadata']['namespace'], body['metadata'].get('name'))
        kind = str(body['kind']).lower()
        if kind == 'beamsqltable':
            tables[key] = [body]
        elif kind == 'beamsqlview':
            views[key] = [body]
        elif kind == 'configmap':
            configmaps[key] = [body]
        elif kind == 'beamsqlstatementset':
            statementsets.append(body)
        elif kind == 'flinkpythonudf':
            udfs.append(body)
    return tables, views, configmaps, statementsets, udfs


def newest_udfs(udfs):
    """{file name: source} with the newest version of each UDF, as the SQL
    Gateway picks them (the last of the sorted file names wins)."""
    files = {}
    for udf in udfs:
        spec = udf.get('spec') or {}
        files[f"{spec.get('filename')}_{spec.get('version')}.py"] = spec.get('class') or ''
    newest = {}
    for name in sorted(files):
        newest[name.rsplit('_v', 1)[0]] = name
    return {name: files[name] for name in newest.values()}


def parse_args(argv):
    """([rendered manifests], output directory, default namespace)"""
    args = argv[1:]
    namespace = 'iff'
    if '--namespace' in args:
        position = args.index('--namespace')
        namespace = args[position + 1]
        args = args[:position] + args[position + 2:]
    if len(args) < 2:
        raise SystemExit('usage: compose_requests.py RENDERED.yaml... OUTDIR [--namespace NS]')
    return args[:-1], args[-1], namespace


def write_udfs(udfs, outdir):
    """OUTDIR/udf/<filename>_<version>.py, the newest version of each"""
    os.makedirs(os.path.join(outdir, 'udf'), exist_ok=True)
    for filename, source in newest_udfs(udfs).items():
        with open(os.path.join(outdir, 'udf', safe(filename)), 'w', encoding='utf-8') as file:
            file.write(source)


def write_request(body, indexes, outdir, logger):
    """OUTDIR/requests/<namespace>_<name>.json; False if it cannot be composed"""
    tables, views, configmaps = indexes
    namespace = body['metadata']['namespace']
    name = body['spec'].get('name') or body['metadata'].get('name')
    try:
        request = operator.compose_statementset(tables, views, configmaps, body['spec'],
                                                body, namespace, name, logger)
    except (kopf.TemporaryError, kopf.PermanentError) as err:
        print(f"Could not compose {namespace}/{name}: {err}", file=sys.stderr)
        return False
    target = os.path.join(outdir, 'requests', f"{safe(namespace)}_{safe(name)}.json")
    with open(target, 'w', encoding='utf-8') as file:
        json.dump(request, file, indent=1)
    print(f"Composed {namespace}/{name}: {len(request.get('tables', []))} tables, "
          f"{len(request.get('views', []))} views, "
          f"{len(request.get('sqlstatementset', []))} statements -> {target}")
    return True


def main(argv):
    """Write the requests and UDFs; 0 when every statement set composed."""
    rendered, outdir, namespace = parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger('compose_requests')
    tables, views, configmaps, statementsets, udfs = load(rendered, namespace)
    write_udfs(udfs, outdir)
    os.makedirs(os.path.join(outdir, 'requests'), exist_ok=True)
    composed = [write_request(body, (tables, views, configmaps), outdir, logger)
                for body in statementsets]
    if not statementsets:
        print(f"No BeamSqlStatementSet in {' '.join(rendered)}", file=sys.stderr)
        return 1
    return 0 if all(composed) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
