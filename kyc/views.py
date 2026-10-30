from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import engine, workflow
from .flows import FLOWS
from .models import Case


@require_http_methods(['GET', 'POST'])
def start(request):
    if request.method == 'POST':
        flow = FLOWS.get(request.POST.get('flow'))
        if not flow:
            raise Http404
        case = Case.objects.create(flow_key=flow.key, flow_version=flow.version)
        return redirect('kyc:case', token=case.token)
    return render(request, 'kyc/start.html', {'flows': FLOWS.values()})
