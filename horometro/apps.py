from django.apps import AppConfig


class HorometroConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'horometro'

    def ready(self):
        from . import signals