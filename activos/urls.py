# activos/urls.py
from django.urls import path
from . import views

app_name = "activos"

urlpatterns = [
    # URLs Generales
    path("", views.ordenes_list, name="ordenes_list"),
    path("mis-tareas/", views.mis_tareas, name="mis_tareas"),
    path("agendar/", views.agendar_mantenimiento, name="agendar_mantenimiento"),
    path("detalle/<str:codigo>/", views.detalle_activo_por_codigo, name="detalle_activo_por_codigo"),
    
    # URLs de Acciones sobre Activos/OTs
    path("iniciar/<int:activo_id>/", views.iniciar_mantenimiento, name="iniciar_mantenimiento"),
    path("asignar/<int:pk>/", views.asignar_ot, name="asignar_ot"),
    path("crear-ot-desde-alerta/<int:pk>/", views.crear_ot_desde_alerta, name="crear_ot_desde_alerta"),

    # --- ESTRUCTURA CORREGIDA Y UNIFICADA ---
    # Todas las acciones para una OT específica ahora empiezan con 'mantenimiento/<pk>/'

    # Corregido: Se usa 'pk' para estandarizar y la ruta es más clara.
    path('mantenimiento/<int:pk>/checklist/', views.checklist_mantenimiento, name='checklist_mantenimiento'),
    
    # Corregido: Esta es la única URL para cambiar el estado.
    path('mantenimiento/<int:pk>/cambiar-estado/', views.cambiar_estado_ot, name='cambiar_estado_ot'),
]