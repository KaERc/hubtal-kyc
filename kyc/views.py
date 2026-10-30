from django.contrib import messages
from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from . import engine, workflow
from .flows import FLOWS
from .models import Case, Document, InfoRequest


def client_ip(request):
    return request.META.get('REMOTE_ADDR')  # behind a proxy this must come from a trusted header (README)


def case_by_token(token):
    return get_object_or_404(Case, token=token)


@require_http_methods(['GET', 'POST'])
def start(request):
    if request.method == 'POST':
        flow = FLOWS.get(request.POST.get('flow'))
        if not flow:
            raise Http404
        case = Case.objects.create(flow_key=flow.key, flow_version=flow.version)
        return redirect('kyc:case', token=case.token)
    return render(request, 'kyc/start.html', {'flows': FLOWS.values()})


def case_home(request, token):
    case = case_by_token(token)
    return render(request, 'kyc/case.html', {
        'case': case,
        'prog': engine.case_progress(case),
        'requests': case.info_requests.all(),
        'actions': workflow.available(case, 'applicant'),
    })


@require_POST
def submit(request, token):
    """One button, two events: the first submission, and sending answers back after a reviewer's request."""
    case = case_by_token(token)
    event = 'respond' if case.status == 'info_requested' else 'submit'
    try:
        workflow.fire(case, event, 'applicant', 'applicant', client_ip(request))
        messages.success(request, 'Sent to the reviewer.')
    except workflow.TransitionError as e:
        messages.error(request, str(e))
    return redirect('kyc:case', token=token)


@require_POST
def reply(request, token, pk):
    case = case_by_token(token)
    ask = get_object_or_404(InfoRequest, pk=pk, case=case)
    text = request.POST.get('reply', '').strip()
    if case.status != 'info_requested' or not ask.open:
        messages.error(request, 'This question is no longer open.')
    elif text:
        ask.reply, ask.answered_at = text[:engine.MAX_TEXT], timezone.now()
        ask.save()
        messages.success(request, 'Answer saved. Update your details if needed, then send everything back.')
    return redirect('kyc:case', token=token)
