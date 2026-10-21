"""NGSI-LD semantics: the data views validation runs against."""

from .views import (DataView, ViewStats, build_view, collapse_updates,
                    normalise_empty_lists)
from .build import KINDS, attribute, coerce, entity, kind_for_shape, payload_key

__all__ = ['DataView', 'ViewStats', 'build_view', 'collapse_updates',
           'normalise_empty_lists', 'KINDS', 'attribute', 'coerce', 'entity',
           'kind_for_shape', 'payload_key']
