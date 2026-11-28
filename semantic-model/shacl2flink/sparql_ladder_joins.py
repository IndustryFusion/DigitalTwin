#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
The Join operators of SPARQL_ENGINE=ladder (alpha) in a Flink job's plan.

    sparql_ladder_joins.py <plan.json>    (Flink REST /jobs/<id>/plan)

Prints their number. The build writes how many there must be into
output/sparql-ladder-joins.txt; more means the planner copied a level, which
doubles the joins with every level (see Functions.Barrier). A join is the
ladder's when it selects a column only the ladder's SQL has: the job also
holds the joins of the other validations. Standard library only: it runs
where the end-to-end tests run.
"""
import json
import re
import sys

# columns of the ladder's CTEs (lib/sparql_ladder_sql.py) no other statement selects
LADDER_COLUMNS = {'node', 'k', 'b', 'cls', 'msg', 'keyspec', 'flt', 'lvl', 'grp', 'suffix'}
JOIN = re.compile(r'Join\(joinType=\[[^\]]*\],.*?select=\[([^\]]*)\]')


def ladder_joins(plan):
    """The Join operators of the ladder in a plan, as their select lists."""
    found = []
    for node in plan['plan']['nodes']:
        for match in JOIN.finditer(node.get('description', '')):
            columns = {column.strip() for column in match[1].split(',')}
            if columns & LADDER_COLUMNS:
                found.append(sorted(columns))
    return found


def main(path):
    with open(path) as handle:
        print(len(ladder_joins(json.load(handle))))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
