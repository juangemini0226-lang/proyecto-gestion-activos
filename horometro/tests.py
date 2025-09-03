from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from activos.models import Activo
from .models import AlertaMantenimiento, LecturaHorometro


class AlertaMantenimientoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pw")
        self.activo = Activo.objects.create(
            codigo="A1", numero_activo="1", nombre="Excavadora"
        )
        self.lectura = LecturaHorometro.objects.create(
            activo=self.activo, anio=2024, semana=1, lectura=Decimal("100")
        )

    def test_crear_actualizar_cerrar_alerta(self):
        alerta = AlertaMantenimiento.objects.create(
            activo=self.activo,
            lectura=self.lectura,
            anio=2024,
            semana=1,
            valor_ciclos=Decimal("1000"),
            creado_por=self.user,
        )
        self.assertEqual(alerta.estado, "NUEVA")
        self.assertTrue(alerta.abierta)

        alerta.estado = "EN_PROCESO"
        alerta.save()
        self.assertTrue(alerta.abierta)

        alerta.estado = "CERRADA"
        alerta.cerrado_en = timezone.now()
        alerta.save()
        self.assertFalse(alerta.abierta)
        self.assertIsNotNone(alerta.cerrado_en)

