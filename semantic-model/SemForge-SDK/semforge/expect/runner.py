"""Running examples against expectations, and reporting coverage.

Two separate questions, deliberately not merged:

* Did each example behave as declared? -- assertions and residue.
* Is each constraint actually exercised anywhere? -- coverage (H6).

The second exists because the first cannot answer it. A SPARQL constraint whose
body can never match returns an empty result set, which is byte-for-byte what a
satisfied constraint returns, so per-example status classifies it CONFORMANT on
every example forever. Only a negative example that asserts the constraint FIRES
proves it is alive. A positive example proves nothing about liveness.

And even both sides can be defeated together: a negative example written to make
a shape fire will carry whatever type the shape's author assumed, so a shape
targeting the wrong class and an example typed to match it agree with each other
and both pass. Coverage narrows the gap; it does not close it. What it
guarantees is that a constraint is not validating NOTHING.
"""

from dataclasses import dataclass, field

from ..validate.results import Status


def constraint_ref(result):
    """A readable reference to the constraint a result came from.

    Structural for now -- shape, attribute and component. Section 5.4 of the
    architecture calls for a DECLARED, frozen semforge:id instead, because a
    structural reference changes whenever the path changes, which is exactly
    the rename a regression report exists to explain. Until those annotations
    exist this is what expectations name.
    """
    shape = result.shape_curie or result.shape.rsplit('/', 1)[-1].rsplit('#', 1)[-1]
    return f'{shape}/{result.attribute}/{result.component}' if result.attribute \
        else f'{shape}/{result.component}'


@dataclass
class TestOutcome:
    example: str
    passed: bool = True
    failures: list = field(default_factory=list)
    residue: str = ''
    residue_changed: bool = False

    def fail(self, message):
        self.passed = False
        self.failures.append(message)


@dataclass
class CoverageEntry:
    constraint: str
    firing_examples: list = field(default_factory=list)
    conforming_examples: list = field(default_factory=list)

    @property
    def has_firing(self):
        return bool(self.firing_examples)

    @property
    def has_conforming(self):
        return bool(self.conforming_examples)

    @property
    def status(self):
        if not self.has_firing:
            # Never seen to fire. Either it lacks a negative example, or it
            # cannot fire at all -- and those two look identical from here,
            # which is precisely why this is reported rather than inferred.
            return 'no-firing-example'
        if not self.has_conforming:
            return 'no-conforming-example'
        return 'two-sided'


def evaluate(example, report, known=None):
    """Check one example's report against its declared expectations.

    `known` is every constraint a shape declares (sanity.known_constraints).
    With it, an assert naming a constraint that does not exist says so --
    "did not fire" sends the reader looking for a data problem that is not
    there.
    """
    outcome = TestOutcome(example=example.path)

    violations = report.violations
    if example.expect == 'valid' and violations:
        outcome.fail(f'expected valid, got {len(violations)} violation(s)')
    if example.expect == 'invalid' and not violations:
        outcome.fail('expected invalid, but everything conformed')

    fired = {(r.resource, constraint_ref(r)) for r in violations}
    for assertion in example.asserts:
        wanted = (assertion.get('resource', ''), assertion['constraint'])
        if wanted not in fired:
            if known is not None and assertion['constraint'] not in known:
                outcome.fail(
                    f'asserts {assertion["constraint"]}, a constraint no shape '
                    f'declares -- it can never fire. Was it renamed or '
                    f'removed? `semforge check` lists every such assert.')
                continue
            outcome.fail(
                f'asserted {assertion["constraint"]} to fire'
                + (f' on {wanted[0]}' if wanted[0] else '')
                + ', but it did not')

    asserted = example.asserted_keys()
    residue_results = [r for r in report.results
                       if (r.resource, constraint_ref(r)) not in asserted]

    from .digest import residue_digest
    outcome.residue = residue_digest(residue_results)
    if example.requires_full_conformance and violations:
        outcome.fail('conformance: full requires an empty residue of violations')
    if example.residue and example.residue != outcome.residue:
        outcome.residue_changed = True
        outcome.fail(
            'residue changed. A constraint that this example does not assert '
            'now behaves differently -- review and `semforge accept` if intended')
    return outcome


def run_tests(examples_and_reports, known=None):
    """[(Example, Report)] -> [TestOutcome]."""
    return [evaluate(example, report, known)
            for example, report in examples_and_reports]


def coverage(examples_and_reports):
    """Two-sided coverage per constraint, across every example."""
    entries = {}
    for example, report in examples_and_reports:
        for result in report.results:
            if result.status not in (Status.VIOLATED, Status.CONFORMANT):
                continue
            ref = constraint_ref(result)
            entry = entries.setdefault(ref, CoverageEntry(constraint=ref))
            target = (entry.firing_examples if result.status is Status.VIOLATED
                      else entry.conforming_examples)
            if example.path not in target:
                target.append(example.path)
    return [entries[key] for key in sorted(entries)]
