"""Loading and saving a semantic package."""

from .discover import describe, explain, find, is_package, root
from .loader import Package, load
from .registry import (Dependency, assemble_knowledge, dependencies_from_config,
                       digest, resolve)

__all__ = ['Package', 'load', 'describe', 'explain', 'find',
           'is_package', 'root', 'Dependency', 'assemble_knowledge',
           'dependencies_from_config', 'digest', 'resolve']


# Every parse of a JSON-LD document goes through rdflib's context fetch; this
# makes it fetch a remote context once per machine instead of once per parse.
from .context import install_context_cache  # noqa: E402

install_context_cache()
