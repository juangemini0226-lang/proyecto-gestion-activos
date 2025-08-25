# accounts/urls.py
from django.urls import path, include


urlpatterns = [
    # Incluimos todas las URLs de autenticación de Django aquí
    path('', include('django.contrib.auth.urls')),

    # En el futuro, aquí podrías añadir una ruta para un formulario de registro:
    # path('register/', views.register, name='register'),
]

