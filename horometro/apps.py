from django.apps import AppConfig


class HorometroConfig(AppConfig):
    """Configuración de la aplicación Horómetro."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "horometro"
    verbose_name = "Horómetro"

    def ready(self) -> None:  # pragma: no cover - hook de inicialización
        # Importa señales al iniciar la aplicación
        from . import signals  # noqa: F401
