from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from horometro.services import importer
from django.conf import settings


class Command(BaseCommand):
    """Importa lecturas del horómetro desde ``Horometro_actualizado.xlsx``.

    El archivo se busca por defecto en la carpeta ``excel`` del proyecto.
    Se puede indicar otra ruta con ``--path`` y una hoja específica con
    ``--sheet``.  Por defecto se ejecuta en *dry-run*.
    """

    help = "Importa lecturas del horómetro desde un archivo actualizado"

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(Path(settings.BASE_DIR) / "excel" / "Horometro_actualizado.xlsx"),
            help="Ruta del archivo a procesar",
        )
        parser.add_argument("--sheet", default=None, help="Nombre de la hoja a usar")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Guardar cambios en base de datos (por defecto solo simula)",
        )

    def handle(self, *args, **opts):
        ruta = Path(opts["path"])
        if not ruta.exists():
            raise CommandError(f"Archivo no encontrado: {ruta}")

        with ruta.open("rb") as fh:
            res = importer.importar_excel(
                fh,
                nombre_hoja=opts["sheet"],
                dry_run=not opts["commit"],
            )

        self.stdout.write(self.style.SUCCESS(res["resumen"]))
        if res.get("errores"):
            self.stdout.write(self.style.WARNING("Errores:\n" + res["errores"]))