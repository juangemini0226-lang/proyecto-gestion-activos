import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_buscar_por_numero_activo_redirige_a_detalle(client, activo):
    url = reverse("activos:buscar_activo", args=[activo.numero_activo])
    resp = client.get(url)
    assert resp.status_code == 302
    assert resp.url == reverse("activos:detalle_activo_por_codigo", args=[activo.codigo])