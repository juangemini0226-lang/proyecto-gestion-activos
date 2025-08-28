from django.urls import path
from . import views

app_name = "activos"

urlpatterns = [
    path("", views.ordenes_list, name="ordenes_list"),
    path("listado/", views.activos_list, name="activos_list"),
    path("listado/nuevo/", views.activo_create, name="activo_create"),
    path("listado/<int:pk>/editar/", views.activo_update, name="activo_update"),
    #path("mis-tareas/", views.mis_tareas, name="mis_tareas"),
    path("agendar/", views.agendar_mantenimiento, name="agendar_mantenimiento"),
    path("crear-ot/", views.agendar_mantenimiento, name="crear_ot"),
    path("buscar/<str:codigo>/", views.redirect_buscar_a_detalle, name="buscar_activo"),
    path("detalle/<str:codigo>/", views.detalle_activo_por_codigo, name="detalle_activo_por_codigo"),
    path("iniciar/<int:activo_id>/", views.iniciar_mantenimiento, name="iniciar_mantenimiento"),
    path("asignar/<int:pk>/", views.asignar_ot, name="asignar_ot"),
    #path("crear-ot-desde-alerta/<int:pk>/", views.crear_ot_desde_alerta, name="crear_ot_desde_alerta"),
    path("mantenimiento/<int:pk>/checklist/", views.checklist_mantenimiento, name="checklist_mantenimiento"),
    #path("mantenimiento/<int:pk>/cambiar-estado/", views.cambiar_estado_ot, name="cambiar_estado_ot"),
]
