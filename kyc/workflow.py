"""The case lifecycle as a table. fire() is the only place a status changes, so every change is
guarded, checked against who is asking, and written to the history.

    draft ──submit──▶ submitted ──start_review──▶ in_review ──approve──▶ approved
                          │                          │  ▲  └──reject──▶ rejected
                          └────request_info──────────┤  │
                                                     ▼  │ respond
                                              info_requested
"""
from dataclasses import dataclass
from typing import Callable

from django.db import transaction
from django.utils import timezone

from .engine import case_progress
from .models import Case, CaseEvent


class TransitionError(Exception):
    pass


@dataclass(frozen=True)
class Transition:
    sources: frozenset
    target: str
    actor: str  # 'applicant' or 'reviewer'
    label: str
    guard: Callable | None = None  # case -> error message, or None when the move is allowed


def _open_requests(case):
    return case.info_requests.filter(answered_at__isnull=True)


def incomplete(case):
    # ponytail: every guard recomputes case_progress, a few queries per page load;
    # cache it on the case for the request if it shows up in profiling.
    return None if case_progress(case).complete else 'Required information or documents are missing.'


def unanswered(case):
    return 'Every information request needs a reply first.' if _open_requests(case).exists() else None


def no_request_yet(case):
    return None if _open_requests(case).exists() else 'Add an information request first.'


def no_reason(case):
    return None if case.notes.exists() else 'Add an internal note with the reason first.'


def all_of(*guards):
    return lambda case: next((e for g in guards if (e := g(case))), None)


TRANSITIONS = {
    'submit': Transition(frozenset({'draft'}), 'submitted', 'applicant', 'Submit for review', incomplete),
    'start_review': Transition(frozenset({'submitted'}), 'in_review', 'reviewer', 'Start review'),
    'request_info': Transition(frozenset({'submitted', 'in_review'}), 'info_requested', 'reviewer',
                               'Send information request', no_request_yet),
    'respond': Transition(frozenset({'info_requested'}), 'in_review', 'applicant', 'Send answers back to review',
                          all_of(incomplete, unanswered)),
    'approve': Transition(frozenset({'in_review'}), 'approved', 'reviewer', 'Approve', all_of(incomplete, unanswered)),
    'reject': Transition(frozenset({'in_review'}), 'rejected', 'reviewer', 'Reject', no_reason),
}


def available(case, actor):
    """[(event, transition, why_blocked_or_None)] for what this actor could do now; the UI disables blocked ones."""
    return [(e, t, t.guard(case) if t.guard else None)
            for e, t in TRANSITIONS.items() if t.actor == actor and case.status in t.sources]


def fire(case, event, actor, who, ip=None):
    t = TRANSITIONS.get(event)
    if not t or t.actor != actor:
        raise TransitionError(f'“{event}” is not possible.')
    with transaction.atomic():
        # Lock the row and judge the move on the status as it is now, not as this request loaded it:
        # two reviewers pressing Approve and Reject at once must not both succeed.
        Case.objects.select_for_update().get(pk=case.pk)
        case.refresh_from_db()
        if case.status not in t.sources:
            raise TransitionError(f'“{event}” is not possible while the case is {case.status_label.lower()}.')
        if t.guard and (error := t.guard(case)):
            raise TransitionError(error)
        # ponytail: nothing is announced; both sides learn of a change by opening their
        # page. Send mail or enqueue a screening job from here.
        CaseEvent.objects.create(case=case, event=event, from_status=case.status, to_status=t.target, actor=who, ip=ip)
        case.status = t.target
        if event == 'submit':
            case.submitted_at = timezone.now()
        case.save(update_fields=['status', 'submitted_at', 'updated_at'])
