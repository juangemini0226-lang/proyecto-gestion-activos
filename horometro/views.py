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
        help_text="Nombre exacto de la hoja (opcional)",
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
        help_text="Crear/actualizar alertas a partir de esta carga",
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
                        "section": "horometro",
                    },
                )
            except Exception as e:
                messages.error(request, f"Error al importar: {e}")
        else:
            messages.error(request, "El formulario no es válido. Revisa los campos.")
    else:
        form = UploadForm()

    return render(request, "horometro/upload.html", {"form": form, "section": "horometro"})


# -------- Dashboard --------
@login_required
def dashboard(request):
    lecturas = (
        LecturaHorometro.objects.select_related("activo")
        .order_by("activo__codigo", "-anio", "-semana")
    )
    datos = []
    vistos = set()
    for l in lecturas:
        if l.activo_id in vistos:
            continue
        prev = (
            LecturaHorometro.objects.filter(activo=l.activo)
            .exclude(pk=l.pk)
            .order_by("-anio", "-semana")
            .first()
        )
        diff = l.lectura - prev.lectura if prev else None
        alerta = (
            AlertaMantenimiento.objects.filter(
                activo=l.activo, estado__in=["NUEVA", "EN_PROCESO"]
            )
            .order_by("-anio", "-semana")
            .first()
        )
        datos.append(
            {
                "activo": l.activo,
                "lectura": l.lectura,
                "diferencia": diff,
                "alerta": alerta,
            }
        )
        vistos.add(l.activo_id)

    chart_labels = [d["activo"].codigo for d in datos]
    chart_values = [float(d["lectura"]) for d in datos]

    return render(
        request,
        "horometro/dashboard.html",
        {
            "items": datos,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "section": "horometro",
        },
    )


# -------- Historial de un activo (tabla + gráfica) --------
@login_required
def historial_activo(request, codigo):
    """
    Página para ver el historial (tabla + gráfica) de lecturas del horómetro de un activo.
    URL: /horometro/activo/<codigo>/
    """
    activo = get_object_or_404(Activo, codigo__iexact=codigo)
    inicio = (request.GET.get("inicio") or "").strip()
    fin = (request.GET.get("fin") or "").strip()
    comparar = (request.GET.get("comparar") or "").strip()

    qs = LecturaHorometro.objects.filter(activo=activo)

    def aplicar_rango(qs):
        if inicio:
            try:
                y, w = inicio.split("-W")
                qs = qs.filter(Q(anio__gt=int(y)) | (Q(anio=int(y)) & Q(semana__gte=int(w))))
            except Exception:
                pass
        if fin:
            try:
                y, w = fin.split("-W")
                qs = qs.filter(Q(anio__lt=int(y)) | (Q(anio=int(y)) & Q(semana__lte=int(w))))
            except Exception:
                pass
        return qs

    lecturas_qs = aplicar_rango(qs).order_by("anio", "semana")
    main_map = {f"{l.anio}-W{l.semana:02d}": float(l.lectura) for l in lecturas_qs}
    chart_labels = list(main_map.keys())
    chart_values = list(main_map.values())

    compare_activo = None
    compare_values = None
    if comparar:
        compare_activo = Activo.objects.filter(codigo__iexact=comparar).first()
        if compare_activo:
            comp_qs = aplicar_rango(
                LecturaHorometro.objects.filter(activo=compare_activo).order_by("anio", "semana")
            )
            comp_map = {f"{l.anio}-W{l.semana:02d}": float(l.lectura) for l in comp_qs}
            labels = sorted(set(chart_labels) | set(comp_map.keys()))
            chart_labels = labels
            chart_values = [main_map.get(lbl) for lbl in labels]
            compare_values = [comp_map.get(lbl) for lbl in labels]

    context = {
        "activo": activo,
        "lecturas": lecturas_qs,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "inicio": inicio,
        "fin": fin,
        "comparar": comparar,
        "section": "horometro",
    }
    if compare_activo and compare_values is not None:
        context.update({"compare_activo": compare_activo, "compare_values": compare_values})

    return render(request, "horometro/historial_activo.html", context)



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
            "section": "horometro",
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
