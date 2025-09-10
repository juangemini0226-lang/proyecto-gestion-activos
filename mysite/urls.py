# mysite/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Home, dashboard, etc. desde 'core'
    path("", include("core.urls")),
    # Admin
    path("admin/", admin.site.urls),
    path("_nested_admin/", include("nested_admin.urls")),
    # Autenticación (tu app 'accounts')
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    # Otras apps
    path("escaner/", include("lector_qr.urls")),
    #path("activos/", include("activos.urls")),
    path("horometro/", include("horometro.urls")),
    path("activos/", include(("activos.urls", "activos"), namespace="activos")),
    path("reports/", include(("reports.urls", "reports"), namespace="reports")),
    
]

# Archivos de usuario (MEDIA) sólo en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
