"""Provenance and tiers (architecture.md sections 2.3, 5.5).

Every element carries a TIER, and only `declared` compiles:

    observed   seen in example data
    proposed   the derivation engine suggests it
    declared   explicitly stated, or an accepted proposal

That distinction is the whole of "import and add, not import and infer": an
imported nodeset or a repeated observation is EVIDENCE, however authoritative it
feels, and evidence does not become a requirement without somebody saying so.

Provenance is stored out of band rather than as triples in knowledge.ttl or
shacl.ttl, because those two files are consumed by shacl2flink, by closure
computation and by Fuseki -- all of which would otherwise read tooling triples
as domain knowledge. A transitive closure over a graph polluted that way is a
defect waiting to happen.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum


class Tier(Enum):
    OBSERVED = 'observed'
    PROPOSED = 'proposed'
    DECLARED = 'declared'


@dataclass
class Origin:
    subject: str                 # the shape or ontology element
    kind: str                    # imported-shacl | imported-ontology | sdk-declaration | ...
    tier: str = Tier.DECLARED.value
    locator: str = ''            # file:line
    note: str = ''


@dataclass
class Provenance:
    origins: dict = field(default_factory=dict)

    def record(self, origin):
        self.origins[origin.subject] = origin

    def of(self, subject):
        return self.origins.get(str(subject))

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            for origin in sorted(self.origins.values(), key=lambda o: o.subject):
                handle.write(json.dumps(asdict(origin)) + '\n')

    @classmethod
    def load(cls, path):
        store = cls()
        if not os.path.exists(path):
            return store
        with open(path) as handle:
            for line in handle:
                if line.strip():
                    store.record(Origin(**json.loads(line)))
        return store

    def __len__(self):
        return len(self.origins)


def build_provenance(package):
    """Provenance for a freshly loaded package.

    Everything read from an artifact is `declared` -- somebody wrote it in a
    file. What makes the tier meaningful is that importers do NOT get to write
    at this tier: their output arrives as `proposed` and needs an explicit
    acceptance step, which is diff-visible.
    """
    from ..validate.shapes import node_shapes

    store = Provenance()
    shapes_index = package.index('shapes')
    for shape in node_shapes(package.shapes):
        store.record(Origin(
            subject=str(shape), kind='imported-shacl',
            tier=Tier.DECLARED.value,
            locator=shapes_index.locator(shape)))

    knowledge_index = package.index('knowledge')
    for subject in set(package.knowledge.subjects(None, None)):
        locator = knowledge_index.locator(subject)
        if locator:
            store.record(Origin(
                subject=str(subject), kind='imported-ontology',
                tier=Tier.DECLARED.value, locator=locator))
    return store
