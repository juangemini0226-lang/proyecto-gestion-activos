from django.core.management.base import BaseCommand, CommandError
from horometro.services import importer

class Command(BaseCommand):
    help = "Importa lecturas de horómetro desde un archivo Excel"

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta del .xlsx")
        parser.add_argument("--sheet", type=str, default=None)
        parser.add_argument("--commit", action="store_true", help="Guardar (por defecto: dry-run)")

    def handle(self, *args, **opts):
        ruta = opts["archivo"]
        try:
            with open(ruta, "rb") as f:
                res = importer.importar_excel(f, nombre_hoja=opts["sheet"], dry_run=not opts["commit"])
        except FileNotFoundError:
            raise CommandError(f"Archivo no encontrado: {ruta}")

        self.stdout.write(self.style.SUCCESS(res["resumen"]))
        if res["errores"]:
            self.stdout.write(self.style.WARNING("Errores:\n" + res["errores"]))
