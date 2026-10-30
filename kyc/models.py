import secrets

from django.conf import settings
from django.db import models

from .flows import FLOWS

STATUS_LABELS = {
    'draft': 'Draft',
    'submitted': 'Submitted',
    'in_review': 'In review',
    'info_requested': 'Information requested',
    'approved': 'Approved',
    'rejected': 'Rejected',
}


def new_token():
    return secrets.token_urlsafe(16)


class Case(models.Model):
    """One KYC case. Answers live in `data` as {section: {field: value}} (a list of those for repeated sections):
    the shape of the answers is owned by the flow definition, so a new flow needs no migration."""
    # ponytail: the link is the only credential, and an EOR case has one link for
    # both parties; emailed, expiring links per party before real applicants use it.
    token = models.CharField(max_length=32, unique=True, default=new_token)
    flow_key = models.CharField(max_length=40)
    # ponytail: only the version string is stored, not the flow definition it names;
    # snapshot the answers and the declaration wording at submit so a later flow edit
    # cannot change what was agreed.
    flow_version = models.CharField(max_length=20)  # pins the exact declaration texts the applicant agreed to
    status = models.CharField(max_length=20, default='draft', choices=tuple(STATUS_LABELS.items()))
    # ponytail: answers as one JSON document break first normal form (nested lists
    # such as owners, values the database cannot type, constrain or index) and hide
    # their dependencies from it; normalise persons, owners and documents into typed
    # tables, or move to PostgreSQL JSONB with indexes, once screening or reporting
    # must search across cases.
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    @property
    def flow(self):
        return FLOWS[self.flow_key]

    @property
    def editable(self):
        return self.status in ('draft', 'info_requested')

    @property
    def status_label(self):
        return STATUS_LABELS[self.status]

    @property
    def subject(self):
        section, key = self.flow.subject.split('.')
        return self.data.get(section, {}).get(key) or '(unnamed)'

    def __str__(self):
        return f'{self.flow_key} #{self.pk} {self.subject}'


class Document(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='documents')
    key = models.CharField(max_length=40)  # a Doc.key from the flow
    # ponytail: local disk, unencrypted and not virus-scanned, and Django reads the
    # whole upload before the 10 MB check; private object storage with scanning and a
    # size limit at the proxy for production.
    file = models.FileField(upload_to='cases/%Y/%m/')
    name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class InfoRequest(models.Model):
    """The reviewer asks the applicant for something; the applicant's reply closes it."""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='info_requests')
    section = models.CharField(max_length=40, blank=True)  # a Section.key, blank = general
    message = models.TextField()
    reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    @property
    def open(self):
        return self.answered_at is None

    @property
    def section_title(self):
        return next((s.title for s in self.case.flow.sections if s.key == self.section), '')


class ReviewNote(models.Model):
    """Internal only: never shown to the applicant."""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class CaseEvent(models.Model):
    """Written by workflow.fire only: who moved the case from where to where, when, from which IP."""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='events')
    event = models.CharField(max_length=20)
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    actor = models.CharField(max_length=150)
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)
