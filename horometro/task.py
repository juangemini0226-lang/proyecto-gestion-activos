from pathlib import Path

from celery import shared_task
from django.conf import settings

from .services import importer


@shared_task
def importar_horometro_task(path: str | None = None, sheet: str | None = None):
    """Tarea de Celery que importa el horómetro semanal."""
    ruta = Path(path) if path else Path(settings.BASE_DIR) / "excel" / "Horometro_actualizado.xlsx"
    if not ruta.exists():
        return "archivo no encontrado"
    with ruta.open("rb") as fh:
        res = importer.importar_excel(fh, nombre_hoja=sheet, dry_run=False)
    return res["resumen"]