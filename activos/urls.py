# activos/urls.py
from django.urls import path
from . import views

app_name = "activos"

urlpatterns = [
    path("", views.ordenes_list, name="ordenes_list"),
    path("mis-tareas/", views.mis_tareas, name="mis_tareas"),
    path("agendar/", views.agendar_mantenimiento, name="agendar_mantenimiento"),
    path("asignar/<int:pk>/", views.asignar_ot, name="asignar_ot"),
    path("checklist/<int:registro_id>/", views.checklist_mantenimiento, name="checklist_mantenimiento"),
    path("cambiar-estado/<int:pk>/", views.cambiar_estado_ot, name="cambiar_estado_ot"),
    path("crear-ot-desde-alerta/<int:pk>/", views.crear_ot_desde_alerta, name="crear_ot_desde_alerta"),
    path("detalle/<str:codigo>/", views.detalle_activo_por_codigo, name="detalle_activo_por_codigo"),
    path("iniciar/<int:activo_id>/", views.iniciar_mantenimiento, name="iniciar_mantenimiento"),
]
