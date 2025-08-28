import os
import tempfile
from django.test import TestCase, override_settings
from activos.models import Activo, CategoriaActivo, EstadoActivo, Ubicacion


class ActivoModelTests(TestCase):
    def test_activo_generates_qr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                categoria = CategoriaActivo.objects.create(nombre="Vehículo")
                estado = EstadoActivo.objects.create(nombre="Operativo")
                ubicacion = Ubicacion.objects.create(nombre="Planta 1")
                activo = Activo.objects.create(
                    codigo="A1",
                    numero_activo="001",
                    nombre="Camión",
                    categoria=categoria,
                    estado=estado,
                    ubicacion=ubicacion,
                )
                self.assertTrue(activo.qr_code.name)
                path = os.path.join(tmpdir, activo.qr_code.name)
                self.assertTrue(os.path.exists(path))
