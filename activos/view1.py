# activos/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.urls import reverse
# --- Imports de Modelos (Organizados) ---
from .models import (
    Activo,
    RegistroMantenimiento,
    TareaMantenimiento,
    DetalleMantenimiento,
    EstadoOT,
    TipoOT,
    PlantillaChecklist,
)
# --- Imports de Formularios (Organizados) ---
from .forms import (
    RegistroMantenimientoForm,
    EvidenciaDetalleForm,
    CargarPlantillaForm,
    GuardarComoPlantillaForm,
    AddTareaRapidaForm,
    AsignarOTForm, # Se movió a forms.py, asumimos que está ahí
)
from horometro.models import AlertaMantenimiento, LecturaHorometro


def redirect_buscar_a_detalle(request, codigo: str):
    return redirect("activos:detalle_activo_por_codigo", codigo=codigo)

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
    # (Tu código de filtros y paginación aquí... se mantiene igual)
    qs = RegistroMantenimiento.objects.select_related("activo", "asignado_a").all()
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    context = {
        "page_obj": page_obj,
        "ordenes": page_obj.object_list,
        # ... otros filtros que uses ...
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

            origen = _apply_best_template_or_fallback(ot)
            txt = "Plantilla aplicada." if origen == "plantilla" else "Checklist base generado."
            messages.success(request, f"Orden creada (#{ot.id}). {txt}")
            return redirect("activos:ordenes_list")
    else:
        form = RegistroMantenimientoForm()

    return render(request, "activos/agendar_mantenimiento.html", {"form": form})

@login_required
def checklist_mantenimiento(request, pk: int):
    """
    Vista del checklist de la OT. Maneja la actualización y la subida de evidencias.
    """
    ot = get_object_or_404(RegistroMantenimiento, pk=pk)
    _ensure_checklist_exists(ot)
    
    items_checklist = ot.detalles.select_related("tarea").prefetch_related("evidencias").all()

    if request.method == "POST":
        # Acción: Subir una evidencia
        if 'upload_evidencia' in request.POST:
            item_id = request.POST.get('detalle_id')
            item_detalle = get_object_or_404(DetalleMantenimiento, pk=item_id)
            form_evidencia = EvidenciaDetalleForm(request.POST, request.FILES)

            if form_evidencia.is_valid():
                evidencia = form_evidencia.save(commit=False)
                evidencia.detalle_mantenimiento = item_detalle
                evidencia.subido_por = request.user
                
                archivo_nombre = evidencia.archivo.name.lower()
                evidencia.tipo = 'IMG' if archivo_nombre.endswith(('.png', '.jpg', '.jpeg')) else 'FILE'
                evidencia.save()
                messages.success(request, f"Evidencia subida para '{item_detalle.tarea.nombre}'.")
            else:
                messages.error(request, "Error al subir la evidencia.")
            return redirect("activos:checklist_mantenimiento", pk=pk)

        # Acción: Guardar el estado de los checkboxes y observaciones
        elif "guardar_checklist" in request.POST:
            for item in items_checklist:
                item.completado = f'tarea_{item.id}' in request.POST
                item.observaciones = (request.POST.get(f"obs_{item.id}") or "").strip()
                item.save(update_fields=["completado", "observaciones"])
            messages.success(request, "Checklist actualizado.")
            return redirect("activos:checklist_mantenimiento", pk=pk)

        # ... Aquí puedes integrar la lógica para tus otros formularios si los necesitas
        # (CargarPlantillaForm, GuardarComoPlantillaForm, etc.)
    
    # Preparar formularios para el contexto
    context = {
        "ot": ot,
        "items_checklist": items_checklist,
        "upload_form": EvidenciaDetalleForm(),
        "cargar_form": CargarPlantillaForm(activo=ot.activo, tipo=ot.tipo),
        "guardar_form": GuardarComoPlantillaForm(),
        "add_tarea_form": AddTareaRapidaForm(),
    }
    return render(request, "activos/checklist_mantenimiento.html", context)


@login_required
@user_passes_test(es_supervisor)
def cambiar_estado_ot(request, pk: int):
    """Cambia el estado de una OT de forma segura."""
    ot = get_object_or_404(RegistroMantenimiento, pk=pk)
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        try:
            # Aquí deberías llamar a la lógica de transición de tu modelo si la tienes
            # Por ejemplo: ot.transition_to(nuevo_estado, usuario=request.user)
            ot.estado = nuevo_estado
            ot.save()
            messages.success(request, f"OT #{ot.id} actualizada al estado '{ot.get_estado_display()}'.")
        except Exception as e:
            messages.error(request, f"No se pudo cambiar el estado: {e}")
    
    # Redirige a la lista general o al detalle, según prefieras
    return redirect("activos:ordenes_list")

# El resto de tus vistas (mis_tareas, asignar_ot, etc.) se mantienen como estaban.
# Solo asegúrate de que los redirects apunten a las URLs correctas.


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
    return render(request, "activos/mis_tareas.html", {"ordenes": qs})


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
    ot = get_object_or_404(
        RegistroMantenimiento.objects.select_related("activo"), pk=pk
    )

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
@user_passes_test(es_supervisor)
def cambiar_estado_ot(request, pk: int):
    """
    Cambia el estado de una OT (PEN → PRO → REV → CER) usando transition_to().
    Controla sellos y validaciones (asignación, checklist, etc).
    """
    ot = get_object_or_404(RegistroMantenimiento, pk=pk)

    if request.method != "POST":
        messages.error(request, "Método no permitido.")
        return redirect("activos:ordenes_list")

    nuevo = (request.POST.get("estado") or "").upper()
    validos = {val for val, _ in EstadoOT.choices}
    if nuevo not in validos:
        messages.error(request, "Estado inválido.")
        return redirect("activos:ordenes_list")

    try:
        ot.transition_to(nuevo, usuario=request.user, motivo=request.POST.get("comentario", ""))
    except Exception as e:
        messages.error(request, f"No se pudo cambiar el estado: {e}")
        return redirect("activos:ordenes_list")

    messages.success(request, f"OT #{ot.id} ahora está en '{ot.get_estado_display()}'.")
    return redirect("activos:ordenes_list")


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

def iniciar_mantenimiento(request, activo_id: int):
    """
    Wrapper liviano: valida que el activo exista y redirige a la vista de agendar
    con el activo preseleccionado por querystring (?activo=<id>).
    Evita acoplarse a campos específicos de RegistroMantenimiento.
    """
    get_object_or_404(Activo, pk=activo_id)
    url = f"{reverse('activos:agendar_mantenimiento')}?activo={activo_id}"
    return redirect(url)