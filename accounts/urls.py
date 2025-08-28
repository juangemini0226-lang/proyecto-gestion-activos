# accounts/urls.py
from django.urls import path, include
from . import views

app_name = "accounts"


urlpatterns = [
    path("users/", views.users_list, name="users_list"),
    # Incluimos todas las URLs de autenticación de Django aquí
    path("", include("django.contrib.auth.urls")),

    # En el futuro, aquí podrías añadir una ruta para un formulario de registro:
    # path('register/', views.register, name='register'),
]