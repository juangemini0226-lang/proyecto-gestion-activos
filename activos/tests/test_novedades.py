import pytest
from django.urls import reverse
from activos.models import Novedad, CatalogoFalla, RegistroMantenimiento


@pytest.mark.django_db
def test_registra_novedad(activo, user):
    falla = CatalogoFalla.objects.create(codigo="F1", nombre="Falla 1")
    nov = Novedad.objects.create(
        activo=activo,
        etapa="INICIO",
        descripcion="Se detectó algo",
        falla=falla,
        reportado_por=user,
    )
    assert nov.pk is not None


@pytest.mark.django_db
def test_escalado_por_regla(activo, user, settings):
    settings.NOVEDAD_FALLAS_CRITICAS = ["CRIT"]
    falla = CatalogoFalla.objects.create(codigo="CRIT", nombre="Critica")
    nov = Novedad.objects.create(
        activo=activo,
        etapa="INICIO",
        descripcion="Falla crítica",
        falla=falla,
        reportado_por=user,
    )
    nov.refresh_from_db()
    assert nov.orden_mantenimiento is not None
    assert RegistroMantenimiento.objects.filter(pk=nov.orden_mantenimiento_id).exists()


@pytest.mark.django_db
def test_detalle_activo_muestra_formulario(activo, client, user):
    client.force_login(user)
    url = reverse("activos:detalle_activo_por_codigo", args=[activo.codigo])
    resp = client.get(url)
    assert resp.status_code == 200
    assert b"Reportar Novedad" in resp.content