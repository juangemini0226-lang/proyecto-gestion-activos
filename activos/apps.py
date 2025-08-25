from django.apps import AppConfig


class ActivosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "activos"
    verbose_name = "Gestión de Activos y Mantenimiento"

    def ready(self):
        # Registra los receivers de señales del app
        from . import signals  # noqa: F401
