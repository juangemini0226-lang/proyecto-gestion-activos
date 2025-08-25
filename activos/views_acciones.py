# activos/views_acciones.py (o donde gestione acciones de OT)
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import RegistroMantenimiento, EstadoOT

@login_required
def cerrar_ot(request, pk):
    ot = get_object_or_404(RegistroMantenimiento, pk=pk)
    try:
        ot.transition_to(EstadoOT.CER, usuario=request.user, motivo=request.POST.get('motivo',''))
        messages.success(request, f"OT #{ot.pk} cerrada.")
    except Exception as e:
        messages.error(request, str(e))
    return redirect('activos:ordenes_list')
