"""Expectations, residue and coverage."""

from .digest import canonical_lines, residue_digest
from .store import (Expectations, Example, compose, discover,
                    load_expectations, save_expectations)
from .runner import CoverageEntry, TestOutcome, coverage, run_tests

__all__ = ['canonical_lines', 'residue_digest', 'Expectations', 'Example', 'compose', 'discover',
           'load_expectations', 'save_expectations', 'CoverageEntry',
           'TestOutcome', 'coverage', 'run_tests']
