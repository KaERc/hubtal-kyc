"""Vocabulary for describing a KYC flow as data.

A flow is a module in kyc/flows/ that exports FLOW. Nothing else in the app
knows about Indonesia, EOR or any specific question: engine.py, the views and
the templates are driven entirely by these dataclasses. A new country or
process variant is a new module here, with no migration.

show_if is a tuple of (path, value) pairs; the item is shown when ANY pair
matches. path is "field" (same section / same repeated entry) or
"section.field" (anywhere in the case). A multiselect matches if it contains value.
"""
from dataclasses import dataclass

from django.utils.text import slugify

FIELD_TYPES = {'text', 'textarea', 'email', 'tel', 'date', 'number', 'select', 'multiselect', 'yesno', 'consent'}

YES_NO = (('yes', 'Yes'), ('no', 'No'))


def ch(*labels):
    """Options from plain labels; a label becomes its slug unless given as (value, label)."""
    return tuple(l if isinstance(l, tuple) else (slugify(l), l) for l in labels)


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: str = 'text'
    required: bool = True
    options: tuple = ()
    show_if: tuple = ()
    rule: str = ''          # date only: 'past' (birth date) or 'future' (expiry, start date)
    min: float | None = None  # number only
    max: float | None = None
    flag_on: str = ''       # answer the reviewer should see highlighted (e.g. "yes" to "ever bankrupt?")
    help: str = ''

    def __post_init__(self):
        assert self.type in FIELD_TYPES, self.type
        assert self.type not in ('select', 'multiselect', 'yesno') or self.options, self.key


def yes_no(key, label, flag_on='', **kw):
    return Field(key, label, 'yesno', options=YES_NO, flag_on=flag_on, **kw)


def with_other(field):
    """The form's "Others: ____" pattern: a select with an 'other' option plus a required free-text follow-up."""
    follow_up = Field(f'{field.key}_other', 'Please specify', show_if=((field.key, 'other'),))
    return (field, follow_up)


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    fields: tuple
    party: str = ''         # who is expected to fill it; display only (see README: one link per case)
    repeat: bool = False    # a list of entries (e.g. beneficial owners), at least one required
    intro: str = ''


@dataclass(frozen=True)
class Doc:
    key: str
    label: str
    required: bool = True
    show_if: tuple = ()
    help: str = ''


@dataclass(frozen=True)
class Flow:
    key: str
    version: str            # bump when a question or a declaration text changes; stored on every case
    country: str
    title: str
    subject: str            # "section.field" used as the case's display name
    sections: tuple
    docs: tuple = ()
