import shutil
import tempfile

from django.http import QueryDict
from django.test import TestCase, override_settings

from . import demo, engine, workflow
from .flows import FLOWS
from .models import InfoRequest

MEDIA = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def post(**fields):
    q = QueryDict(mutable=True)
    for k, v in fields.items():
        q.setlist(k, v if isinstance(v, list) else [v])
    return q


def section(flow_key, key):
    return next(s for s in FLOWS[flow_key].sections if s.key == key)


def progress_of(flow, data):
    return engine.progress(flow, data, {d.key for d in engine.active_docs(flow, data)})


class EngineTests(TestCase):
    def test_other_follow_up_exists_only_when_other_is_chosen(self):
        s = section('id-non-eor', 'stay')
        values, _ = engine.parse_entry(s, post(purpose='work', purpose_other='left over'))
        self.assertEqual(values, {'purpose': 'work'})
        values, _ = engine.parse_entry(s, post(purpose='other', purpose_other='sabbatical'))
        self.assertEqual(values, {'purpose': 'other', 'purpose_other': 'sabbatical'})

    def test_invalid_values_are_reported_and_not_stored(self):
        s = section('id-non-eor', 'applicant')
        values, errors = engine.parse_entry(s, post(
            email='nope', phone='abc', date_of_birth='2999-01-01', passport_expiry='2000-01-01', full_name='A B'))
        self.assertEqual(values, {'full_name': 'A B'})
        self.assertEqual(set(errors), {'email', 'phone', 'date_of_birth', 'passport_expiry'})

    def test_zero_percent_is_an_answer_and_over_100_is_not(self):
        s = section('id-eor', 'ubos')
        values, errors = engine.parse_entry(s, post(ownership_pct='0'))
        self.assertEqual((values, errors), ({'ownership_pct': 0}, {}))
        _, errors = engine.parse_entry(s, post(ownership_pct='101'))
        self.assertIn('ownership_pct', errors)

    def test_every_registered_flow_can_be_completed(self):
        for flow in FLOWS.values():
            p = progress_of(flow, demo.complete_data(flow))
            self.assertEqual((p.missing, p.percent), ([], 100), flow.key)

    def test_empty_case_lists_what_is_missing(self):
        p = engine.progress(FLOWS['id-non-eor'], {}, set())
        self.assertFalse(p.complete)
        self.assertIn('Applicant information: Full name (as in passport)', p.missing)
        self.assertIn('Document: Passport copy (photo page)', p.missing)
        self.assertNotIn('Document: Evidence of source of wealth', p.missing)  # optional

    def test_repeat_section_needs_at_least_one_entry(self):
        data = demo.complete_data(FLOWS['id-eor'])
        data['ubos'] = []
        self.assertIn('Ultimate beneficial owners: add at least one entry', progress_of(FLOWS['id-eor'], data).missing)

    def test_document_required_only_when_its_condition_holds(self):
        flow = FLOWS['id-eor']
        data = demo.complete_data(flow)
        data['background']['certification'] = 'no'
        self.assertEqual([d.key for d in engine.active_docs(flow, data)].count('certificates'), 0)
        data['background']['certification'] = 'yes'
        self.assertIn('certificates', [d.key for d in engine.active_docs(flow, data)])

    def test_red_flags_are_detected(self):
        bankrupt = next(f for f in section('id-eor', 'compliance').fields if f.key == 'bankrupt')
        self.assertTrue(engine.flagged(bankrupt, 'yes'))
        self.assertFalse(engine.flagged(bankrupt, 'no'))
        method = next(f for f in section('id-non-eor', 'wealth').fields if f.key == 'receiving_method')
        self.assertTrue(engine.flagged(method, ['bank-transfer', 'third-party-transfer']))


@override_settings(MEDIA_ROOT=MEDIA)
class WorkflowTests(TestCase):
    def test_incomplete_case_cannot_be_submitted(self):
        case = demo.make_case('id-non-eor', complete=False)
        with self.assertRaises(workflow.TransitionError):
            workflow.fire(case, 'submit', 'applicant', 'applicant')
        self.assertEqual(case.status, 'draft')

    def test_full_review_cycle_is_recorded(self):
        case = demo.make_case('id-non-eor')
        fire = lambda event, actor: workflow.fire(case, event, actor, actor)
        fire('submit', 'applicant')
        fire('start_review', 'reviewer')
        with self.assertRaises(workflow.TransitionError):  # nothing to send yet
            fire('request_info', 'reviewer')
        ask = InfoRequest.objects.create(case=case, message='Which city?')
        fire('request_info', 'reviewer')
        self.assertTrue(case.editable)  # the applicant may edit again to answer
        with self.assertRaises(workflow.TransitionError):  # request still unanswered
            fire('respond', 'applicant')
        ask.reply, ask.answered_at = 'Bali', case.updated_at
        ask.save()
        fire('respond', 'applicant')
        fire('approve', 'reviewer')
        self.assertEqual(case.status, 'approved')
        self.assertEqual(list(case.events.values_list('event', flat=True)),
                         ['submit', 'start_review', 'request_info', 'respond', 'approve'])
        with self.assertRaises(workflow.TransitionError):  # terminal
            fire('reject', 'reviewer')

    def test_actor_must_match_the_event(self):
        case = demo.make_case('id-non-eor')
        with self.assertRaises(workflow.TransitionError):
            workflow.fire(case, 'submit', 'reviewer', 'reviewer')

    def test_approval_is_blocked_while_a_request_is_open(self):
        case = demo.make_case('id-non-eor')
        workflow.fire(case, 'submit', 'applicant', 'a')
        workflow.fire(case, 'start_review', 'reviewer', 'r')
        InfoRequest.objects.create(case=case, message='?')
        self.assertEqual(dict((e, why) for e, _, why in workflow.available(case, 'reviewer'))['approve'],
                         'Every information request needs a reply first.')
