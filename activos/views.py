# activos/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.views import es_supervisor

from horometro.models import AlertaMantenimiento

from .forms import (
    ActivoForm,
    AsignarOTForm,
    RegistroMantenimientoForm,
    NovedadForm,
    CrearOTDesdeNovedadForm,
)
from .models import (
    Activo,
    DetalleMantenimiento,
    EstadoOT,
    PlantillaChecklist,
    PrioridadOT,
    RegistroMantenimiento,
    TareaMantenimiento,
    TipoOT,
    Ubicacion,
    Novedad,
)


def redirect_buscar_a_detalle(request, codigo: str):
    """Pequeño atajo que redirige un código o número de activo a su detalle."""
    codigo = codigo.strip()
    activo = Activo.objects.filter(Q(codigo=codigo) | Q(numero_activo=codigo)).first()
    if not activo:
        messages.error(request, "Activo no encontrado")
        return redirect(request.META.get("HTTP_REFERER") or "activos:activos_list")
    return redirect("activos:detalle_activo_por_codigo", codigo=activo.codigo)


@login_required
def activos_list(request):
    """Listado sencillo de activos."""
    activos = Activo.objects.all()
    context = {"activos": activos, "section": "activos"}
    return render(request, "activos/activos_list.html", context)


def _apply_best_template_or_fallback(ot: RegistroMantenimiento):
    """Aplica la mejor plantilla disponible o genera un checklist base."""
    plantilla = (
        PlantillaChecklist.objects.filter(activo=ot.activo, vigente=True).first()
        or PlantillaChecklist.objects.filter(familia=ot.activo.familia, vigente=True).first()
        or PlantillaChecklist.objects.filter(falla=ot.falla, vigente=True).first()
    )

    if plantilla:
        ot.aplicar_plantilla(plantilla)
        return "plantilla"

    # Fallback: generar checklist base con todas las tareas si no hay detalles
    if not ot.detalles.exists():
        DetalleMantenimiento.objects.bulk_create(
            [
                DetalleMantenimiento(registro=ot, tarea=t)
                for t in TareaMantenimiento.objects.all()
            ]
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

    # 1) Filtros por defecto + los guardados en sesión
    defaults = {
        "estado": "",
        "tipo": "",
        "q": "",
        "asignado": "",
        "vencimiento": "",
        "ubicacion": "",
        "prioridad": "",
    }
    filtros = {**defaults, **request.session.get("filtros_ot", {})}

    # 2) Si es POST, actualizar filtros en sesión (PRG) y redirigir
    if request.method == "POST":
        filtros = {
            "estado": request.POST.get("estado", ""),
            "tipo": request.POST.get("tipo", ""),
            "q": request.POST.get("q", ""),
            "asignado": request.POST.get("asignado", ""),
            "vencimiento": request.POST.get("vencimiento", ""),
            "ubicacion": request.POST.get("ubicacion", ""),
            "prioridad": request.POST.get("prioridad", ""),
        }
        request.session["filtros_ot"] = filtros
        return redirect("activos:ordenes_list")

    # 3) Construcción del queryset base
    qs = RegistroMantenimiento.objects.select_related("activo").all()
    novedades_qs = (
        Novedad.objects.select_related("activo")
        .filter(orden_mantenimiento__isnull=True)
    )
    #  4) Aplicación de filtros
    if filtros.get("estado"):
        if filtros["estado"] == EstadoOT.SIN:
            qs = qs.none()
        else:
            qs = qs.filter(estado=filtros["estado"])

    if filtros.get("tipo"):
        qs = qs.filter(tipo=filtros["tipo"])

    if filtros.get("asignado"):
        # Permite filtrar por asignadas, sin asignar o por ID específico
        if filtros["asignado"] == "SI":
            qs = qs.filter(asignado_a__isnull=False)
        elif filtros["asignado"] == "NO":
            qs = qs.filter(asignado_a__isnull=True)
        else:
            qs = qs.filter(asignado_a_id=filtros["asignado"])

    if filtros.get("ubicacion"):
        qs = qs.filter(activo__ubicacion_id=filtros["ubicacion"])

    if filtros.get("prioridad"):
        qs = qs.filter(prioridad=filtros["prioridad"])

    if filtros.get("vencimiento"):
        # Ejemplo: fecha límite <= vencimiento (YYYY-MM-DD)
        qs = qs.filter(vencimiento__date__lte=filtros["vencimiento"])

    if filtros.get("q"):
        q = filtros["q"]
        qs = qs.filter(
            Q(id__icontains=q)
            | Q(activo__codigo__icontains=q)
            | Q(activo__nombre__icontains=q)
            | Q(asignado_a__username__icontains=q)
        )
        novedades_qs = novedades_qs.filter(
            Q(id__icontains=q)
            | Q(activo__codigo__icontains=q)
            | Q(activo__nombre__icontains=q)
            | Q(descripcion__icontains=q)
        )

    # 5) Unir órdenes y novedades sin OT
    items = [
        (ot, False) for ot in qs.order_by("-fecha_creacion")
    ] + [
        (nov, True) for nov in novedades_qs.order_by("-fecha")
    ]
    items.sort(
        key=lambda tup: getattr(tup[0], "fecha_creacion", None)
        or getattr(tup[0], "fecha", None),
        reverse=True,
    )

    # Paginación y render
    paginator = Paginator(items, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "ordenes": page_obj.object_list,
        "section": "mantenimiento",
        "ESTADOS": EstadoOT.choices,
        "PRIORIDADES": PrioridadOT.choices,
        "ubicaciones": Ubicacion.objects.all(),
        "filtros": filtros,
    }
    return render(request, "activos/ordenes_list.html", context)


@login_required
@user_passes_test(es_supervisor)
def activo_create(request):
    """Crea un nuevo activo."""
    form = ActivoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Activo creado correctamente.")
        return redirect("activos:activos_list")
    return render(request, "activos/activo_form.html", {"form": form, "section": "activos"})


@login_required
@user_passes_test(es_supervisor)
def activo_update(request, pk: int):
    """Actualiza un activo existente."""
    activo = get_object_or_404(Activo, pk=pk)
    form = ActivoForm(request.POST or None, instance=activo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Activo actualizado correctamente.")
        return redirect("activos:activos_list")
    return render(
        request,
        "activos/activo_form.html",
        {"form": form, "activo": activo, "section": "activos"},
    )


@login_required
def mis_tareas(request):
    """Lista de órdenes asignadas al usuario actual."""
    ordenes = (
        RegistroMantenimiento.objects.select_related("activo")
        .filter(asignado_a=request.user)
        .order_by("-fecha_creacion")
    )
    return render(
        request,
        "activos/mis_tareas.html",
        {"ordenes": ordenes, "section": "mantenimiento"},
    )


@login_required
@user_passes_test(es_supervisor)
def agendar_mantenimiento(request):
    """Crea una OT en estado PEN usando el RegistroMantenimientoForm."""
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


@login_required
@user_passes_test(es_supervisor)
def crear_ot_desde_alerta(request, pk: int):
    alerta = get_object_or_404(
        AlertaMantenimiento.objects.select_related("activo"), pk=pk
    )

    ot = RegistroMantenimiento.objects.create(
        activo=alerta.activo,
        creado_por=request.user,
        estado=EstadoOT.PEN,
        tipo=TipoOT.PRE,
        titulo=f"Mantenimiento desde alerta #{alerta.id}",
    )

    _apply_best_template_or_fallback(ot)

    alerta.estado = "EN_PROCESO"
    alerta.save(update_fields=["estado"])

    messages.success(
        request,
        f"Orden #{ot.id} creada para {alerta.activo.codigo}. La alerta quedó EN_PROCESO.",
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
def checklist_mantenimiento(request, pk: int):
    """Muestra y gestiona el checklist de una OT."""
    ot = get_object_or_404(
        RegistroMantenimiento.objects.select_related("activo"), pk=pk
    )
    _ensure_checklist_exists(ot)

    items = ot.detalles.select_related("tarea").prefetch_related("evidencias")

    # Si más adelante se procesan formularios de evidencias, hacerlo aquí.
    # if request.method == "POST":
    #     ...
    #     return redirect("activos:checklist_mantenimiento", pk=pk)

    return render(
        request,
        "activos/checklist_mantenimiento.html",
        {"ot": ot, "items_checklist": items},
    )


@login_required
def cambiar_estado_ot(request, pk: int):
    """Cambia el estado de una OT si la transición es válida."""
    ot = get_object_or_404(RegistroMantenimiento, pk=pk)

    if not (es_supervisor(request.user) or ot.asignado_a_id == request.user.id):
        messages.error(request, "No tiene permiso para actualizar esta OT.")
        return redirect("activos:ordenes_list")

    if request.method == "POST":
        nuevo = request.POST.get("estado")
        if nuevo == "COM":
            nuevo = EstadoOT.CER
        try:
            ot.transition_to(nuevo, usuario=request.user)
            messages.success(request, "Estado actualizado correctamente.")
        except Exception as exc:  # defensa
            messages.error(request, str(exc))

    return redirect(request.META.get("HTTP_REFERER") or "activos:ordenes_list")


def detalle_activo_por_codigo(request, codigo: str):
    """Detalle de un activo buscado por su código."""
    activo = get_object_or_404(
        Activo,
        Q(codigo__iexact=codigo) | Q(numero_activo__iexact=codigo),
    )
    ots = (
        RegistroMantenimiento.objects.filter(activo=activo)
        .select_related("activo")
        .order_by("-id")[:20]
    )
    novedades = activo.novedades.select_related("orden_mantenimiento").order_by("-fecha")

    if request.method == "POST":
        form = NovedadForm(request.POST, request.FILES)
        if form.is_valid():
            novedad = form.save(commit=False)
            novedad.activo = activo
            if request.user.is_authenticated:
                novedad.reportado_por = request.user
            novedad.save()
            return redirect("activos:detalle_activo_por_codigo", codigo=codigo)
    else:
        form = NovedadForm()

    ctx = {
        "activo": activo,
        "ots": ots,
        "novedades": novedades,
        "novedad_form": form,
    }
    return render(request, "activos/detalle_activo.html", ctx)


@login_required
def novedad_detail(request, pk: int):
    novedad = get_object_or_404(
        Novedad.objects.select_related("activo", "orden_mantenimiento"), pk=pk
    )
    form = None
    if novedad.orden_mantenimiento_id is None:
        if request.method == "POST":
            form = CrearOTDesdeNovedadForm(request.POST)
            if form.is_valid():
                ot = form.save(commit=False)
                ot.activo = novedad.activo
                ot.creado_por = request.user
                ot.estado = EstadoOT.PEN
                ot.tipo = TipoOT.COR
                if novedad.falla_id and not ot.falla_id:
                    ot.falla = novedad.falla
                ot.save()
                _apply_best_template_or_fallback(ot)
                novedad.orden_mantenimiento = ot
                novedad.save(update_fields=["orden_mantenimiento"])
                messages.success(
                    request,
                    f"OT #{ot.id} creada para {novedad.activo.codigo}.",
                )
                return redirect("activos:checklist_mantenimiento", pk=ot.pk)
        else:
            form = CrearOTDesdeNovedadForm(
                initial={
                    "titulo": f"Novedad #{novedad.id} - {novedad.activo.codigo}",
                    "descripcion": novedad.descripcion,
                }
            )

    ctx = {"novedad": novedad, "form": form}
    return render(request, "activos/novedad_detail.html", ctx)


@login_required
def iniciar_mantenimiento(request, activo_id: int):
    """Redirige a la vista de agendar con el activo preseleccionado."""
    get_object_or_404(Activo, pk=activo_id)
    url = f"{reverse('activos:agendar_mantenimiento')}?activo={activo_id}"
    return redirect(url)
