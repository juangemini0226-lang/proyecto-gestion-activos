# activos/tests/conftest.py
import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from activos.models import (
    Activo,
    RegistroMantenimiento,
    TareaMantenimiento,
    DetalleMantenimiento,
    EstadoOT,
    TipoOT,
)


@pytest.fixture
def user(django_user_model):
    u = django_user_model.objects.create_user(
        username="operario1", password="x", is_active=True
    )
    # (Opcional) crea/añade al grupo Operarios por si lo necesitas en otras vistas
    grp, _ = Group.objects.get_or_create(name="Operarios")
    u.groups.add(grp)
    return u


@pytest.fixture
def activo():
    return Activo.objects.create(
        codigo="AC-001",
        numero_activo="1001",
        nombre="Compresor principal",
        peso=100.0,
    )


@pytest.fixture
def ot_pen_asignada(activo, user):
    """OT en PEN ya asignada a un operario (lista para pasar a PRO)."""
    return RegistroMantenimiento.objects.create(
        activo=activo,
        estado=EstadoOT.PEN,
        tipo=TipoOT.PRE,
        creado_por=user,
        asignado_a=user,
    )


@pytest.fixture
def ot_en_revision(activo, user):
    """
    OT con checklist completo para poder pasar a REV y luego cerrar.
    Se arranca en PRO, se completan tareas y se transiciona a REV.
    """
    ot = RegistroMantenimiento.objects.create(
        activo=activo,
        estado=EstadoOT.PEN,
        tipo=TipoOT.PRE,
        creado_por=user,
        asignado_a=user,
    )
    # a) pasar a PRO
    ot.transition_to(EstadoOT.PRO, usuario=user)

    # b) checklist: crear tareas maestras si no hay y marcarlas completas
    if TareaMantenimiento.objects.count() == 0:
        TareaMantenimiento.objects.create(nombre="Inspección general")
        TareaMantenimiento.objects.create(nombre="Limpieza de filtros")

    for t in TareaMantenimiento.objects.all():
        DetalleMantenimiento.objects.create(
            registro=ot, tarea=t, completado=True
        )

    # c) pasar a REV (requiere checklist completo)
    ot.transition_to(EstadoOT.REV, usuario=user)
    ot.refresh_from_db()
    return ot
