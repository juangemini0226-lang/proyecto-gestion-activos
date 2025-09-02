import pytest
from django.urls import reverse
from activos.models import Activo


@pytest.mark.django_db
def test_busqueda_por_codigo_o_numero_activo_ignora_mayusculas(client):
    activo = Activo.objects.create(
        codigo="AA-01",
        numero_activo="BB-02",
        nombre="Equipo",
    )

    # Buscar por código en minúsculas
    resp = client.get(reverse("activos:detalle_activo_por_codigo", args=["aa-01"]))
    assert resp.status_code == 200
    assert resp.context["activo"] == activo

    # Buscar por número de activo en minúsculas
    resp = client.get(reverse("activos:detalle_activo_por_codigo", args=["bb-02"]))
    assert resp.status_code == 200
    assert resp.context["activo"] == activo

    # Redirección normaliza el código
    resp = client.get(reverse("activos:buscar_activo", args=["bb-02"]))
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/detalle/AA-01/")