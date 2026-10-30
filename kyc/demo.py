"""Sample answers generated from a flow's own description, so any flow (including one added later) can be
filled in completely without hand-written fixtures. Used by the seed command and the tests."""
from datetime import date, timedelta

from django.core.files.base import ContentFile

from .engine import active, active_docs
from .flows import FLOWS
from .models import Case, Document


def sample(f):
    if f.type == 'consent':
        return True
    if f.type == 'multiselect':
        return [f.options[0][0]]
    if f.type in ('select', 'yesno'):
        return next(v for v, _ in f.options if v != f.flag_on)  # never a red-flag answer by default
    if f.type == 'email':
        return 'sample@example.com'
    if f.type == 'tel':
        return '+372 5555 5555'
    if f.type == 'date':
        return str(date.today() + timedelta(days=800 if f.rule == 'future' else -9000))
    if f.type == 'number':
        return max(f.min or 0, 1)
    return f'Sample {f.label.lower()}'[:80]


def complete_data(flow):
    """Answers for every visible field; repeat sections get two entries."""
    data = {}
    for s in flow.sections:
        built = []
        for _ in range(2 if s.repeat else 1):
            entry = {}
            for f in s.fields:  # in order: a follow-up field always comes after the field it depends on
                if active(f.show_if, data, entry):
                    entry[f.key] = sample(f)
            built.append(entry)
        data[s.key] = built if s.repeat else built[0]
    return data


def make_case(flow_key, complete=True):
    flow = FLOWS[flow_key]
    case = Case.objects.create(flow_key=flow_key, flow_version=flow.version, data=complete_data(flow) if complete else {})
    if complete:
        for d in active_docs(flow, case.data):
            if d.required:
                Document.objects.create(case=case, key=d.key, name=f'{d.key}.pdf',
                                        file=ContentFile(b'%PDF-1.4 demo document', name=f'{d.key}.pdf'))
    return case
