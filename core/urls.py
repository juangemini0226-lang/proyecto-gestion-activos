# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path("dashboard/horometro/", views.dashboard_horometro, name="dashboard_horometro"),
    path("dashboard/novedades/", views.dashboard_novedades, name="dashboard_novedades"),
]