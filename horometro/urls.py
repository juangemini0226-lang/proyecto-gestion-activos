# horometro/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="horometro_dashboard"),
    # Carga del Excel (semana a semana)
    path("subir/", views.subir_excel, name="horometro_subir"),
    path("upload/", views.subir_excel, name="horometro_upload"),  # alias para plantillas que ya lo usan

    # Historial por activo (tabla + gráfica)
    path("activo/<str:codigo>/", views.historial_activo, name="horometro_historial"),

    # Alertas de mantenimiento
    path("mantenimiento/alertas/", views.lista_alertas, name="horometro_alertas"),
    path("mantenimiento/alertas/<int:pk>/estado/", views.cambiar_estado_alerta, name="horometro_alerta_estado"),
]
