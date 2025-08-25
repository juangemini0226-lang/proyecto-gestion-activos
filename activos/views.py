# activos/views.py
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    Activo,
    RegistroMantenimiento,
    TareaMantenimiento,
    DetalleMantenimiento,
    EstadoOT,
    TipoOT,
    PlantillaChecklist,
    PlantillaItem,  # para "guardar como plantilla"
)
from .forms import (
    CargarPlantillaForm,
    GuardarComoPlantillaForm,
    AddTareaRapidaForm,
)
from horometro.models import AlertaMantenimiento, LecturaHorometro

User = get_user_model()


# ===================== Helpers de permisos =====================
def es_supervisor(u):
    """Pertenece al grupo Supervisor o es superusuario."""
    return u.is_superuser or u.groups.filter(name__iexact="Supervisor").exists()


def operarios_qs():
    """QuerySet de usuarios activos del grupo Operarios."""
    return (
        User.objects.filter(is_active=True, groups__name__iexact="Operarios")
        .order_by("username")
    )


# ===================== Formularios ligeros (inline) =====================
class AsignarOTForm(forms.Form):
    operario = forms.ModelChoiceField(
        queryset=User.objects.none(),  # se carga en __init__
        required=True,
        label="Asignar a",
        help_text="Selecciona un operario.",
    )
    comentario = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Comentario (opcional)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["operario"].queryset = operarios_qs()


class AgendarOTForm(forms.Form):
    activo = forms.ModelChoiceField(queryset=Activo.objects.none(), label="Activo")
    tipo = forms.ChoiceField(choices=TipoOT.choices, initial=TipoOT.PRE, label="Tipo")
    asignado_a = forms.ModelChoiceField(
        queryset=User.objects.none(), required=False, label="Asignado a"
    )
    notas = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Notas",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activo"].queryset = Activo.objects.order_by("codigo")
        self.fields["asignado_a"].queryset = operarios_qs()


# ===================== Utilidades de negocio =====================
def _apply_best_template_or_fallback(ot: RegistroMantenimiento):
    """
    Intenta aplicar la mejor plantilla (Activo → Familia → Global).
    Si no encuentra, replica checklist con todas las tareas maestras como fallback.
    """
    plant = PlantillaChecklist.mejor_coincidencia(
        activo=ot.activo, tipo=ot.tipo, falla=getattr(ot, "falla", None)
    )
    if plant:
        ot.aplicar_plantilla(plant)
        return "plantilla"
    # Fallback: todas las tareas maestras (sin metadatos)
    if not ot.detalles.exists():
        DetalleMantenimiento.objects.bulk_create(
            [DetalleMantenimiento(registro=ot, tarea=t) for t in TareaMantenimiento.objects.all()],
            batch_size=200,
        )
    return "fallback"


def _ensure_checklist_exists(ot: RegistroMantenimiento):
    """Garantiza que la OT tenga checklist (plantilla o fallback)."""
    if not ot.detalles.exists():
        _apply_best_template_or_fallback(ot)


# ===================== Vistas básicas =====================
@login_required
def detalle_activo_por_codigo(request, codigo: str):
    """Ficha de activo (por código) + últimas lecturas de horómetro."""
    activo = get_object_or_404(Activo, codigo__iexact=codigo)
    lecturas = (
        LecturaHorometro.objects.filter(activo=activo)
        .order_by("-anio", "-semana")[:12]
    )
    return render(
        request, "activos/detalle_activo.html", {"activo": activo, "lecturas": lecturas}
    )


@login_required
def iniciar_mantenimiento(request, activo_id: int):
    """
    Crea una OT PRE, aplica mejor plantilla (o fallback), pasa a PRO y redirige al checklist.
    """
    activo = get_object_or_404(Activo, pk=activo_id)
    ot = RegistroMantenimiento.objects.create(
        activo=activo,
        tipo=TipoOT.PRE,
        creado_por=request.user,
        asignado_a=(
            request.user if request.user.groups.filter(name__iexact="Operarios").exists() else None
        ),
    )

    origen = _apply_best_template_or_fallback(ot)

    # Pasar a PRO con sellos (usa método centralizado)
    try:
        ot.transition_to(EstadoOT.PRO, usuario=request.user)
    except Exception as e:
        messages.error(request, f"No se pudo iniciar la OT: {e}")
        return redirect("activos:ordenes_list")

    txt = "Plantilla aplicada." if origen == "plantilla" else "Checklist base generado."
    messages.success(request, f"Orden iniciada para {activo.codigo}. {txt}")
    return redirect("activos:checklist_mantenimiento", registro_id=ot.id)


@login_required
def checklist_mantenimiento(request, registro_id: int):
    """
    Vista del checklist de la OT.
    Acciones en POST:
      - guardar_checklist: guarda checks/observaciones.
      - cargar_plantilla: aplica plantilla seleccionada.
      - guardar_plantilla: registra checklist actual como nueva plantilla.
      - enviar_revision: intenta transición a REV (valida % avance).
      - add_tarea_rapida: agrega una tarea al checklist (existente o nueva).
    """
    ot = get_object_or_404(
        RegistroMantenimiento.objects.select_related("activo"), pk=registro_id
    )

    # Asegurar que exista checklist
    _ensure_checklist_exists(ot)

    tareas = ot.detalles.select_related("tarea").all()

    # Formularios secundarios
    cargar_form = CargarPlantillaForm(request.POST or None, activo=ot.activo, tipo=ot.tipo, falla=getattr(ot, "falla", None))
    guardar_form = GuardarComoPlantillaForm(request.POST or None)
    add_tarea_form = AddTareaRapidaForm(request.POST or None)

    if request.method == "POST":
        # 0) Agregar tarea rápida (antes de guardar checklist)
        if "add_tarea_rapida" in request.POST and add_tarea_form.is_valid():
            t = add_tarea_form.cleaned_data.get("tarea_existente")
            nombre_nuevo = (add_tarea_form.cleaned_data.get("nueva_tarea") or "").strip()

            if not t and nombre_nuevo:
                t, _ = TareaMantenimiento.objects.get_or_create(nombre=nombre_nuevo)

            if t:
                max_orden = ot.detalles.aggregate(m=Max("orden")).get("m") or 0
                DetalleMantenimiento.objects.create(
                    registro=ot, tarea=t, orden=max_orden + 10
                )
                messages.success(request, f"Tarea '{t.nombre}' agregada al checklist.")
            return redirect("activos:checklist_mantenimiento", registro_id=registro_id)

        # 1) Guardar checklist (checks + observaciones)
        if "guardar_checklist" in request.POST:
            for det in tareas:
                det.completado = bool(request.POST.get(f"tarea_{det.id}"))
                det.observaciones = (request.POST.get(f"obs_{det.id}") or "").strip() or None
                det.save(update_fields=["completado", "observaciones"])
            messages.success(request, "Checklist actualizado.")
            return redirect("activos:checklist_mantenimiento", registro_id=registro_id)

        # 2) Cargar plantilla
        if "cargar_plantilla" in request.POST and cargar_form.is_valid():
            pl = cargar_form.cleaned_data["plantilla"]
            ot.aplicar_plantilla(pl)
            messages.success(request, f"Plantilla '{pl.nombre}' aplicada a la OT.")
            return redirect("activos:checklist_mantenimiento", registro_id=registro_id)

        # 3) Guardar como plantilla
        if "guardar_plantilla" in request.POST and guardar_form.is_valid():
            nombre = guardar_form.cleaned_data["nombre"].strip()
            es_global = guardar_form.cleaned_data["es_global"]

            nueva = PlantillaChecklist.objects.create(
                nombre=nombre,
                tipo=ot.tipo,
                es_global=es_global,
                activo=(None if es_global else ot.activo),
                # si en tu modelo tienes familia/falla/vigente/version, puedes setearlos aquí
                # familia=ot.activo.familia if aplicar_a_familia else None,
                # falla=ot.falla,
                # vigente=True,
                # version=1,
                creado_por=request.user,
            )
            items = []
            for det in ot.detalles.select_related("tarea").all():
                items.append(
                    PlantillaItem(
                        plantilla=nueva,
                        tarea=det.tarea,
                        obligatorio=getattr(det, "obligatorio", False),
                        requiere_evidencia=getattr(det, "requiere_evidencia", False),
                        orden=getattr(det, "orden", 0),
                        notas_sugeridas=det.observaciones or "",
                    )
                )
            if items:
                PlantillaItem.objects.bulk_create(items, batch_size=200)

            messages.success(request, f"Plantilla '{nueva.nombre}' creada.")
            return redirect("activos:checklist_mantenimiento", registro_id=registro_id)

        # 4) Enviar a revisión
        if "enviar_revision" in request.POST or request.POST.get("accion") == "revision":
            try:
                ot.transition_to(EstadoOT.REV, usuario=request.user)
                messages.success(request, "Checklist enviado a revisión.")
            except Exception as e:
                messages.error(request, f"No se pudo enviar a revisión: {e}")
            return redirect("activos:checklist_mantenimiento", registro_id=registro_id)

    return render(
        request,
        "activos/checklist_mantenimiento.html",
        {
            "ot": ot,
            "tareas": tareas,
            "cargar_form": cargar_form,
            "guardar_form": guardar_form,
            "add_tarea_form": add_tarea_form,
        },
    )


@login_required
@user_passes_test(es_supervisor)
def agendar_mantenimiento(request):
    """
    Crea una OT en estado PEN (planificada). Opcional: asignar a operario.
    Aplica mejor plantilla (o fallback) para dejar checklist listo.
    """
    if request.method == "POST":
        form = AgendarOTForm(request.POST)
        if form.is_valid():
            ot = RegistroMantenimiento.objects.create(
                activo=form.cleaned_data["activo"],
                tipo=form.cleaned_data["tipo"],
                estado=EstadoOT.PEN,
                creado_por=request.user,
                asignado_a=form.cleaned_data.get("asignado_a") or None,
            )

            origen = _apply_best_template_or_fallback(ot)
            txt = "Plantilla aplicada." if origen == "plantilla" else "Checklist base generado."
            messages.success(request, f"Orden creada (#{ot.id}). {txt}")
            return redirect("activos:ordenes_list")
    else:
        form = AgendarOTForm()

    return render(request, "activos/agendar_mantenimiento.html", {"form": form})


# ===================== Gestión de OT (listado, mis tareas, acciones) =====================

FILTRO_SESSION_KEY = "filtros_ordenes"


def _leer_filtros(request):
    """Lee y persiste filtros en sesión (POST guarda; GET lee)."""
    if request.method == "POST":
        filtros = {
            "estado": (request.POST.get("estado") or "").strip().upper(),
            "tipo": (request.POST.get("tipo") or "").strip().upper(),
            "q": (request.POST.get("q") or "").strip(),
        }
        request.session[FILTRO_SESSION_KEY] = filtros
        return filtros
    return request.session.get(FILTRO_SESSION_KEY, {"estado": "", "tipo": "", "q": ""})


@login_required
@user_passes_test(es_supervisor)
def ordenes_list(request):
    """Listado de órdenes (supervisor) con filtros persistentes y paginación."""
    filtros = _leer_filtros(request)

    qs = (
        RegistroMantenimiento.objects.select_related(
            "activo", "asignado_a", "creado_por", "completado_por"
        )
        .all()
        .order_by("-fecha_creacion")
    )

    if filtros["estado"]:
        qs = qs.filter(estado=filtros["estado"])
    if filtros["tipo"]:
        qs = qs.filter(tipo=filtros["tipo"])
    if filtros["q"]:
        q = filtros["q"]
        qs = qs.filter(
            Q(id__icontains=q)
            | Q(activo__codigo__icontains=q)
            | Q(activo__nombre__icontains=q)
            | Q(asignado_a__username__icontains=q)
        )

    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "activos/ordenes_list.html",
        {
            "page_obj": page_obj,            # para paginación
            "ordenes": page_obj.object_list, # compatibilidad con plantilla actual
            "filtros": filtros,
            "estado": filtros["estado"],     # compat: selects del template
            "tipo": filtros["tipo"],
            "q": filtros["q"],
            "ESTADOS": EstadoOT.choices,
        },
    )


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
