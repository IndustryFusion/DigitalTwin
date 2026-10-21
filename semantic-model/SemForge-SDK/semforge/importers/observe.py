"""Structure observed in example data (manifest section 6).

Observation is the weakest tier and the one most likely to be mistaken for
knowledge. This reports what the examples CONTAIN -- types, attributes, the
datatypes seen, how often each appears -- and proposes nothing at all.

The project explicitly rejects the assumption that repeated observation defines
a requirement. Four examples that all carry a serial number are four examples,
not a cardinality constraint; whether it is required is a decision, and the
observation is the evidence for making it.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF

from ..validate.normalise import local
from .base import Proposal

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
VALUE_PATHS = {NGSILD + p for p in ('hasValue', 'hasObject', 'hasValueList')}


@dataclass
class Observation:
    entity_type: str
    attribute: str
    count: int = 0
    entities: set = field(default_factory=set)
    datatypes: set = field(default_factory=set)
    kinds: set = field(default_factory=set)

    @property
    def seen_on_every_entity(self):
        return False    # never inferred here; the caller compares with totals


def observe_examples(graphs, source='examples'):
    """What the example data contains. Returns (observations, Proposal).

    The Proposal is at the `observed` tier and holds no shapes: there is
    nothing to accept, because nothing has been claimed.
    """
    observations = {}
    totals = defaultdict(set)

    for graph in graphs:
        types = {}
        for subject, cls in graph.subject_objects(RDF.type):
            if isinstance(subject, URIRef):
                types.setdefault(subject, set()).add(local(cls))
        for entity, names in types.items():
            for name in names:
                totals[name].add(str(entity))

        for entity, predicate, node in graph:
            if not isinstance(entity, URIRef) or not isinstance(node, BNode):
                continue
            for name in types.get(entity, {'?'}):
                key = (name, local(predicate))
                record = observations.setdefault(key, Observation(*key))
                record.count += 1
                record.entities.add(str(entity))
                for value_path in VALUE_PATHS:
                    for value in graph.objects(node, URIRef(value_path)):
                        record.kinds.add(local(value_path))
                        if isinstance(value, Literal):
                            record.datatypes.add(
                                local(value.datatype) if value.datatype else 'plain')
                        elif isinstance(value, URIRef):
                            record.datatypes.add('IRI')

    proposal = Proposal(source=source, kind='observed')
    for (entity_type, attribute), record in sorted(observations.items()):
        proposal.propose(
            f'{entity_type}.{attribute}',
            f'seen on {len(record.entities)} of {len(totals[entity_type])} '
            f'{entity_type} instance(s); values: '
            f'{", ".join(sorted(record.datatypes)) or "none"}')
    return observations, proposal
