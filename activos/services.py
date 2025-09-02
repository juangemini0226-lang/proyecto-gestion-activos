from django.conf import settings

from .models import RegistroMantenimiento, TipoOT, PrioridadOT

def escalar_novedad(novedad, force=False):
    """Escala la novedad a una OT según reglas configurables."""
    if novedad.orden_mantenimiento_id:
        return novedad.orden_mantenimiento
    reglas = getattr(settings, "NOVEDAD_FALLAS_CRITICAS", [])
    if not force and not (novedad.falla and novedad.falla.codigo in reglas):
        return None
    ot = RegistroMantenimiento.objects.create(
        activo=novedad.activo,
        falla=novedad.falla,
        titulo=novedad.descripcion[:160],
        tipo=TipoOT.COR,
        prioridad=PrioridadOT.ALTA,
        creado_por=novedad.reportado_por,
    )
    novedad.orden_mantenimiento = ot
    novedad.save(update_fields=["orden_mantenimiento"])
    return ot