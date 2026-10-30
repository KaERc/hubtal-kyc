import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import TestCase, override_settings

from . import demo, engine, workflow
from .flows import FLOWS
from .flows.spec import Doc, Field, Flow, Section
from .models import Case, Document, InfoRequest, ReviewNote

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


@override_settings(MEDIA_ROOT=MEDIA)
class ViewTests(TestCase):
    def start(self, flow='id-non-eor'):
        return self.client.post('/', {'flow': flow}).headers['Location'].split('/')[2]

    def upload(self, token, key, name='file.pdf', body=b'%PDF-1.4 x'):
        self.client.post(f'/c/{token}/docs/', {'key': key, 'file': SimpleUploadedFile(name, body)})

    def test_applicant_to_approval_end_to_end(self):
        token = self.start()
        case = Case.objects.get(token=token)
        case.data = demo.complete_data(case.flow)
        case.save()
        self.client.post(f'/c/{token}/submit/')
        case.refresh_from_db()
        self.assertEqual(case.status, 'draft')  # documents are still missing
        self.upload(token, 'passport')
        self.upload(token, 'lease_or_booking')
        self.client.post(f'/c/{token}/submit/')
        case.refresh_from_db()
        self.assertEqual(case.status, 'submitted')

        User.objects.create_user('rev', password='pw', is_staff=True)
        self.client.login(username='rev', password='pw')
        self.assertContains(self.client.get('/review/'), case.subject)
        self.client.post(f'/review/{case.pk}/do/start_review/')
        self.client.post(f'/review/{case.pk}/request/', {'section': 'stay', 'message': 'Which city?'})
        case.refresh_from_db()
        self.assertEqual(case.status, 'info_requested')
        self.client.post(f'/c/{token}/submit/')  # cannot send back before answering
        case.refresh_from_db()
        self.assertEqual(case.status, 'info_requested')
        self.client.post(f'/c/{token}/reply/{case.info_requests.get().pk}/', {'reply': 'Bali'})
        self.client.post(f'/c/{token}/submit/')
        self.client.post(f'/review/{case.pk}/do/approve/')
        case.refresh_from_db()
        self.assertEqual(case.status, 'approved')

    def test_review_pages_need_a_staff_account(self):
        case = demo.make_case('id-non-eor')
        urls = ['/review/', f'/review/{case.pk}/', f'/review/file/{case.documents.first().pk}/']
        for url in urls:
            r = self.client.get(url)
            self.assertEqual((r.status_code, '/login/' in r['Location']), (302, True), url)
        User.objects.create_user('plain', password='pw')  # signed in but not staff
        self.client.login(username='plain', password='pw')
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self.client.post(f'/review/{case.pk}/do/reject/').status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.status, 'draft')

    def test_case_is_locked_while_it_is_with_the_reviewer(self):
        case = demo.make_case('id-non-eor')
        workflow.fire(case, 'submit', 'applicant', 'a')
        self.client.post(f'/c/{case.token}/s/applicant/', {'full_name': 'Changed'})
        self.client.post(f'/c/{case.token}/docs/{case.documents.first().pk}/delete/')
        case.refresh_from_db()
        self.assertNotEqual(case.data['applicant']['full_name'], 'Changed')
        self.assertEqual(case.documents.count(), 2)

    def test_uploads_are_checked_by_content_and_type(self):
        token = self.start()
        self.upload(token, 'passport', 'fake.pdf', b'<script>alert(1)</script>')
        self.upload(token, 'passport', 'program.exe', b'MZ')
        self.upload(token, 'not-a-document', 'ok.pdf')
        self.assertEqual(Document.objects.count(), 0)
        self.upload(token, 'passport', 'ok.pdf')
        self.assertEqual(Document.objects.count(), 1)

    def test_documents_are_only_served_to_their_own_case(self):
        mine, other = demo.make_case('id-non-eor'), demo.make_case('id-non-eor')
        doc = other.documents.first()
        self.assertEqual(self.client.get(f'/c/{mine.token}/file/{doc.pk}/').status_code, 404)
        r = self.client.get(f'/c/{other.token}/file/{doc.pk}/')
        self.assertEqual((r.status_code, 'attachment' in r['Content-Disposition']), (200, True))

    def test_unknown_token_is_not_found(self):
        self.assertEqual(self.client.get('/c/nope/').status_code, 404)


class FlowDefinitionTests(TestCase):
    """A mistake in a new flow must fail when the flow is imported."""

    def flow(self, **changes):
        base = dict(key='t', version='1', country='XX', title='T', subject='a.n',
                    sections=(Section('a', 'A', (Field('n', 'N'), Field('m', 'M', show_if=(('n', 'x'),)))),),
                    docs=(Doc('d', 'D', show_if=(('a.n', 'x'),)),))
        return Flow(**{**base, **changes})

    def test_a_valid_flow_is_accepted(self):
        self.flow()

    def test_mistakes_are_rejected(self):
        ok = Section('a', 'A', (Field('n', 'N'),))
        cases = {
            'unknown subject': dict(subject='a.nope'),
            'subject in a repeat section': dict(sections=(Section('a', 'A', (Field('n', 'N'),), repeat=True),)),
            'duplicate section': dict(sections=(ok, ok)),
            'duplicate field': dict(sections=(Section('a', 'A', (Field('n', 'N'), Field('n', 'N again'))),)),
            'condition on an unknown field': dict(sections=(Section('a', 'A', (Field('n', 'N', show_if=(('zz', 'x'),)),)),)),
            'condition on a later field': dict(sections=(Section('a', 'A', (Field('n', 'N', show_if=(('m', 'x'),)), Field('m', 'M'))),)),
            'document condition on an unknown field': dict(docs=(Doc('d', 'D', show_if=(('a.zz', 'x'),)),)),
            'document condition without a section': dict(docs=(Doc('d', 'D', show_if=(('n', 'x'),)),)),
            'duplicate document': dict(docs=(Doc('d', 'D'), Doc('d', 'D again'))),
        }
        for name, changes in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.flow(**changes)


@override_settings(MEDIA_ROOT=MEDIA)
class ReviewFixTests(TestCase):
    """Regressions for the problems the code review found."""

    def test_a_huge_number_is_a_field_error_not_a_crash(self):
        s = section('id-eor', 'employer')
        values, errors = engine.parse_entry(s, post(employees='1e5000'))
        self.assertEqual((values, set(errors)), ({}, {'employees'}))
        case = demo.make_case('id-eor', complete=False)
        r = self.client.post(f'/c/{case.token}/s/employer/', {'employees': '1e5000'})
        self.assertEqual(r.status_code, 200)

    def test_a_stale_repeat_list_is_refused_not_applied(self):
        case = demo.make_case('id-eor')
        before = case.data['ubos']
        url = f'/c/{case.token}/s/ubos/'
        self.client.post(url, {'n': '1', '0-full_name': 'Only one'})  # the form believed there was one entry
        self.client.post(url, {'n': '-1'})
        case.refresh_from_db()
        self.assertEqual(case.data['ubos'], before)

    def test_a_stale_status_cannot_be_acted_on(self):
        case = demo.make_case('id-non-eor')
        workflow.fire(case, 'submit', 'applicant', 'a')
        workflow.fire(case, 'start_review', 'reviewer', 'r')
        first, second = Case.objects.get(pk=case.pk), Case.objects.get(pk=case.pk)
        workflow.fire(first, 'approve', 'reviewer', 'r1')
        with self.assertRaises(workflow.TransitionError):
            workflow.fire(second, 'approve', 'reviewer', 'r2')  # second still believes in_review
        self.assertEqual(case.events.filter(event='approve').count(), 1)

    def test_rejecting_needs_a_reason(self):
        case = demo.make_case('id-non-eor')
        workflow.fire(case, 'submit', 'applicant', 'a')
        workflow.fire(case, 'start_review', 'reviewer', 'r')
        with self.assertRaises(workflow.TransitionError):
            workflow.fire(case, 'reject', 'reviewer', 'r')
        ReviewNote.objects.create(case=case, author=User.objects.create_user('rev'), text='Sanctions hit')
        workflow.fire(case, 'reject', 'reviewer', 'r')
        self.assertEqual(case.status, 'rejected')

    def test_double_submit_is_one_submission(self):
        case = demo.make_case('id-non-eor')
        for _ in range(2):
            self.client.post(f'/c/{case.token}/submit/')
        self.assertEqual(case.events.filter(event='submit').count(), 1)

    def test_empty_reply_keeps_the_request_open(self):
        case = demo.make_case('id-non-eor')
        workflow.fire(case, 'submit', 'applicant', 'a')
        workflow.fire(case, 'start_review', 'reviewer', 'r')
        ask = InfoRequest.objects.create(case=case, message='?')
        workflow.fire(case, 'request_info', 'reviewer', 'r')
        self.client.post(f'/c/{case.token}/reply/{ask.pk}/', {'reply': '   '})
        ask.refresh_from_db()
        self.assertTrue(ask.open)

    @override_settings(MAX_FILES_PER_CASE=1)
    def test_the_number_of_files_per_case_is_capped(self):
        case = demo.make_case('id-non-eor', complete=False)
        for name in ('a.pdf', 'b.pdf'):
            self.client.post(f'/c/{case.token}/docs/', {'key': 'passport', 'file': SimpleUploadedFile(name, b'%PDF-1.4 x')})
        self.assertEqual(case.documents.count(), 1)

    def test_a_missing_file_is_a_404_not_a_crash(self):
        case = demo.make_case('id-non-eor')
        doc = case.documents.first()
        doc.file.storage.delete(doc.file.name)
        self.assertEqual(self.client.get(f'/c/{case.token}/file/{doc.pk}/').status_code, 404)

    def test_beneficial_owners_can_be_added_edited_and_removed(self):
        case = demo.make_case('id-eor', complete=False)
        url = f'/c/{case.token}/s/ubos/'
        names = lambda: [e.get('full_name') for e in Case.objects.get(pk=case.pk).data['ubos']]
        self.client.post(url, {'n': '0', 'action': 'add'})
        self.client.post(url, {'n': '1', 'action': 'add', '0-full_name': 'A', '0-ownership_pct': '60'})
        self.assertEqual(names(), ['A', None])
        self.client.post(url, {'n': '2', '0-full_name': 'A', '0-ownership_pct': '60', '1-full_name': 'B', '1-ownership_pct': '40'})
        self.assertEqual(names(), ['A', 'B'])
        self.client.post(url, {'n': '2', 'action': 'remove-0', '0-full_name': 'A', '1-full_name': 'B', '1-ownership_pct': '40'})
        self.assertEqual(names(), ['B'])
