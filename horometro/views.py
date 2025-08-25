from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from activos.models import Activo
from .models import LecturaHorometro, AlertaMantenimiento
from .services import importer


# -------- Helpers de permisos --------
def es_supervisor(u):
    """Permite acceso a usuarios del grupo 'Supervisor' o superusuarios."""
    return u.is_superuser or u.groups.filter(name__iexact="Supervisor").exists()


# -------- Formulario de carga (semana por semana) --------
class UploadForm(forms.Form):
    archivo = forms.FileField(label="Archivo Excel")
    hoja = forms.CharField(
        required=False, label="Hoja",
        help_text="Nombre exacto de la hoja (opcional)"
    )

    # Defaults: ISO actuales (compatible py3.8+)
    _iso = date.today().isocalendar()
    _year = getattr(_iso, "year", _iso[0])
    _week = getattr(_iso, "week", _iso[1])

    anio = forms.IntegerField(label="Año (ISO)", min_value=2000, max_value=2100, initial=_year)
    semana = forms.IntegerField(label="Semana (ISO)", min_value=1, max_value=53, initial=_week)

    dry_run = forms.BooleanField(required=False, initial=True, label="Dry run (simulación)")
    generar_alertas = forms.BooleanField(
        required=False,
        initial=False,  # apagado por defecto para cargas históricas
        label="Generar alertas",
        help_text="Crear/actualizar alertas a partir de esta carga"
    )

    def clean_hoja(self):
        s = (self.cleaned_data.get("hoja") or "").strip()
        return s or None


# -------- Subir Excel --------
@login_required
@user_passes_test(es_supervisor)
def subir_excel(request):
    """
    Formulario para cargar el Excel del horómetro (semana por semana).
    """
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                res = importer.importar_excel(
                    archivo=request.FILES["archivo"],
                    nombre_hoja=form.cleaned_data["hoja"],
                    dry_run=form.cleaned_data["dry_run"],
                    usuario=request.user,
                    anio_fijo=form.cleaned_data["anio"],
                    semana_fija=form.cleaned_data["semana"],
                    generar_alertas=form.cleaned_data["generar_alertas"],  # ← nuevo
                )
                if form.cleaned_data["dry_run"]:
                    messages.info(request, f"Simulación: {res['resumen']}")
                else:
                    msg = f"Importación realizada: {res['resumen']}"
                    if not form.cleaned_data["generar_alertas"]:
                        msg += " (alertas NO generadas)"
                    messages.success(request, msg)
                return render(
                    request,
                    "horometro/upload.html",
                    {
                        "form": form,
                        "resultado": res,
                        "dry": form.cleaned_data["dry_run"],
                    },
                )
            except Exception as e:
                messages.error(request, f"Error al importar: {e}")
        else:
            messages.error(request, "El formulario no es válido. Revisa los campos.")
    else:
        form = UploadForm()

    return render(request, "horometro/upload.html", {"form": form})


# -------- Historial de un activo (tabla + gráfica) --------
@login_required
def historial_activo(request, codigo):
    """
    Página para ver el historial (tabla + gráfica) de lecturas del horómetro de un activo.
    URL: /horometro/activo/<codigo>/
    """
    activo = get_object_or_404(Activo, codigo__iexact=codigo)
    lecturas_qs = (
        LecturaHorometro.objects
        .filter(activo=activo)
        .order_by("anio", "semana")
    )

    # Datos para la gráfica (Chart.js)
    chart_labels = [f"{l.anio}-W{l.semana:02d}" for l in lecturas_qs]
    chart_values = [float(l.lectura) for l in lecturas_qs]

    return render(
        request,
        "horometro/historial_activo.html",
        {
            "activo": activo,
            "lecturas": lecturas_qs,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
        },
    )


# -------- Alertas: listado y cambio de estado --------
@login_required
@user_passes_test(es_supervisor)
def lista_alertas(request):
    """
    Listado de alertas con filtros por estado y búsqueda por activo.
    URL: /mantenimiento/alertas/
    """
    estado = (request.GET.get("estado") or "").strip()
    q = (request.GET.get("q") or "").strip()

    qs = AlertaMantenimiento.objects.select_related("activo").all()
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(
            Q(activo__codigo__icontains=q) |
            Q(activo__nombre__icontains=q) |
            Q(activo__numero_activo__icontains=q)
        )

    alertas = qs.order_by("-anio", "-semana", "activo__codigo")[:500]

    return render(
        request,
        "horometro/alertas_list.html",
        {
            "alertas": alertas,
            "estado": estado,
            "q": q,
        },
    )


@login_required
@user_passes_test(es_supervisor)
@require_POST
def cambiar_estado_alerta(request, pk):
    """
    Cambia el estado de una alerta: NUEVA / EN_PROCESO / CERRADA
    URL: /mantenimiento/alertas/<pk>/estado/
    """
    nueva = (request.POST.get("estado") or "").strip().upper()
    alerta = get_object_or_404(AlertaMantenimiento, pk=pk)

    if nueva not in {"NUEVA", "EN_PROCESO", "CERRADA"}:
        messages.error(request, "Estado inválido.")
        return redirect("horometro_alertas")

    alerta.estado = nueva
    if nueva == "CERRADA":
        from django.utils import timezone
        alerta.cerrado_en = timezone.now()
    alerta.save(update_fields=["estado", "cerrado_en", "actualizado_en"])

    messages.success(request, f"Alerta actualizada a '{nueva}'.")
    return redirect("horometro_alertas")
