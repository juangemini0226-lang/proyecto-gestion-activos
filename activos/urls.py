from django.urls import path
from . import views

app_name = "activos"

urlpatterns = [
    path("", views.ordenes_list, name="ordenes_list"),
    path("mis-tareas/", views.mis_tareas, name="mis_tareas"),
    path("agendar/", views.agendar_mantenimiento, name="agendar_mantenimiento"),

    # Alias para lo que genera el lector QR:
    path("buscar/<str:codigo>/", views.redirect_buscar_a_detalle, name="buscar_activo"),

    # La vista real de detalle por código:
    path("detalle/<str:codigo>/", views.detalle_activo_por_codigo, name="detalle_activo_por_codigo"),

    path("iniciar/<int:activo_id>/", views.iniciar_mantenimiento, name="iniciar_mantenimiento"),
    path("asignar/<int:pk>/", views.asignar_ot, name="asignar_ot"),
    path("crear-ot-desde-alerta/<int:pk>/", views.crear_ot_desde_alerta, name="crear_ot_desde_alerta"),
    path("mantenimiento/<int:pk>/checklist/", views.checklist_mantenimiento, name="checklist_mantenimiento"),
    path("mantenimiento/<int:pk>/cambiar-estado/", views.cambiar_estado_ot, name="cambiar_estado_ot"),
]
