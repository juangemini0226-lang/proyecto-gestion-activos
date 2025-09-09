from django.test import TestCase
from activos.models import Ubicacion


class UbicacionModelTests(TestCase):
    def test_str_ignores_cycles(self):
        a = Ubicacion.objects.create(nombre="A")
        b = Ubicacion.objects.create(nombre="B", padre=a)
        a.padre = b
        a.save()
        self.assertEqual(str(a), "B / A")
        self.assertEqual(str(b), "A / B")

    def test_str_self_parent(self):
        u = Ubicacion.objects.create(nombre="Self")
        u.padre = u
        u.save()
        self.assertEqual(str(u), "Self")
