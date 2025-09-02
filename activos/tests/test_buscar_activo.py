import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_buscar_por_numero_activo_redirige_a_detalle(client, activo):
    url = reverse("activos:buscar_activo", args=[activo.numero_activo])
    resp = client.get(url)
    assert resp.status_code == 302
    assert resp.url == reverse(
        "activos:detalle_activo_por_codigo", args=[activo.codigo]
    )


@pytest.mark.django_db
def test_busqueda_activo_inexistente_redirige_escaner(client):
    resp = client.get(reverse("activos:buscar_activo", args=["no-existe"]))
    assert resp.status_code == 302
    assert resp.url == reverse("escaner")

    resp = client.get(reverse("activos:buscar_activo", args=["no-existe"]), follow=True)
    assert resp.request["PATH_INFO"] == reverse("escaner")
    assert "Verifique el número del activo" in resp.content.decode()