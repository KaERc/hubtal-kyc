from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from kyc import demo, workflow
from kyc.models import Case, InfoRequest, ReviewNote


class Command(BaseCommand):
    help = 'Create or reset the demo reviewer account and, on an empty database, three demo cases. Safe to run again.'

    def handle(self, *args, **options):
        login = settings.DEMO_REVIEWER
        reviewer, _ = User.objects.get_or_create(username=login['username'])
        reviewer.is_staff = True
        reviewer.set_password(login['password'])  # reset every time, so the login printed below always works
        reviewer.save()
        self.stdout.write(f"Reviewer sign-in at /review/: username {login['username']}, password {login['password']}")
        if Case.objects.exists():
            self.stdout.write('Cases already exist, so no demo cases were added. Their links:')
            for case in Case.objects.order_by('pk'):
                self.stdout.write(f'  #{case.pk} {case.flow_key} ({case.status_label}): http://127.0.0.1:8000/c/{case.token}/')
            return self.stdout.write('To start over: delete db.sqlite3 and media/, run migrate, then seed again.')

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
        workflow.fire(b, 'start_review', 'reviewer', reviewer.username)
        ReviewNote.objects.create(case=b, author=reviewer, text='Company was insolvent in the past: check the registry extract.')
        InfoRequest.objects.create(case=b, section='compliance', message='You answered \u201cyes\u201d to bankruptcy. Please give the year and the outcome.')
        workflow.fire(b, 'request_info', 'reviewer', reviewer.username)

        # 3. An EOR case the applicant has only started.
        c = demo.make_case('id-eor', complete=False)
        c.data = {'employer': demo.complete_data(c.flow)['employer']}
        c.data['employer']['company_name'] = 'Example Robotics Ltd'
        c.save()

        self.stdout.write("Three demo cases. Each link is the applicant's private page for one case:")
        for number, (case, what, todo) in enumerate((
            (a, 'non-EOR, submitted', 'nothing left for the applicant; look at it from the reviewer side'),
            (b, 'EOR, question open', 'the reviewer asked something: open this link and answer it'),
            (c, 'EOR, just started', 'only the first section is filled in: continue it'),
        ), 1):
            self.stdout.write(f'  {number}. {what:20} {todo}\n     http://127.0.0.1:8000/c/{case.token}/')
