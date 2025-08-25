# horometro/services/baselines.py
from django.db import transaction

def aplicar_baseline_y_alertas(ot):
    """
    Ajusta baseline del horómetro al cerrar una OT preventiva
    y recalcula ΔPrev + alertas. No cierra alertas automáticamente.
    - ot.activo: FK al activo
    - Se asume ot.tipo in {'PREV', 'CORR'}
    """
    # TODO AJUSTAR: nombres reales de modelos/campos del horómetro:
    #   - LecturaHorometro: (activo, lectura, fecha/semana, ...)
    #   - EstadoHorometro o campo en Activo para baseline_preventivo
    #   - services.alerts: funciones para (re)calcular alertas
    from horometro.models import LecturaHorometro
    from horometro.services.alerts import recalcular_alertas_para_activo  # ya existe según snapshot

    if getattr(ot, 'tipo', None) != 'PREV':
        # Solo hace baseline en OT preventiva
        recalcular_alertas_para_activo(ot.activo_id)  # mantiene coherencia de ΔPrev sin cerrar nada
        return

    with transaction.atomic():
        # 1) Determinar lectura más reciente del activo (o la de cierre si se guarda)
        ultima = (LecturaHorometro.objects
                  .filter(activo_id=ot.activo_id)
                  .order_by('-fecha', '-id')  # ajustar a 'semana' si es por semana
                  .first())
        lectura_base = ultima.lectura if ultima else 0

        # 2) Guardar baseline en el activo (ajustar campo real)
        activo = ot.activo
        if hasattr(activo, 'baseline_preventivo'):
            activo.baseline_preventivo = lectura_base
            activo.save(update_fields=['baseline_preventivo'])

        # 3) Recalcular ΔPrev y (re)generar alertas (sin cerrar automáticamente)
        recalcular_alertas_para_activo(ot.activo_id)
