# horometro/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import LecturaHorometro
from .services.alerts import sync_alert_for_reading

@receiver(post_save, sender=LecturaHorometro)
def lecturahorometro_post_save(sender, instance: LecturaHorometro, **kwargs):
    # Ejecuta la sincronización SOLO cuando la transacción ya fue confirmada
    transaction.on_commit(lambda: sync_alert_for_reading(instance))
