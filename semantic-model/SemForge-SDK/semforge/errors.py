"""Diagnostics and the error model (architecture.md section 13).

Every diagnostic carries a stable code, a category and a severity. Categories
are what let a caller treat a capability problem differently from a data
violation -- CI needs that distinction, and a bare exception cannot carry it.
"""

from dataclasses import dataclass, field


class SemForgeError(Exception):
    """Base for every error the SDK raises deliberately."""


class PackageError(SemForgeError):
    """The package is malformed: missing artifact, unreadable, unresolvable."""


class CapabilityError(SemForgeError):
    """The package asks for something a target profile cannot express."""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    category: str          # package | capability | validation | consistency | divergence | internal
    severity: str          # error | warning | info
    message: str
    locator: str = ''      # file, or file:line when known
    subject: str = ''      # the shape or constraint the diagnostic is about

    def __str__(self):
        where = f' [{self.locator}]' if self.locator else ''
        return f'{self.severity.upper()} {self.code}: {self.message}{where}'


@dataclass
class DiagnosticSet:
    """Collected diagnostics.

    fail_loud() reports EVERY problem at once rather than the first. That is
    invariant C1 (architecture.md section 9.2): a build that stops at the first
    bad shape makes fixing a package an iterative guessing game.
    """
    items: list = field(default_factory=list)

    def add(self, diagnostic):
        self.items.append(diagnostic)

    @property
    def errors(self):
        return [d for d in self.items if d.severity == 'error']

    def fail_loud(self, headline):
        if not self.errors:
            return
        body = '\n'.join(f'  - {d}' for d in self.errors)
        raise CapabilityError(f'{headline}\n{body}')

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)
