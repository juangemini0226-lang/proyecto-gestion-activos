from django.test import TestCase
from activos.models import (
    Activo,
    FamiliaActivo,
    CategoriaActivo,
    EstadoActivo,
    Ubicacion,
    TipoUbicacion,
)


class ActivoComponentesTest(TestCase):
    def setUp(self):
        self.familia = FamiliaActivo.objects.create(nombre="Moldes")
        self.categoria = CategoriaActivo.objects.create(nombre="Molde de inyección")
        self.estado = EstadoActivo.objects.create(nombre="Operativo")

    def test_activo_puede_tener_varios_componentes(self):
        molde = Activo.objects.create(
            codigo="MI-001",
            numero_activo="1",
            nombre="Molde base",
            familia=self.familia,
            categoria=self.categoria,
            estado=self.estado,
        )
        ubic1 = Ubicacion.objects.create(nombre="Sub1", tipo=TipoUbicacion.SUBUNIDAD)
        ubic2 = Ubicacion.objects.create(nombre="Sub2", tipo=TipoUbicacion.SUBUNIDAD)
        sistema1 = Activo.objects.create(
            codigo="SIS-1",
            numero_activo="2",
            nombre="Sistema hidráulico",
            familia=self.familia,
            categoria=self.categoria,
            estado=self.estado,
            ubicacion=ubic1,
        )
        sistema2 = Activo.objects.create(
            codigo="SIS-2",
            numero_activo="3",
            nombre="Sistema eléctrico",
            familia=self.familia,
            categoria=self.categoria,
            estado=self.estado,
            ubicacion=ubic2,
        )
        molde.componentes.add(sistema1, sistema2)
        self.assertEqual(molde.componentes.count(), 2)
        self.assertIn(molde, sistema1.es_parte_de.all())
        self.assertIn(molde, sistema2.es_parte_de.all())