# tests/test_ot_transiciones.py
import pytest
from django.utils import timezone
from activos.models import RegistroMantenimiento, EstadoOT

@pytest.mark.django_db
def test_transicion_pen_a_pro(ot_pen_asignada, user):
    ot = ot_pen_asignada
    ot.transition_to(EstadoOT.PRO, usuario=user)
    assert ot.estado == EstadoOT.PRO

@pytest.mark.django_db
def test_cierre_ot_fija_fecha_fin_y_usuario(ot_en_revision, user):
    ot = ot_en_revision
    ot.transition_to(EstadoOT.CER, usuario=user)
    assert ot.estado == EstadoOT.CER
    assert ot.fecha_fin is not None
    assert ot.cerrado_por == user
