import os

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from . import engine, workflow
from .flows import FLOWS
from .models import Case, Document, InfoRequest

# What an upload must start with, per extension; the extension alone proves nothing.
MAGIC = {'.pdf': b'%PDF', '.jpg': b'\xff\xd8\xff', '.jpeg': b'\xff\xd8\xff', '.png': b'\x89PNG'}


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


def section(request, token, key):
    """Show or save one section. Saving is forgiving: valid answers are kept even when another field is
    invalid or still empty, so an applicant can leave and come back; completeness is judged at submit."""
    case = case_by_token(token)
    s = next((s for s in case.flow.sections if s.key == key), None)
    if s is None:
        raise Http404
    entries = engine.entries(s, case.data)
    errs = [{} for _ in entries]
    posted = request.method == 'POST'
    if posted:
        if not case.editable:
            messages.error(request, 'This case is locked while it is with the reviewer.')
            return redirect('kyc:case', token=token)
        action = request.POST.get('action', '')
        if s.repeat:
            try:
                n = min(int(request.POST.get('n', 0)), 50)
            except ValueError:
                n = 0
            parsed = [engine.parse_entry(s, request.POST, f'{i}-') for i in range(n)]
            entries, errs = [v for v, _ in parsed], [e for _, e in parsed]
            if action == 'add':
                entries.append({})
                errs.append({})
            elif action.startswith('remove-') and action[7:].isdigit() and int(action[7:]) < len(entries):
                del entries[int(action[7:])], errs[int(action[7:])]
        else:
            values, errors = engine.parse_entry(s, request.POST)
            entries, errs = [values], [errors]
        case.data[s.key] = entries if s.repeat else entries[0]
        case.save(update_fields=['data', 'updated_at'])
        if action:
            return redirect('kyc:section', token=token, key=key)
        if not any(errs):
            messages.success(request, f'Saved “{s.title}”.')
            return redirect('kyc:case', token=token)
    forms = [engine.bind(s, e, errs[i], f'{i}-' if s.repeat else '') for i, e in enumerate(entries)]
    if posted:  # show what was typed next to the error rather than a blank field
        for bound in forms:
            for b in bound:
                if b['error']:
                    b['value'] = request.POST.get(b['name'])
        messages.error(request, 'Some answers were not saved, see the marked fields.')
    return render(request, 'kyc/section.html', {'case': case, 's': s, 'forms': forms})


def upload_error(up):
    ext = os.path.splitext(up.name)[1].lower()
    if ext not in MAGIC:
        return 'Only PDF, JPG and PNG files are accepted.'
    if up.size > settings.MAX_UPLOAD_BYTES:
        return 'The file is larger than 10 MB.'
    head = up.read(8)
    up.seek(0)
    if not head.startswith(MAGIC[ext]):
        return 'The file content does not match its type.'


def docs(request, token):
    case = case_by_token(token)
    wanted = engine.active_docs(case.flow, case.data)
    if request.method == 'POST':
        doc = next((d for d in wanted if d.key == request.POST.get('key')), None)
        up = request.FILES.get('file')
        if not case.editable:
            messages.error(request, 'This case is locked while it is with the reviewer.')
        elif not doc or not up:
            messages.error(request, 'Choose a file to upload.')
        elif error := upload_error(up):
            messages.error(request, error)
        else:
            Document.objects.create(case=case, key=doc.key, file=up, name=os.path.basename(up.name)[:255])
            messages.success(request, f'Uploaded: {doc.label}.')
        return redirect('kyc:docs', token=token)
    have = {}
    for d in case.documents.all():
        have.setdefault(d.key, []).append(d)
    return render(request, 'kyc/docs.html', {'case': case, 'rows': [(d, have.get(d.key, [])) for d in wanted]})


@require_POST
def doc_delete(request, token, pk):
    case = case_by_token(token)
    doc = get_object_or_404(Document, pk=pk, case=case)
    if case.editable:
        doc.file.delete(save=False)
        doc.delete()
    return redirect('kyc:docs', token=token)


def send(doc):
    """Always as an attachment: an uploaded file is never rendered by the browser in our origin."""
    return FileResponse(doc.file.open('rb'), as_attachment=True, filename=doc.name)


def download(request, token, pk):
    return send(get_object_or_404(Document, pk=pk, case__token=token))
