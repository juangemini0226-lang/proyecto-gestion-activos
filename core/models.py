# core/models.py  
from django.conf import settings
from django.db import models

class HistorialOT(models.Model):
    ot = models.ForeignKey('activos.RegistroMantenimiento', on_delete=models.CASCADE, related_name='historial')
    estado_anterior = models.CharField(max_length=3, blank=True)
    estado_nuevo = models.CharField(max_length=3)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    comentario = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ot']),
            models.Index(fields=['estado_nuevo']),
            models.Index(fields=['-timestamp']),
        ]
