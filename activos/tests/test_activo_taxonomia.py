import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase

from activos.models import (
    Activo,
    Sistema,
    Subsistema,
    ItemMantenible,
    Parte,
)


@pytest.mark.django_db
class ActivoTaxonomiaViewsTests(TestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="supervisor",
            password="testpass",
            is_superuser=True,
            is_staff=True,
        )

    def _login(self):
        self.client.force_login(self.user)

    def test_crear_activo_con_taxonomia(self):
        self._login()
        url = reverse("activos:activo_create")

        data = {
            "codigo": "AC-01",
            "numero_activo": "0001",
            "nombre": "Activo Uno",
            "peso": "",
            "familia": "",
            "categoria": "",
            "estado": "",
            "ubicacion": "",
            "componentes": [],
            "sistemas-TOTAL_FORMS": "1",
            "sistemas-INITIAL_FORMS": "0",
            "sistemas-MIN_NUM_FORMS": "0",
            "sistemas-MAX_NUM_FORMS": "1000",
            "sistemas-0-id": "",
            "sistemas-0-tag": "SYS-01",
            "sistemas-0-codigo": "S01",
            "sistemas-0-nombre": "Sistema 1",
            "sistemas-0-DELETE": "",
            "sistemas-0-subsistemas-TOTAL_FORMS": "1",
            "sistemas-0-subsistemas-INITIAL_FORMS": "0",
            "sistemas-0-subsistemas-MIN_NUM_FORMS": "0",
            "sistemas-0-subsistemas-MAX_NUM_FORMS": "1000",
            "sistemas-0-subsistemas-0-id": "",
            "sistemas-0-subsistemas-0-tag": "SUB-01",
            "sistemas-0-subsistemas-0-codigo": "SS01",
            "sistemas-0-subsistemas-0-nombre": "Subsistema 1",
            "sistemas-0-subsistemas-0-DELETE": "",
            "sistemas-0-subsistemas-0-items-TOTAL_FORMS": "1",
            "sistemas-0-subsistemas-0-items-INITIAL_FORMS": "0",
            "sistemas-0-subsistemas-0-items-MIN_NUM_FORMS": "0",
            "sistemas-0-subsistemas-0-items-MAX_NUM_FORMS": "1000",
            "sistemas-0-subsistemas-0-items-0-id": "",
            "sistemas-0-subsistemas-0-items-0-tag": "ITEM-01",
            "sistemas-0-subsistemas-0-items-0-codigo": "IT01",
            "sistemas-0-subsistemas-0-items-0-nombre": "Item 1",
            "sistemas-0-subsistemas-0-items-0-DELETE": "",
            "sistemas-0-subsistemas-0-items-0-partes-TOTAL_FORMS": "1",
            "sistemas-0-subsistemas-0-items-0-partes-INITIAL_FORMS": "0",
            "sistemas-0-subsistemas-0-items-0-partes-MIN_NUM_FORMS": "0",
            "sistemas-0-subsistemas-0-items-0-partes-MAX_NUM_FORMS": "1000",
            "sistemas-0-subsistemas-0-items-0-partes-0-id": "",
            "sistemas-0-subsistemas-0-items-0-partes-0-tag": "PAR-01",
            "sistemas-0-subsistemas-0-items-0-partes-0-codigo": "P01",
            "sistemas-0-subsistemas-0-items-0-partes-0-nombre": "Parte 1",
            "sistemas-0-subsistemas-0-items-0-partes-0-DELETE": "",
        }

        response = self.client.post(url, data, follow=False)
        assert response.status_code == 302
        activo = Activo.objects.get(codigo="AC-01")
        sistema = Sistema.objects.get(activo=activo)
        subsistema = Subsistema.objects.get(sistema=sistema)
        item = ItemMantenible.objects.get(subsistema=subsistema)
        parte = Parte.objects.get(item=item)

        assert sistema.tag == "SYS-01"
        assert subsistema.tag == "SUB-01"
        assert item.tag == "ITEM-01"
        assert parte.tag == "PAR-01"

    def test_actualizar_activo_gestiona_altas_y_bajas(self):
        self._login()
        activo = Activo.objects.create(
            codigo="AC-02",
            numero_activo="0002",
            nombre="Activo Dos",
        )
        sistema = Sistema.objects.create(
            activo=activo,
            tag="SYS-OLD",
            codigo="SO",
            nombre="Sistema Antiguo",
        )
        subsistema = Subsistema.objects.create(
            sistema=sistema,
            tag="SUB-OLD",
            codigo="SSO",
            nombre="Subsistema Antiguo",
        )
        item = ItemMantenible.objects.create(
            subsistema=subsistema,
            tag="ITEM-OLD",
            codigo="ITO",
            nombre="Item Antiguo",
        )
        parte = Parte.objects.create(
            item=item,
            tag="PAR-OLD",
            codigo="PO",
            nombre="Parte Antiguo",
        )

        url = reverse("activos:activo_update", args=[activo.pk])
        data = {
            "codigo": "AC-02",
            "numero_activo": "0002",
            "nombre": "Activo Dos",
            "peso": "",
            "familia": "",
            "categoria": "",
            "estado": "",
            "ubicacion": "",
            "componentes": [],
            "sistemas-TOTAL_FORMS": "1",
            "sistemas-INITIAL_FORMS": "1",
            "sistemas-MIN_NUM_FORMS": "0",
            "sistemas-MAX_NUM_FORMS": "1000",
            "sistemas-0-id": str(sistema.id),
            "sistemas-0-tag": "SYS-OLD",
            "sistemas-0-codigo": "SO",
            "sistemas-0-nombre": "Sistema Actualizado",
            "sistemas-0-DELETE": "",
            "sistemas-0-subsistemas-TOTAL_FORMS": "1",
            "sistemas-0-subsistemas-INITIAL_FORMS": "1",
            "sistemas-0-subsistemas-MIN_NUM_FORMS": "0",
            "sistemas-0-subsistemas-MAX_NUM_FORMS": "1000",
            "sistemas-0-subsistemas-0-id": str(subsistema.id),
            "sistemas-0-subsistemas-0-tag": "SUB-OLD",
            "sistemas-0-subsistemas-0-codigo": "SSO",
            "sistemas-0-subsistemas-0-nombre": "Subsistema Actualizado",
            "sistemas-0-subsistemas-0-DELETE": "",
            "sistemas-0-subsistemas-0-items-TOTAL_FORMS": "1",
            "sistemas-0-subsistemas-0-items-INITIAL_FORMS": "1",
            "sistemas-0-subsistemas-0-items-MIN_NUM_FORMS": "0",
            "sistemas-0-subsistemas-0-items-MAX_NUM_FORMS": "1000",
            "sistemas-0-subsistemas-0-items-0-id": str(item.id),
            "sistemas-0-subsistemas-0-items-0-tag": "ITEM-OLD",
            "sistemas-0-subsistemas-0-items-0-codigo": "ITO",
            "sistemas-0-subsistemas-0-items-0-nombre": "Item Nuevo Nombre",
            "sistemas-0-subsistemas-0-items-0-DELETE": "",
            "sistemas-0-subsistemas-0-items-0-partes-TOTAL_FORMS": "2",
            "sistemas-0-subsistemas-0-items-0-partes-INITIAL_FORMS": "1",
            "sistemas-0-subsistemas-0-items-0-partes-MIN_NUM_FORMS": "0",
            "sistemas-0-subsistemas-0-items-0-partes-MAX_NUM_FORMS": "1000",
            "sistemas-0-subsistemas-0-items-0-partes-0-id": str(parte.id),
            "sistemas-0-subsistemas-0-items-0-partes-0-tag": "PAR-OLD",
            "sistemas-0-subsistemas-0-items-0-partes-0-codigo": "PO",
            "sistemas-0-subsistemas-0-items-0-partes-0-nombre": "Parte Antiguo",
            "sistemas-0-subsistemas-0-items-0-partes-0-DELETE": "on",
            "sistemas-0-subsistemas-0-items-0-partes-1-id": "",
            "sistemas-0-subsistemas-0-items-0-partes-1-tag": "PAR-NEW",
            "sistemas-0-subsistemas-0-items-0-partes-1-codigo": "PN",
            "sistemas-0-subsistemas-0-items-0-partes-1-nombre": "Parte Nueva",
            "sistemas-0-subsistemas-0-items-0-partes-1-DELETE": "",
        }

        response = self.client.post(url, data, follow=False)
        assert response.status_code == 302

        activo.refresh_from_db()
        sistema.refresh_from_db()
        subsistema.refresh_from_db()
        item.refresh_from_db()

        assert sistema.nombre == "Sistema Actualizado"
        assert subsistema.nombre == "Subsistema Actualizado"
        assert item.nombre == "Item Nuevo Nombre"
        assert not Parte.objects.filter(tag="PAR-OLD").exists()
        nueva_parte = Parte.objects.get(tag="PAR-NEW")
        assert nueva_parte.nombre == "Parte Nueva"
        assert nueva_parte.item == item

    def test_detalle_muestra_arbol_con_tags(self):
        activo = Activo.objects.create(
            codigo="AC-03",
            numero_activo="0003",
            nombre="Activo Tres",
        )
        sistema = Sistema.objects.create(
            activo=activo,
            tag="SYS-DET",
            codigo="SD",
            nombre="Sistema Detalle",
        )
        subsistema = Subsistema.objects.create(
            sistema=sistema,
            tag="SUB-DET",
            codigo="SSD",
            nombre="Subsistema Detalle",
        )
        item = ItemMantenible.objects.create(
            subsistema=subsistema,
            tag="ITEM-DET",
            codigo="ITD",
            nombre="Item Detalle",
        )
        Parte.objects.create(
            item=item,
            tag="PAR-DET",
            codigo="PD",
            nombre="Parte Detalle",
        )

        url = reverse("activos:detalle_activo_por_codigo", args=["AC-03"])
        response = self.client.get(url)
        assert response.status_code == 200
        self.assertContains(response, "SYS-DET")
        self.assertContains(response, "SUB-DET")
        self.assertContains(response, "ITEM-DET")
        self.assertContains(response, "PAR-DET")