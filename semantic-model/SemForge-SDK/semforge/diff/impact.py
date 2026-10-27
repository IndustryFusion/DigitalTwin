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

"""What a model change did to the examples.

The model layer says a constraint was weakened. This says which example stopped
failing because of it -- which is what turns a diff into a regression report:

    Semantic regression detected

    Constraint changed:
      MachineShape/hasState/MinCountConstraintComponent   (1 -> 0)

    Affected example:
      model-instance.jsonld

    Expected: INVALID because MachineShape/hasState/MinCount
    Actual:   VALID

It is also the only way to settle a change the lattice cannot classify. A
changed SPARQL body is `impact-unknown` in the model layer; running the examples
under both versions says what it actually did.
"""

from dataclasses import dataclass, field

from ..expect.runner import constraint_ref
from ..validate.orchestrator import validate_graphs


@dataclass
class ImpactedExample:
    path: str
    started_failing: list = field(default_factory=list)
    stopped_failing: list = field(default_factory=list)

    @property
    def changed(self):
        return bool(self.started_failing or self.stopped_failing)


@dataclass
class RegressionReport:
    changes: list = field(default_factory=list)
    impacted: list = field(default_factory=list)

    @property
    def has_impact(self):
        return any(example.changed for example in self.impacted)


def _violation_refs(report):
    return {(r.resource, constraint_ref(r)) for r in report.violations}


def regression_report(before, after, examples, changes=None):
    """Compare two package states over the same examples.

    `before` and `after` are (data_graph, shapes_graph, knowledge_graph)
    triples; `examples` is [(name, data_graph)] -- or empty, in which case each
    state's own model is the single example.
    """
    from .model import semantic_diff

    report = RegressionReport(
        changes=changes if changes is not None else semantic_diff(before[1], after[1]))

    for name, data in examples:
        old = validate_graphs(data, before[1], before[2], strict=False)
        new = validate_graphs(data, after[1], after[2], strict=False)
        old_refs, new_refs = _violation_refs(old), _violation_refs(new)
        report.impacted.append(ImpactedExample(
            path=name,
            started_failing=sorted(new_refs - old_refs),
            stopped_failing=sorted(old_refs - new_refs)))
    return report


def format_regression(report):
    lines = []
    for example in report.impacted:
        if not example.changed:
            continue
        lines.append(f'  {example.path}')
        for resource, ref in example.stopped_failing:
            lines.append(f'      no longer fails  {ref}  on {resource}')
        for resource, ref in example.started_failing:
            lines.append(f'      now fails        {ref}  on {resource}')
    return lines
