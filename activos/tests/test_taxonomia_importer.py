import pandas as pd
from django.test import TestCase

from activos.importers import TaxonomiaImporter
from activos.models import Activo, Parte


class TaxonomiaImporterTests(TestCase):
    def setUp(self):
        super().setUp()
        self.activo = Activo.objects.create(
            codigo="AC-100",
            numero_activo="000100",
            nombre="Activo Importado",
        )

    def test_reimportar_conserva_tag_parte_cuando_excel_no_aporta(self):
        datos = pd.DataFrame(
            [
                {
                    "Sistema": "Sistema Principal",
                    "Subsistema": "Subsistema A",
                    "Item": "Item X",
                    "Parte": "Filtro de Aceite",
                    "Codigo Parte": "F-001",
                    "Parte TAG": "",
                }
            ]
        )

        importer = TaxonomiaImporter(self.activo, datos)
        importer.importar()

        parte = Parte.objects.get(item__subsistema__sistema__activo=self.activo)
        tag_inicial = parte.tag
        self.assertTrue(tag_inicial)

        # Reprocesar el mismo archivo no debe alterar el tag existente si el Excel
        # sigue sin proporcionar un valor explícito.
        importer = TaxonomiaImporter(self.activo, datos)
        importer.importar()

        parte.refresh_from_db()
        self.assertEqual(parte.tag, tag_inicial)
