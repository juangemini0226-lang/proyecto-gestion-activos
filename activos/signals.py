# activos/signals.py
from datetime import date
from decimal import Decimal

from django.utils import timezone
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from activos.models import (
    RegistroMantenimiento,
    EstadoOT,
    TipoOT,
)
from core.models import HistorialOT            # ✅ ahora desde core
from horometro.models import LecturaHorometro


@receiver(pre_save, sender=RegistroMantenimiento)
def _cache_old_estado(sender, instance: RegistroMantenimiento, **kwargs):
    """Guarda el estado anterior para detectar cambios de estado."""
    if instance.pk:
        instance._old_estado = (
            sender.objects.filter(pk=instance.pk)
            .values_list("estado", flat=True)
            .first()
        )
    else:
        instance._old_estado = None


def _iso_year_week(d: date):
    iso = d.isocalendar()
    # Compatibilidad py<3.9 / >=3.9
    year = getattr(iso, "year", iso[0])
    week = getattr(iso, "week", iso[1])
    return int(year), int(week)


@receiver(post_save, sender=RegistroMantenimiento)
def _post_ot_changes(sender, instance: RegistroMantenimiento, created, **kwargs):
    """
    Reacciona a cambios en RegistroMantenimiento:
      - Registra historial de cambio de estado.
      - Al pasar a PRO/REV fija sellos de tiempo si faltan.
      - Al cerrar (CER) y si es PRE, fija baseline en la lectura correspondiente y reinicia ΔPrev (no cierra alertas).
    """
    old = getattr(instance, "_old_estado", None)
    new = instance.estado

    # Si es creación, registrar estado inicial
    if created:
        HistorialOT.objects.create(
            ot=instance,
            estado_anterior="",
            estado_nuevo=new,
            usuario=None,            # si capturas usuario vía middleware, asígnalo aquí
            comentario="Creación de OT",
        )
        return

    # Si no cambió el estado, no hacer nada
    if old == new:
        return

    # --- Auditoría de cambio de estado ---
    HistorialOT.objects.create(
        ot=instance,
        estado_anterior=old or "",
        estado_nuevo=new,
        usuario=None,            # setéalo si lo tienes a mano
        comentario="",           # idem
    )

    # --- Sellos mínimos por transición (defensa si alguien evita métodos del modelo) ---
    if new == EstadoOT.PRO and not instance.fecha_inicio_ejecucion:
        instance.fecha_inicio_ejecucion = timezone.now()
        instance.save(update_fields=["fecha_inicio_ejecucion"])

    if new == EstadoOT.REV and not instance.fecha_fin_ejecucion:
        instance.fecha_fin_ejecucion = timezone.now()
        instance.save(update_fields=["fecha_fin_ejecucion"])

    # --- Efectos al cerrar: baseline preventivo ---
    if new == EstadoOT.CER:
        # Asegurar sello de fecha_cierre
        if not instance.fecha_cierre:
            instance.fecha_cierre = timezone.now()
            instance.save(update_fields=["fecha_cierre"])

        # Solo aplica baseline para preventivas
        if instance.tipo != TipoOT.PRE:
            _recalcular_alertas_safe(instance.activo_id)  # mantener ΔPrev coherente
            return

        # Determinar año/semana de ejecución
        if instance.anio_ejecucion and instance.semana_ejecucion:
            y, w = instance.anio_ejecucion, instance.semana_ejecucion
        else:
            base_date = instance.fecha_cierre.date() if instance.fecha_cierre else date.today()
            y, w = _iso_year_week(base_date)

        # Buscar lectura de esa semana; si no hay, usar la última del activo
        lh = (
            LecturaHorometro.objects
            .filter(activo=instance.activo, anio=y, semana=w)
            .order_by("anio", "semana")
            .last()
        ) or (
            LecturaHorometro.objects
            .filter(activo=instance.activo)
            .order_by("anio", "semana")
            .last()
        )

        if not lh:
            # No hay lecturas aún; no se puede fijar baseline
            return

        # Prioridad: lectura registrada en la OT -> lectura semanal -> lectura importada (ciclos_oracle)
        lectura = (
            instance.lectura_ejecucion
            or getattr(lh, "lectura", None)
            or getattr(lh, "ciclos_oracle", None)
        )
        if lectura is None:
            return

        # Fijar baseline preventivo en la lectura y reiniciar ΔPrev
        lh.ciclo_ultimo_preventivo = lectura
        lh.ciclos_desde_ultimo_preventivo = Decimal("0")
        lh.save(update_fields=["ciclo_ultimo_preventivo", "ciclos_desde_ultimo_preventivo"])

        # Recalcular alertas (no se cierran automáticamente)
        _recalcular_alertas_safe(instance.activo_id)


# ---- Utilidad opcional para recalcular alertas, si el servicio existe ----
def _recalcular_alertas_safe(activo_id: int):
    """
    Intenta recalcular alertas para el activo, si existe el servicio.
    No cierra alertas automáticamente (la política de cierre sigue siendo manual).
    """
    try:
        from horometro.services.alerts import recalcular_alertas_para_activo  # type: ignore
    except Exception:
        return
    try:
        recalcular_alertas_para_activo(activo_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Error recalculando alertas para activo %s", activo_id)
