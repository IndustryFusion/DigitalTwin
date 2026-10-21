"""The importer contract (architecture.md section 10).

**An importer emits at the `proposed` tier and never at `declared`.** That is
"import and add, not import and infer" made mechanical: an OPC UA nodeset or a
JSON Schema is evidence, however authoritative it feels, and evidence does not
become a validation requirement because a generator was confident.

So importer output goes to `.semforge/derived.ttl` and is not loaded by
validation. It reaches `shacl.ttl` only through `accept_proposal`, which is an
explicit act and a visible diff. The alternative -- generators writing straight
into the shapes file -- is how a model acquires constraints nobody chose.
"""

import os
from dataclasses import dataclass, field

from rdflib import Graph

from ..provenance import Origin, Provenance, Tier
from ..rdfio import add_property_constraint

DERIVED = os.path.join('.semforge', 'derived.ttl')


@dataclass
class Proposal:
    """Candidate semantics from one importer run."""
    source: str
    kind: str                              # imported-schema | imported-ontology | observed
    graph: Graph = field(default_factory=Graph)
    provenance: Provenance = field(default_factory=Provenance)
    notes: list = field(default_factory=list)

    def propose(self, subject, note=''):
        tier = Tier.OBSERVED.value if self.kind == 'observed' \
            else Tier.PROPOSED.value
        self.provenance.record(Origin(
            subject=str(subject), kind=self.kind, tier=tier,
            locator=self.source, note=note))

    @property
    def subjects(self):
        return sorted(self.provenance.origins)

    def __len__(self):
        return len(self.provenance)


def save_proposal(proposal, package_path):
    """Write to .semforge/, which validation does not read."""
    target = os.path.join(package_path, DERIVED)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    proposal.graph.serialize(destination=target, format='turtle')
    proposal.provenance.save(
        os.path.join(package_path, '.semforge', 'proposals.jsonl'))
    return target


def load_proposal(package_path):
    target = os.path.join(package_path, DERIVED)
    proposal = Proposal(source=target, kind='imported-schema')
    if os.path.exists(target):
        proposal.graph.parse(target, format='turtle')
    proposal.provenance = Provenance.load(
        os.path.join(package_path, '.semforge', 'proposals.jsonl'))
    return proposal


def accept_proposal(package, shape, attribute_path, parameters):
    """Promote one proposed constraint into the shapes file.

    Deliberately one constraint at a time and through the text-anchored writer,
    so the change is minimal, reviewable, and lands in the file the author
    reads -- not appended wholesale by a generator.
    """
    updated = add_property_constraint(
        package.sources['shapes'], shape, attribute_path, parameters)
    with open(package.sources['shapes'], 'w', encoding='utf-8') as handle:
        handle.write(updated)
    return package.sources['shapes']
