import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from kyc import demo, workflow
from kyc.models import Case, InfoRequest, ReviewNote

USERNAME = 'reviewer'


class Command(BaseCommand):
    help = 'Create a demo reviewer account and three demo cases (does nothing if cases already exist).'

    def handle(self, *args, **options):
        password = os.environ.get('KYC_DEMO_PASSWORD', 'reviewer')  # demo account for local use only
        reviewer, created = User.objects.get_or_create(username=USERNAME, defaults={'is_staff': True})
        if created:
            reviewer.set_password(password)
            reviewer.save()
        self.stdout.write(f'Reviewer sign-in: {USERNAME} / {password if created else "(unchanged)"}  ->  /review/')
        if Case.objects.exists():
            return self.stdout.write('Cases already exist, not adding demo cases.')

        # 1. A clean non-EOR case, submitted.
        a = demo.make_case('id-non-eor')
        a.data['applicant']['full_name'] = 'Anna Example'
        a.save()
        workflow.fire(a, 'submit', 'applicant', 'applicant')

        # 2. An EOR case with a red flag, in review with a note and an open question to the applicant.
        b = demo.make_case('id-eor')
        b.data['candidate']['full_name'] = 'Jonas Example'
        b.data['compliance']['bankrupt'] = 'yes'
        b.save()
        workflow.fire(b, 'submit', 'applicant', 'applicant')
        workflow.fire(b, 'start_review', 'reviewer', USERNAME)
        ReviewNote.objects.create(case=b, author=reviewer, text='Company was insolvent in the past: check the registry extract.')
        InfoRequest.objects.create(case=b, section='compliance', message='You answered “yes” to bankruptcy. Please give the year and the outcome.')
        workflow.fire(b, 'request_info', 'reviewer', USERNAME)

        # 3. An EOR case the applicant has only started.
        c = demo.make_case('id-eor', complete=False)
        c.data = {'employer': demo.complete_data(c.flow)['employer']}
        c.data['employer']['company_name'] = 'Example Robotics Ltd'
        c.save()

        self.stdout.write('Three demo cases. Each link is the applicant\'s private page for one case:')
        for number, (case, what, todo) in enumerate((
            (a, 'non-EOR, submitted', 'nothing left for the applicant; look at it from the reviewer side'),
            (b, 'EOR, question open', 'the reviewer asked something: open this link and answer it'),
            (c, 'EOR, just started', 'only the first section is filled in: continue it'),
        ), 1):
            self.stdout.write(f'  {number}. {what:20} {todo}\n     http://127.0.0.1:8000/c/{case.token}/')
