# activos/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.urls import reverse
from .models import (
    Activo,
    RegistroMantenimiento,
    TareaMantenimiento,
    DetalleMantenimiento,
    EstadoOT,
    TipoOT,
    PlantillaChecklist,
    CatalogoFalla,
    Ubicacion,
)
from .forms import (
    RegistroMantenimientoForm,
    EvidenciaDetalleForm,
    CargarPlantillaForm,
    GuardarComoPlantillaForm,
    AddTareaRapidaForm,
    AsignarOTForm,
    ActivoForm,
)
from horometro.models import AlertaMantenimiento, LecturaHorometro


def redirect_buscar_a_detalle(request, codigo: str):
    return redirect("activos:detalle_activo_por_codigo", codigo=codigo)


@login_required
def activos_list(request):
    """Listado sencillo de activos."""
    activos = Activo.objects.all()
    context = {"activos": activos, "section": "activos"}
    return render(request, "activos/activos_list.html", context)


@login_required
def activo_create(request):
    if request.method == "POST":
        form = ActivoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Activo creado correctamente.")
            return redirect("activos:activos_list")
    else:
        form = ActivoForm()
    return render(request, "activos/activo_form.html", {"form": form})


@login_required
def activo_update(request, pk: int):
    activo = get_object_or_404(Activo, pk=pk)
    if request.method == "POST":
        form = ActivoForm(request.POST, request.FILES, instance=activo)
        if form.is_valid():
            form.save()
            messages.success(request, "Activo actualizado correctamente.")
            return redirect("activos:activos_list")
    else:
        form = ActivoForm(instance=activo)
    return render(request, "activos/activo_form.html", {"form": form, "activo": activo})


# ===================== Helpers de permisos =====================
def es_supervisor(u):
    return u.is_superuser or u.groups.filter(name__iexact="Supervisor").exists()


# ===================== Utilidades de negocio =====================
def _apply_best_template_or_fallback(ot: RegistroMantenimiento):
    """
    Aplica la mejor plantilla usando el manager del modelo.
    Prioridad: Falla -> Activo -> Familia -> Global.
    """
    plantilla = PlantillaChecklist.objects.get_best_template_for(
        activo=ot.activo, tipo=ot.tipo, falla=ot.falla
    )
    if plantilla:
        ot.aplicar_plantilla(plantilla)
        return "plantilla"
    
    # Fallback si no encuentra plantilla
    if not ot.detalles.exists():
        DetalleMantenimiento.objects.bulk_create(
            [DetalleMantenimiento(registro=ot, tarea=t) for t in TareaMantenimiento.objects.all()]
        )
    return "fallback"


def _ensure_checklist_exists(ot: RegistroMantenimiento):
    """Garantiza que la OT tenga un checklist (plantilla o fallback)."""
    if not ot.detalles.exists():
        _apply_best_template_or_fallback(ot)


# ===================== Vistas =====================

@login_required
@user_passes_test(es_supervisor)
def ordenes_list(request):
    """Listado de órdenes (supervisor) con filtros y paginación."""

    # Recuperar filtros desde la sesión o inicializarlos
    filtros = request.session.get("filtros_ot", {"estado": "", "tipo": "", "q": ""})

    # Si vienen datos por POST, actualizamos la sesión y redirigimos (PRG)
    if request.method == "POST":
        filtros = {
            "estado": request.POST.get("estado", ""),
            "tipo": request.POST.get("tipo", ""),
            "q": request.POST.get("q", ""),
        }
        request.session["filtros_ot"] = filtros
        return redirect("activos:ordenes_list")

    qs = RegistroMantenimiento.objects.select_related("activo", "asignado_a").all()

    # Aplicar filtros
    if filtros.get("estado"):
        qs = qs.filter(estado=filtros["estado"])
    if filtros.get("tipo"):
        qs = qs.filter(tipo=filtros["tipo"])
    if filtros.get("q"):
        q = filtros["q"]
        qs = qs.filter(
            Q(id__icontains=q)
            | Q(activo__codigo__icontains=q)
            | Q(activo__nombre__icontains=q)
            | Q(asignado_a__username__icontains=q)
        )

    paginator = Paginator(qs.order_by("-fecha_creacion"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "ordenes": page_obj.object_list,
        "section": "mantenimiento",
        "ESTADOS": EstadoOT.choices,
        "filtros": filtros,
    }
    return render(request, "activos/ordenes_list.html", context)


@login_required
@user_passes_test(es_supervisor)
def agendar_mantenimiento(request):
    """Crea una OT en estado PEN usando el nuevo RegistroMantenimientoForm."""
    if request.method == "POST":
        form = RegistroMantenimientoForm(request.POST)
        if form.is_valid():
            ot = form.save(commit=False)
            ot.creado_por = request.user
            ot.estado = EstadoOT.PEN
            ot.save()

            # Aplicar la plantilla o fallback
            origen = _apply_best_template_or_fallback(ot)
            txt = "Plantilla aplicada." if origen == "plantilla" else "Checklist base generado."
            messages.success(request, f"Orden creada (#{ot.id}). {txt}")
            return redirect("activos:ordenes_list")
    else:
        form = RegistroMantenimientoForm()

    return render(request, "activos/agendar_mantenimiento.html", {"form": form})
    def crear_ot_desde_alerta(request, pk: int):
        request, f"Orden #{ot.id} creada para {alerta.activo.codigo}. La alerta quedó EN_PROCESO."
    
    return redirect("activos:ordenes_list")


@login_required
@user_passes_test(es_supervisor)
def asignar_ot(request, pk: int):
    """Asigna o reasigna una OT a un operario."""
    ot = get_object_or_404(RegistroMantenimiento.objects.select_related("activo"), pk=pk)

    if request.method == "POST":
        form = AsignarOTForm(request.POST)
        if form.is_valid():
            ot.asignado_a = form.cleaned_data["operario"]
            ot.save(update_fields=["asignado_a"])
            messages.success(
                request, f"OT #{ot.id} asignada a {ot.asignado_a.username}."
            )
            return redirect("activos:ordenes_list")
    else:
        form = AsignarOTForm(initial={"operario": ot.asignado_a_id})

    return render(request, "activos/ot_asignar.html", {"ot": ot, "form": form})


@login_required
def checklist_mantenimiento(request, pk: int):
    """Muestra y gestiona el checklist de una OT."""
    ot = get_object_or_404(
        RegistroMantenimiento.objects.select_related("activo"), pk=pk
    )
    _ensure_checklist_exists(ot)

    items = ot.detalles.select_related("tarea").prefetch_related("evidencias")

    if request.method == "POST":
        # Subida de evidencias
        if request.POST.get("upload_evidencia"):
            det_id = request.POST.get("upload_evidencia")
            det = get_object_or_404(items, pk=det_id)
            form = EvidenciaDetalleForm(request.POST, request.FILES)
            if form.is_valid():
                evidencia = form.save(commit=False)
                evidencia.detalle_mantenimiento = det
                evidencia.subido_por = request.user
                evidencia.save()
                messages.success(request, "Evidencia subida correctamente.")
            else:
                messages.error(request, "No se pudo subir la evidencia.")
            return redirect("activos:checklist_mantenimiento", pk=pk)

        # Guardar checklist
        if request.POST.get("guardar_checklist"):
            updated = []
            for det in items:
                det.completado = request.POST.get(f"tarea_{det.id}") == "on"
                det.observaciones = request.POST.get(f"obs_{det.id}", "").strip() or None
                updated.append(det)
            DetalleMantenimiento.objects.bulk_update(updated, ["completado", "observaciones"])
            messages.success(request, "Checklist actualizado.")
            return redirect("activos:checklist_mantenimiento", pk=pk)

    return render(
        request,
        "activos/checklist_mantenimiento.html",
        {"ot": ot, "items_checklist": items},
    )

def detalle_activo_por_codigo(request, codigo: str):
    """
    Detalle de Activo buscado por su 'codigo'.
    Muestra además las OTs recientes vinculadas al activo.
    """
    activo = get_object_or_404(Activo, codigo=codigo)

    ots = (
        RegistroMantenimiento.objects
        .filter(activo=activo)
        .select_related("activo")
        .order_by("-id")[:20]
    )

    ctx = {"activo": activo, "ots": ots}
    return render(request, "activos/detalle_activo.html", ctx)
@login_required
def iniciar_mantenimiento(request, activo_id: int):
    """
    Wrapper liviano: valida que el activo exista y redirige a la vista de agendar
    con el activo preseleccionado por querystring (?activo=<id>).
    Evita acoplarse a campos específicos de RegistroMantenimiento.
    """
    get_object_or_404(Activo, pk=activo_id)
    url = f"{reverse('activos:agendar_mantenimiento')}?activo={activo_id}"

    return redirect(url)
