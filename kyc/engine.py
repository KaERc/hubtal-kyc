"""Interprets a Flow against a case's answers. No country- or form-specific code lives here.

Answer shape: data[section.key] is a dict {field: value}, or a list of such dicts for repeat sections.
Values: str for text-like, 'yes'/'no' for yesno, option value for select, list for multiselect, True for consent.
"""
import json
import re
from dataclasses import dataclass, field as dc_field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

PHONE = re.compile(r'^\+?[0-9 ()\-]{6,20}$')
MAX_TEXT = 4000


def blank(value):
    """Not `value in (...)`: that would treat the number 0 as False, i.e. as an unanswered question."""
    return value is None or value is False or value == '' or value == []


def lookup(path, data, scope):
    """Value for a show_if path: "field" in the current section/entry (scope), "section.field" anywhere."""
    if '.' not in path:
        return (scope or {}).get(path)
    section, key = path.split('.', 1)
    entry = data.get(section)
    return entry.get(key) if isinstance(entry, dict) else None


def active(cond, data, scope=None):
    """True when there is no condition, or any (path, value) pair matches."""
    if not cond:
        return True
    for path, expected in cond:
        got = lookup(path, data, scope)
        if got == expected or (isinstance(got, list) and expected in got):
            return True
    return False


def entries(section, data):
    """Always a list of dicts: one for a plain section, N for a repeat section."""
    raw = data.get(section.key)
    if section.repeat:
        return raw if isinstance(raw, list) else []
    return [raw if isinstance(raw, dict) else {}]


def visible_fields(section, scope, data):
    return [f for f in section.fields if active(f.show_if, data, scope)]


# ---- parsing and validation -------------------------------------------------

def clean(f, raw):
    """(value, error) for one raw form value. An empty answer is never an error: missing is reported by progress()."""
    if f.type == 'consent':
        return (True, None) if raw else (None, None)
    if f.type == 'multiselect':
        picked = [v for v in raw or [] if v]
        bad = set(picked) - {v for v, _ in f.options}
        return (None, 'Choose from the list.') if bad else (picked or None, None)
    raw = (raw or '').strip()
    if not raw:
        return None, None
    if len(raw) > MAX_TEXT:
        return None, 'Too long.'
    if f.type in ('select', 'yesno'):
        return (raw, None) if raw in {v for v, _ in f.options} else (None, 'Choose from the list.')
    if f.type == 'email':
        try:
            validate_email(raw)
        except ValidationError:
            return None, 'Enter a valid email address.'
    elif f.type == 'tel' and not PHONE.match(raw):
        return None, 'Enter a valid phone number, for example +372 5555 5555.'
    elif f.type == 'date':
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            return None, 'Enter a valid date.'
        if f.rule == 'past' and d >= date.today():
            return None, 'The date must be in the past.'
        if f.rule == 'future' and d <= date.today():
            return None, 'The date must be in the future.'
    elif f.type == 'number':
        try:
            n = Decimal(raw)
        except InvalidOperation:
            return None, 'Enter a number.'
        if not n.is_finite():
            return None, 'Enter a number.'
        if (f.min is not None and n < f.min) or (f.max is not None and n > f.max):
            return None, f'Enter a number between {f.min if f.min is not None else "−∞"} and {f.max if f.max is not None else "∞"}.'
        return (int(n) if n == n.to_integral() else float(n)), None
    return raw, None


def parse_entry(section, post, prefix=''):
    """Read one entry from POST. Fields hidden by show_if are dropped, so stale answers never linger.
    Returns (values, errors); an invalid value is not stored and carries an error."""
    values, errors = {}, {}
    for f in section.fields:
        raw = post.getlist(prefix + f.key) if f.type == 'multiselect' else post.get(prefix + f.key)
        values[f.key], err = clean(f, raw)
        if err:
            errors[f.key] = err
    for f in section.fields:
        if not active(f.show_if, {}, values):
            values.pop(f.key)
            errors.pop(f.key, None)
    return {k: v for k, v in values.items() if not blank(v)}, errors


# ---- binding values to the form -----------------------------------------------

def bind(section, entry, errors=None, prefix=''):
    """Per-field render model for the templates: the field, its input name, current value, error, and visibility."""
    out = []
    for f in section.fields:
        out.append({
            'f': f,
            'name': prefix + f.key,
            'value': entry.get(f.key),
            'error': (errors or {}).get(f.key),
            'show': active(f.show_if, {}, entry),
            'cond': json.dumps(f.show_if),
            'prefix': prefix,
        })
    return out


# ---- completeness ---------------------------------------------------------------

@dataclass
class SectionProgress:
    section: object
    done: int = 0
    total: int = 0
    missing: list = dc_field(default_factory=list)

    @property
    def complete(self):
        return not self.missing


@dataclass
class Progress:
    sections: list
    docs_missing: list
    docs_total: int

    @property
    def missing(self):
        return [m for s in self.sections for m in s.missing] + [f'Document: {d.label}' for d in self.docs_missing]

    @property
    def complete(self):
        return not self.missing

    @property
    def done(self):
        return sum(s.done for s in self.sections) + self.docs_total - len(self.docs_missing)

    @property
    def total(self):
        return sum(s.total for s in self.sections) + self.docs_total

    @property
    def percent(self):
        return round(100 * self.done / self.total) if self.total else 100


def progress(flow, data, uploaded_keys):
    sections = []
    for s in flow.sections:
        sp = SectionProgress(s)
        items = entries(s, data)
        if s.repeat and not items:
            sp.total, sp.missing = 1, [f'{s.title}: add at least one entry']
        for i, entry in enumerate(items, 1):
            where = f'{s.title} #{i}' if s.repeat else s.title
            for f in visible_fields(s, entry, data):
                if not f.required:
                    continue
                sp.total += 1
                if blank(entry.get(f.key)):
                    sp.missing.append(f'{where}: {f.label if f.type != "consent" else "confirm the declaration"}')
                else:
                    sp.done += 1
        sections.append(sp)
    docs = [d for d in flow.docs if d.required and active(d.show_if, data)]
    return Progress(sections, [d for d in docs if d.key not in uploaded_keys], len(docs))


def case_progress(case):
    return progress(case.flow, case.data, {d.key for d in case.documents.all()})


def active_docs(flow, data):
    return [d for d in flow.docs if active(d.show_if, data)]


# ---- what the reviewer sees ------------------------------------------------------

def show(f, value):
    if value is None:
        return '—'
    labels = dict(f.options)
    if isinstance(value, list):
        return ', '.join(labels.get(v, v) for v in value)
    if value is True:
        return 'Confirmed'
    return labels.get(value, value)


def flagged(f, value):
    return bool(f.flag_on) and (f.flag_on in value if isinstance(value, list) else value == f.flag_on)


def answers(case):
    """[(section, [[(label, text, flagged), ...] per entry])] with only the visible fields."""
    out = []
    for s in case.flow.sections:
        rows = [[(f.label, show(f, e.get(f.key)), flagged(f, e.get(f.key))) for f in visible_fields(s, e, case.data)]
                for e in entries(s, case.data)]
        out.append((s, rows))
    return out
