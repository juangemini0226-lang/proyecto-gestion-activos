# core/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django import forms
import json
from django.db.models import Count
from activos.models import RegistroMantenimiento, Activo, Novedad
from horometro.models import LecturaHorometro, AlertaMantenimiento

# ----------------- Home -----------------
@login_required
def home(request):
    # Órdenes de mantenimiento pendientes o en progreso
    ordenes_pendientes = (
        RegistroMantenimiento.objects
        .filter(estado__in=["PEN", "PRO"])
        .order_by("fecha_creacion")
    )

    # Badge de alertas (solo para supervisores / superusuarios)
    if request.user.is_superuser or request.user.groups.filter(name__iexact="Supervisor").exists():
        alertas_nuevas = AlertaMantenimiento.objects.filter(estado="NUEVA").count()
    else:
        alertas_nuevas = 0

    contexto = {
        "ordenes": ordenes_pendientes,
        "alertas_nuevas": alertas_nuevas,   # <-- coincide con el template
        "section": "home",
    }
    return render(request, "core/home.html", contexto)


# ----------------- Dashboard Horómetro -----------------
def es_supervisor(u):
    return u.is_superuser or u.groups.filter(name__iexact="Supervisor").exists()


class SelectorActivoForm(forms.Form):
    codigo = forms.CharField(
        required=False,
        label="Activo",
        help_text="Escribe el código o selecciona de la lista",
        widget=forms.TextInput(attrs={"placeholder": "Ej. MOL15282", "class": "form-control"})
    )


@login_required
@user_passes_test(es_supervisor)
def dashboard_horometro(request):
    """
    Dashboard: selector de activo + gráfica y tabla de lecturas.
    URL: /dashboard/horometro/
    """
    form = SelectorActivoForm(request.GET or None)
    activo = None
    lecturas = []
    chart_labels = []
    chart_values = []

    # Para limitar lecturas (ej: ?limite=52 muestra últimas 52)
    try:
        limite = max(0, int(request.GET.get("limite", "0")))  # 0 = sin límite
    except ValueError:
        limite = 0

    # Lista para el datalist (código + nombre)
    activos_list = list(
        Activo.objects.order_by("codigo").values_list("codigo", "nombre")[:1000]
    )

    if form.is_valid() and form.cleaned_data.get("codigo"):
        q = form.cleaned_data["codigo"].strip()
        # Buscar por código; si no, número; si no, nombre
        activo = (
            Activo.objects.filter(codigo__iexact=q).first()
            or Activo.objects.filter(numero_activo__iexact=q).first()
            or Activo.objects.filter(nombre__iexact=q).first()
        )
        if activo:
            qs = (
                LecturaHorometro.objects
                .filter(activo=activo)
                .order_by("anio", "semana")
            )

            # Si se pidió límite, tomar las últimas N manteniendo el orden cronológico
            if limite > 0:
                qs = list(qs.reverse()[:limite])[::-1]

            lecturas = list(qs)
            chart_labels = [f"{l.anio}-W{l.semana:02d}" for l in lecturas]
            chart_values = [float(l.lectura) for l in lecturas]

    # Paginación de la tabla (no afecta la gráfica)
    paginator = Paginator(lecturas, 50)  # 50 filas por página
    page_number = request.GET.get("page")
    lecturas_page = paginator.get_page(page_number)

    return render(
        request,
        "core/dashboard_horometro.html",
        {
            "form": form,
            "activo": activo,
            "lecturas": lecturas_page,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "activos_list": activos_list,
            "limite": limite,
        },
    )


@login_required
def dashboard_novedades(request):
    """Dashboard con gráficos de novedades."""
    fallas_qs = (
        Novedad.objects.values("falla__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    labels_fallas = [row["falla__nombre"] or "Sin falla" for row in fallas_qs]
    counts_fallas = [row["total"] for row in fallas_qs]

    total = sum(counts_fallas) or 1
    cumulative = []
    acc = 0
    for c in counts_fallas:
        acc += c
        cumulative.append(round(acc * 100 / total, 2))

    etapas_qs = (
        Novedad.objects.values("etapa")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    labels_etapas = [row["etapa"] or "Sin etapa" for row in etapas_qs]
    counts_etapas = [row["total"] for row in etapas_qs]

    context = {
        "labels_fallas": labels_fallas,
        "counts_fallas": counts_fallas,
        "cumulative_fallas": cumulative,
        "labels_etapas": labels_etapas,
        "counts_etapas": counts_etapas,
        "section": "dashboard",
    }
    return render(request, "core/dashboard_novedades.html", context)