"""Normalised validation results.

The vocabulary here is SHACL's: focus node, path, source shape, severity,
message. alerts_bulk_view, constraint_trigger_table and Alerta severities are
platform vocabulary and appear nowhere in the SDK (architecture.md section 7.4).
"""

from dataclasses import dataclass, field
from enum import Enum


class Status(Enum):
    """Per-constraint outcome.

    CONFORMANT and NOT_APPLICABLE are populated by the applicable-set
    enumerator (H1), which is M2 work: a SHACL engine reports only violations,
    so conformance is the ABSENCE of a result and has to be established
    separately. Until then a report carries VIOLATED results only, and
    Report.complete says so rather than letting silence read as success.
    """
    CONFORMANT = 'conformant'
    VIOLATED = 'violated'
    NOT_APPLICABLE = 'not-applicable'
    NOT_EVALUATED = 'not-evaluated'


@dataclass(frozen=True)
class Result:
    resource: str            # the owning entity IRI
    attribute: str           # the attribute the constraint is on, or ''
    component: str           # e.g. MaxCountConstraintComponent
    shape: str               # the source shape, as a full IRI
    severity: str            # violation | warning | info (SHACL severities)
    status: Status = Status.VIOLATED
    message: str = ''
    view: str = 'current'
    shape_curie: str = ''    # prefixed shape name, for display and expectations

    @property
    def shape_name(self):
        """Short name, for display only.

        Never used as identity: the corpus carries two distinct CartridgeShape
        IRIs -- base_shacl and filter_shacl -- and collapsing them to one local
        name merges two shapes' verdicts into one, which would corrupt both the
        coverage report and the residue digest.
        """
        return self.shape.rsplit('/', 1)[-1].rsplit('#', 1)[-1]

    def key(self):
        """Identity used for comparison and, later, the residue digest.

        Deliberately free of blank node labels, which are not stable across
        runs.
        """
        return (self.resource, self.attribute, self.component, self.shape)


@dataclass
class Report:
    results: list = field(default_factory=list)
    view_stats: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    complete: bool = False   # True once every applicable constraint has a status (H1/V1)
    rule_iterations: int = 0

    @property
    def violations(self):
        return [r for r in self.results if r.status is Status.VIOLATED]

    def with_status(self, status):
        return [r for r in self.results if r.status is status]

    @property
    def conformant(self):
        return self.with_status(Status.CONFORMANT)

    @property
    def evaluated(self):
        """Every constraint that got a real verdict, either way."""
        return [r for r in self.results
                if r.status in (Status.VIOLATED, Status.CONFORMANT)]

    @property
    def conforms(self):
        return not self.violations

    def keys(self):
        return sorted(r.key() for r in self.violations)

    def by_resource(self, resource):
        return [r for r in self.results if r.resource == resource]

    def __len__(self):
        return len(self.results)
