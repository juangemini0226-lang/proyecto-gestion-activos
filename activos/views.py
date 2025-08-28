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
    qs = RegistroMantenimiento.objects.select_related("activo", "asignado_a").all()
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    context = {
        "page_obj": page_obj,
        "ordenes": page_obj.object_list,
        "section": "mantenimiento",
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

def cambiar_estado_ot(request, pk: int):
    """Cambia el estado de una OT de forma segura."""
    ot = get_object_or_404(RegistroMantenimiento, pk=pk)
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        try:
            ot.estado = nuevo_estado
            ot.save()
            messages.success(request, f"OT #{ot.id} actualizada al estado '{ot.get_estado_display()}'.")
        except Exception as e:
            messages.error(request, f"No se pudo cambiar el estado: {e}")
    
    return redirect("activos:ordenes_list")


@login_required
def mis_tareas(request):
    """Vista para operarios: muestra tareas asignadas en PENDIENTE / PRO."""
    qs = (
        RegistroMantenimiento.objects.filter(
            asignado_a=request.user, estado__in=[EstadoOT.PEN, EstadoOT.PRO]
        )
        .select_related("activo")
        .order_by("fecha_creacion")
    )
    return render(
        request,
        "activos/mis_tareas.html",
        {"ordenes": qs, "section": "tareas"},
    )


@login_required
@user_passes_test(es_supervisor)
def crear_ot_desde_alerta(request, pk: int):
    """
    Crea una OT preventiva a partir de una alerta.
    No se cierra la alerta automáticamente; se marca EN_PROCESO.
    Aplica mejor plantilla (o fallback).
    """
    alerta = get_object_or_404(AlertaMantenimiento, pk=pk)

    ot = RegistroMantenimiento.objects.create(
        activo=alerta.activo,
        tipo=TipoOT.PRE,
        estado=EstadoOT.PEN,
        creado_por=request.user,
    )

    _apply_best_template_or_fallback(ot)

    if getattr(alerta, "estado", "") != "CERRADA":
        alerta.estado = "EN_PROCESO"
        if hasattr(alerta, "actualizado_en"):
            alerta.actualizado_en = timezone.now()
            alerta.save(update_fields=["estado", "actualizado_en"])
        else:
            alerta.save(update_fields=["estado"])

    messages.success(
        request, f"Orden #{ot.id} creada para {alerta.activo.codigo}. La alerta quedó EN_PROCESO."
    )
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
