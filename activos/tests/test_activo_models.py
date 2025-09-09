import os
import tempfile
from django.test import TestCase, override_settings
from activos.models import (
    Activo,
    CategoriaActivo,
    EstadoActivo,
    Ubicacion,
    TipoUbicacion,
)


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
                self.assertTrue(os.path.exists(activo.qr_code.path))

    def test_activo_hierarchy_properties(self):
        industria = Ubicacion.objects.create(nombre="Ind", tipo=TipoUbicacion.INDUSTRIA)
        empresa = Ubicacion.objects.create(nombre="Emp", tipo=TipoUbicacion.EMPRESA, padre=industria)
        planta = Ubicacion.objects.create(nombre="Pla", tipo=TipoUbicacion.PLANTA, padre=empresa)
        proceso = Ubicacion.objects.create(nombre="Pro", tipo=TipoUbicacion.PROCESO, padre=planta)
        seccion = Ubicacion.objects.create(nombre="Sec", tipo=TipoUbicacion.SECCION, padre=proceso)
        unidad = Ubicacion.objects.create(nombre="Uni", tipo=TipoUbicacion.UNIDAD, padre=seccion)
        subunidad = Ubicacion.objects.create(nombre="Sub", tipo=TipoUbicacion.SUBUNIDAD, padre=unidad)
        item = Ubicacion.objects.create(nombre="Item", tipo=TipoUbicacion.ITEM, padre=subunidad)
        parte = Ubicacion.objects.create(nombre="Parte", tipo=TipoUbicacion.PARTE, padre=item)
        categoria = CategoriaActivo.objects.create(nombre="Vehículo")
        estado = EstadoActivo.objects.create(nombre="Operativo")
        activo = Activo.objects.create(
            codigo="A2",
            numero_activo="002",
            nombre="Activo",
            categoria=categoria,
            estado=estado,
            ubicacion=parte,
        )
        self.assertEqual(activo.industria, industria)
        self.assertEqual(activo.empresa, empresa)
        self.assertEqual(activo.planta, planta)
        self.assertEqual(activo.proceso, proceso)
        self.assertEqual(activo.seccion, seccion)
        self.assertEqual(activo.unidad, unidad)
        self.assertEqual(activo.subunidad, subunidad)
        self.assertEqual(activo.item_mantenible, item)
        self.assertEqual(activo.parte, parte)