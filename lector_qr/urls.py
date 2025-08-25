# lector_qr/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Cuando alguien visite la URL raíz de esta app, se ejecutará la vista "escaner_qr"
    path('', views.escaner_qr, name='escaner'),
]

