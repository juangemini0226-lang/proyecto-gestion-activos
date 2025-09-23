import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from openpyxl import Workbook

from activos.models import (
    Activo,
    Sistema,
    Subsistema,
    ItemMantenible,
    Parte,
)
from activos.importers import TaxonomiaImportError, TaxonomiaImporter


TAXONOMY_HEADERS = [
    "Sistema Tag",
    "Sistema Código",
    "Sistema Nombre",
    "Subsistema Tag",
    "Subsistema Código",
    "Subsistema Nombre",
    "Item Tag",
    "Item Código",
    "Item Nombre",
    "Parte Tag",
    "Parte Código",
    "Parte Nombre",
]


def build_taxonomia_upload(rows, headers=None, filename="taxonomia.xlsx"):
    """Genera un archivo Excel en memoria con la jerarquía recibida."""

    wb = Workbook()
    ws = wb.active
    headers = headers or TAXONOMY_HEADERS
    ws.append(headers)
    for row in rows:
        ws.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    return SimpleUploadedFile(
        filename,
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def snapshot_taxonomia(activo):
    """Devuelve una representación anidada de la taxonomía del activo."""

    jerarquia = []
    for sistema in activo.sistemas.order_by("tag"):
        sistema_data = {
            "tag": sistema.tag,
            "codigo": sistema.codigo,
            "nombre": sistema.nombre,
            "subsistemas": [],
        }
        for subsistema in sistema.subsistemas.order_by("tag"):
            subsistema_data = {
                "tag": subsistema.tag,
                "codigo": subsistema.codigo,
                "nombre": subsistema.nombre,
                "items": [],
            }
            for item in subsistema.items.order_by("tag"):
                item_data = {
                    "tag": item.tag,
                    "codigo": item.codigo,
                    "nombre": item.nombre,
                    "partes": [],
                }
                for parte in item.partes.order_by("tag"):
                    item_data["partes"].append(
                        {
                            "tag": parte.tag,
                            "codigo": parte.codigo,
                            "nombre": parte.nombre,
                        }
                    )
                subsistema_data["items"].append(item_data)
            sistema_data["subsistemas"].append(subsistema_data)
        jerarquia.append(sistema_data)
    return jerarquia


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
        self.assertContains(response, "PAR-DET")


@pytest.mark.django_db
class TaxonomiaImporterTests(TestCase):
    def setUp(self):
        super().setUp()
        self.activo = Activo.objects.create(
            codigo="AC-IMP",
            numero_activo="0010",
            nombre="Activo Importable",
        )

    def test_import_crea_jerarquia_completa(self):
        upload = build_taxonomia_upload(
            [
                [
                    "SYS-1",
                    "S01",
                    "Sistema 1",
                    "SUB-1",
                    "SS01",
                    "Subsistema 1",
                    "ITEM-1",
                    "IT01",
                    "Item 1",
                    "PAR-1",
                    "P01",
                    "Parte 1",
                ]
            ]
        )

        importer = TaxonomiaImporter(activo=self.activo, archivo=upload)
        summary = importer.importar()

        assert summary.sistemas_creados == 1
        assert summary.subsistemas_creados == 1
        assert summary.items_creados == 1
        assert summary.partes_creadas == 1
        assert summary.total_creados == 4
        assert not summary.errores

        sistema = Sistema.objects.get(tag="SYS-1")
        subsistema = Subsistema.objects.get(tag="SUB-1")
        item = ItemMantenible.objects.get(tag="ITEM-1")
        parte = Parte.objects.get(tag="PAR-1")

        assert sistema.nombre == "Sistema 1"
        assert subsistema.nombre == "Subsistema 1"
        assert item.nombre == "Item 1"
        assert parte.nombre == "Parte 1"

    def test_import_actualiza_registros_existentes(self):
        sistema = Sistema.objects.create(
            activo=self.activo,
            tag="SYS-1",
            codigo="OLD",
            nombre="Sistema Viejo",
        )
        subsistema = Subsistema.objects.create(
            sistema=sistema,
            tag="SUB-1",
            codigo="OLD",
            nombre="Subsistema Viejo",
        )
        item = ItemMantenible.objects.create(
            subsistema=subsistema,
            tag="ITEM-1",
            codigo="OLD",
            nombre="Item Viejo",
        )
        parte = Parte.objects.create(
            item=item,
            tag="PAR-1",
            codigo="OLD",
            nombre="Parte Vieja",
        )

        upload = build_taxonomia_upload(
            [
                [
                    "SYS-1",
                    "S02",
                    "Sistema Nuevo",
                    "SUB-1",
                    "SS02",
                    "Subsistema Nuevo",
                    "ITEM-1",
                    "IT02",
                    "Item Nuevo",
                    "PAR-1",
                    "P02",
                    "Parte Nueva",
                ]
            ]
        )

        importer = TaxonomiaImporter(activo=self.activo, archivo=upload)
        summary = importer.importar()

        assert summary.sistemas_actualizados == 1
        assert summary.subsistemas_actualizados == 1
        assert summary.items_actualizados == 1
        assert summary.partes_actualizados == 1
        assert not summary.errores

        sistema.refresh_from_db()
        subsistema.refresh_from_db()
        item.refresh_from_db()
        parte.refresh_from_db()

        assert sistema.nombre == "Sistema Nuevo"
        assert sistema.codigo == "S02"
        assert subsistema.nombre == "Subsistema Nuevo"
        assert item.nombre == "Item Nuevo"
        assert parte.nombre == "Parte Nueva"

    def test_import_con_limpiar_elimina_jerarquia_previa(self):
        Sistema.objects.create(
            activo=self.activo,
            tag="SYS-OLD",
            codigo="OLD",
            nombre="Sistema Antiguo",
        )

        upload = build_taxonomia_upload(
            [
                [
                    "SYS-NEW",
                    "SN",
                    "Sistema Nuevo",
                    "SUB-NEW",
                    "SSN",
                    "Subsistema Nuevo",
                    "ITEM-NEW",
                    "IN",
                    "Item Nuevo",
                    "PAR-NEW",
                    "PN",
                    "Parte Nueva",
                ]
            ]
        )

        importer = TaxonomiaImporter(activo=self.activo, archivo=upload, limpiar=True)
        summary = importer.importar()

        assert not Sistema.objects.filter(tag="SYS-OLD").exists()
        assert Sistema.objects.filter(tag="SYS-NEW").exists()
        assert summary.sistemas_creados == 1
        assert not summary.errores

    def test_import_snapshot_muestra_taxonomia_esperada(self):
        upload = build_taxonomia_upload(
            [
                [
                    "SYS-VER",
                    "SVER",
                    "Sistema Verificación",
                    "SUB-VER",
                    "SSVER",
                    "Subsistema Verificación",
                    "ITEM-A",
                    "ITA",
                    "Item A",
                    "PAR-A",
                    "PA",
                    "Parte A",
                ],
                [
                    "SYS-VER",
                    "SVER",
                    "Sistema Verificación",
                    "SUB-VER",
                    "SSVER",
                    "Subsistema Verificación",
                    "ITEM-B",
                    "ITB",
                    "Item B",
                    "PAR-B",
                    "PB",
                    "Parte B",
                ],
            ]
        )

        importer = TaxonomiaImporter(activo=self.activo, archivo=upload)
        importer.importar()

        assert snapshot_taxonomia(self.activo) == [
            {
                "tag": "SYS-VER",
                "codigo": "SVER",
                "nombre": "Sistema Verificación",
                "subsistemas": [
                    {
                        "tag": "SUB-VER",
                        "codigo": "SSVER",
                        "nombre": "Subsistema Verificación",
                        "items": [
                            {
                                "tag": "ITEM-A",
                                "codigo": "ITA",
                                "nombre": "Item A",
                                "partes": [
                                    {
                                        "tag": "PAR-A",
                                        "codigo": "PA",
                                        "nombre": "Parte A",
                                    }
                                ],
                            },
                            {
                                "tag": "ITEM-B",
                                "codigo": "ITB",
                                "nombre": "Item B",
                                "partes": [
                                    {
                                        "tag": "PAR-B",
                                        "codigo": "PB",
                                        "nombre": "Parte B",
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

    def test_import_registra_errores_de_fila(self):
        upload = build_taxonomia_upload(
            [
                [
                    "",
                    "S01",
                    "Sistema sin tag",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            ]
        )

        importer = TaxonomiaImporter(activo=self.activo, archivo=upload)
        summary = importer.importar()

        assert summary.total_creados == 0
        assert summary.errores
        assert "Falta el tag del sistema" in summary.errores[0]

    def test_import_sin_encabezados_validos_lanza_error(self):
        upload = build_taxonomia_upload(
            [["dato"]],
            headers=["Sin datos"],
        )

        importer = TaxonomiaImporter(activo=self.activo, archivo=upload)
        with self.assertRaises(TaxonomiaImportError):
            importer.importar()


@pytest.mark.django_db
class ActivosListImportViewTests(TestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="operador",
            password="testpass",
            is_staff=True,
        )
        self.activo = Activo.objects.create(
            codigo="AC-20",
            numero_activo="0020",
            nombre="Activo Veinte",
        )

    def _login(self):
        self.client.force_login(self.user)

    def test_post_importa_taxonomia(self):
        self._login()
        upload = build_taxonomia_upload(
            [
                [
                    "SYS-20",
                    "S20",
                    "Sistema 20",
                    "SUB-20",
                    "SS20",
                    "Subsistema 20",
                    "ITEM-20",
                    "IT20",
                    "Item 20",
                    "PAR-20",
                    "P20",
                    "Parte 20",
                ]
            ]
        )

        response = self.client.post(
            reverse("activos:activos_list"),
            data={"activo": self.activo.pk, "archivo": upload, "limpiar": ""},
            follow=True,
        )

        self.assertRedirects(response, reverse("activos:activos_list"))
        assert Sistema.objects.filter(activo=self.activo, tag="SYS-20").exists()

    def test_post_con_errores_muestra_mensaje(self):
        self._login()
        response = self.client.post(
            reverse("activos:activos_list"),
            data={"activo": self.activo.pk},
            follow=True,
        )

        assert response.status_code == 200
        self.assertContains(
            response,
            "Corrige los errores del formulario de importación.",
        )
        assert Sistema.objects.count() == 0