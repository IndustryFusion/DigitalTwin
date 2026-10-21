"""NGSI-LD timestamps (`observedAt`): read as points in time, written one way.

The kms fixes the form `YYYY-MM-DDTHH:mm:ss.SSSZ` -- UTC, milliseconds -- the
one in which text order is time order. Data arrives in other ISO 8601 forms
too (`+02:00`, no milliseconds), so a timestamp is READ as a point in time,
never compared as text, and WRITTEN in the kms form.

"Latest" is the platform's rule: per (entity, attribute, datasetId) the
attribute view keeps the instance with the greatest COALESCE(observedAt, ts),
and an instance without observedAt -- or with one that does not parse -- is
stamped by the bridge with the time it arrives: now. So such an instance is
"now" here too, later than any past observation.
"""

import re
from datetime import datetime, timedelta, timezone

CANONICAL = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')
NOW = datetime.max.replace(tzinfo=timezone.utc)      # what an unstamped instance is
FRACTION = re.compile(r'(T\d{2}:\d{2}:\d{2})\.(\d+)')


def parse(text):
    """The point in time an observedAt says (UTC), or None if it says none."""
    value = str(text or '').strip()
    if not value or 'T' not in value:
        return None
    # Python 3.10 reads a fraction of 3 or 6 digits only; ISO 8601 allows any.
    value = FRACTION.sub(lambda m: f'{m[1]}.{m[2][:6].ljust(6, "0")}', value)
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None                     # no zone: no point in time
    return moment.astimezone(timezone.utc)


def canonical(moment):
    """A point in time in the kms form: 2024-02-28T13:52:35.000Z."""
    moment = moment.astimezone(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + f'{moment.microsecond // 1000:03d}Z'


def normalised(text):
    """`text` in the kms form, or None when it is no timestamp."""
    moment = parse(text)
    return canonical(moment) if moment is not None else None


def is_canonical(text):
    return bool(CANONICAL.match(str(text or '')))


def key(instance):
    """How late an instance is: its observedAt, or NOW without a usable one."""
    if not isinstance(instance, dict):
        return NOW
    return parse(instance.get('observedAt')) or NOW


def now():
    return canonical(datetime.now(timezone.utc))


def after(text):
    """One millisecond after `text`: "just after the latest"."""
    moment = parse(text)
    return canonical(moment + timedelta(milliseconds=1)) if moment else now()
