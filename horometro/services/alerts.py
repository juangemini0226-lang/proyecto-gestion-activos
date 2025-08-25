# horometro/services/alerts.py
from __future__ import annotations
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional, Iterable, Tuple
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from horometro.models import LecturaHorometro, AlertaMantenimiento

# ====================== Umbrales ======================
ALERTA_UMBRAL = Decimal("70000")   # Rojo / Alerta
WARN_UMBRAL   = Decimal("60000")   # Amarillo (si lo usas en UI)
THRESHOLD     = ALERTA_UMBRAL      # alias p/compatibilidad externa


# ====================== Utilidades ======================
def _ywk_key(y: int, w: int) -> int:
    """Convierte (año, semana) en entero comparable (y*100+w)."""
    return int(y) * 100 + int(w)


def _delta_prev(lh: LecturaHorometro) -> Optional[Decimal]:
    """
    ΔPrev = ciclos desde el último preventivo.
      1) Usa lh.ciclos_desde_ultimo_preventivo si está.
      2) Si no, intenta (lh.lectura - lh.ciclo_ultimo_preventivo).
      3) Si no, intenta (lh.ciclos_oracle - lh.ciclo_ultimo_preventivo).
    """
    if lh.ciclos_desde_ultimo_preventivo is not None:
        return lh.ciclos_desde_ultimo_preventivo

    base = lh.lectura if lh.lectura is not None else lh.ciclos_oracle
    if base is not None and lh.ciclo_ultimo_preventivo is not None:
        try:
            return Decimal(base) - Decimal(lh.ciclo_ultimo_preventivo)
        except Exception:
            return None
    return None


def _has_later_reading(lh: LecturaHorometro) -> bool:
    """
    ¿Existe una lectura posterior (año/semana mayor) para este activo?
    Se usa para garantizar que sólo la última semana genere/actualice/cierre alertas.
    """
    return LecturaHorometro.objects.filter(
        activo=lh.activo
    ).filter(
        Q(anio__gt=lh.anio) | (Q(anio=lh.anio) & Q(semana__gt=lh.semana))
    ).exists()


def _latest_reading_for(activo) -> Optional[LecturaHorometro]:
    """Devuelve la última lectura por (anio, semana) para un activo."""
    return (
        LecturaHorometro.objects
        .filter(activo=activo)
        .order_by("anio", "semana")
        .last()
    )


# ====================== Resultado ======================
@dataclass
class SyncResult:
    created: bool = False
    updated: bool = False
    closed_previous: bool = False
    closed_existing: bool = False
    skipped: bool = False
    reason: str = ""


# ====================== Sincronización ======================
@transaction.atomic
def sync_alert_for_reading(
    lh: LecturaHorometro,
    umbral: Decimal = ALERTA_UMBRAL,
    *,
    only_latest: bool = True,
) -> SyncResult:
    """
    Sincroniza la alerta en función **de esta lectura**.

    Reglas:
      - Si only_latest=True (por defecto), solo la **última** semana del activo
        puede crear/actualizar/cerrar alertas. Las lecturas antiguas se ignoran.
      - Si ΔPrev >= umbral => crea/actualiza alerta (NUEVA si no existe).
      - Si ΔPrev  < umbral => cierra alerta abierta (NUEVA/EN_PROCESO) si esta
        lectura es la última o de la misma/semana posterior (según only_latest).

    Devuelve un SyncResult con lo que ocurrió.
    """
    sr = SyncResult()

    # Restringir a la última semana si así se pide
    if only_latest and _has_later_reading(lh):
        sr.skipped = True
        sr.reason = "no_es_ultima_semana"
        return sr

    dprev = _delta_prev(lh)
    if dprev is None:
        sr.skipped = True
        sr.reason = "sin_delta"
        return sr
    # Evita alertas con ΔPrev negativo por datos inconsistentes
    if dprev < 0:
        sr.skipped = True
        sr.reason = "delta_negativo"
        return sr

    # Alerta abierta (NUEVA/EN_PROCESO) más reciente para el activo
    open_alert = (
        AlertaMantenimiento.objects
        .filter(activo=lh.activo, estado__in=["NUEVA", "EN_PROCESO"])
        .order_by("-anio", "-semana")
        .first()
    )

    this_key = _ywk_key(lh.anio, lh.semana)
    open_key = _ywk_key(open_alert.anio, open_alert.semana) if open_alert else -1

    if dprev >= umbral:
        # Si hay una alerta abierta de una semana anterior, la cerramos
        if open_alert and open_key < this_key:
            open_alert.estado = "CERRADA"
            open_alert.cerrado_en = timezone.now()
            open_alert.save(update_fields=["estado", "cerrado_en", "actualizado_en"])
            sr.closed_previous = True

        # Creamos/actualizamos la alerta para ESTA semana
        alerta, created = AlertaMantenimiento.objects.get_or_create(
            activo=lh.activo, anio=lh.anio, semana=lh.semana,
            defaults={"valor_ciclos": dprev, "umbral": umbral, "estado": "NUEVA"},
        )
        if created:
            sr.created = True
        else:
            # Actualizamos valores; si está EN_PROCESO, respetamos su estado
            alerta.valor_ciclos = dprev
            alerta.umbral = umbral
            alerta.save(update_fields=["valor_ciclos", "umbral", "actualizado_en"])
            sr.updated = True

        return sr

    # dprev < umbral: cerrar si corresponde
    # (si only_latest=True, this_key ya es la última semana del activo)
    if open_alert and this_key >= open_key:
        open_alert.estado = "CERRADA"
        open_alert.cerrado_en = timezone.now()
        open_alert.save(update_fields=["estado", "cerrado_en", "actualizado_en"])
        sr.closed_existing = True
    else:
        sr.skipped = True
        sr.reason = "debajo_umbral"
    return sr


# ---------- Helpers para usos puntuales ----------
def sync_alert_for_latest_of(activo, umbral: Decimal = ALERTA_UMBRAL) -> SyncResult:
    """
    Busca la última lectura de `activo` y sincroniza su alerta.
    Útil para jobs/reparaciones manuales.
    """
    lh = _latest_reading_for(activo)
    if not lh:
        return SyncResult(skipped=True, reason="sin_lecturas")
    return sync_alert_for_reading(lh, umbral=umbral, only_latest=True)


def recompute_all_alerts(umbral: Decimal = ALERTA_UMBRAL) -> Tuple[int, int, int]:
    """
    Recorre todos los activos que tienen lecturas y recalcula la alerta
    en función de su **última** semana. Devuelve (creadas, actualizadas, cerradas).
    """
    created = updated = closed = 0
    activos_ids = (
        LecturaHorometro.objects.values_list("activo_id", flat=True).distinct()
    )
    for aid in activos_ids:
        lh = (
            LecturaHorometro.objects
            .filter(activo_id=aid)
            .order_by("anio", "semana")
            .last()
        )
        if not lh:
            continue
        res = sync_alert_for_reading(lh, umbral=umbral, only_latest=True)
        if res.created: created += 1
        if res.updated: updated += 1
        if res.closed_existing or res.closed_previous: closed += 1
    return created, updated, closed
